"""User-facing handlers: menu, catalog, direct-buy, referrals, post-payment delivery."""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from config import Config
from database import Database, OrderItem
from keyboards.user_kb import (
    back_home,
    catalog_keyboard,
    main_menu,
    product_keyboard,
)
from utils.notifier import notify_admin_new_order

logger = logging.getLogger(__name__)
router = Router(name="user")

# How many stars a referrer earns per paid star (10 = 10%).
REFERRAL_PERCENT = 10

WELCOME = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    "Здесь ты можешь выбрать услугу и оплатить её через <b>Telegram Stars</b> ⭐.\n\n"
    "Выбери действие в меню:"
)

ABOUT = (
    "ℹ️ <b>О сервисе</b>\n\n"
    "Демонстрационный Telegram-магазин на aiogram 3 + MySQL.\n"
    "• Оплата через Telegram Stars\n"
    "• Корзина и авто-доставка контента после оплаты\n"
    "• Реферальная система и возвраты\n"
)


async def _send_menu(message: Message, db: Database) -> None:
    cart_count = len(await db.cart_lines(message.from_user.id))
    await message.answer(WELCOME, reply_markup=main_menu(cart_count))


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_deeplink(
    message: Message, command: CommandObject, db: Database
) -> None:
    referrer_id: int | None = None
    payload = command.args or ""
    if payload.startswith("ref_"):
        try:
            referrer_id = int(payload[4:])
        except ValueError:
            referrer_id = None

    user = message.from_user
    is_new = await db.upsert_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        referrer_id=referrer_id,
    )
    if is_new and referrer_id:
        logger.info("New user %s came from referrer %s", user.id, referrer_id)

    await _send_menu(message, db)


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    user = message.from_user
    await db.upsert_user(user_id=user.id, username=user.username, full_name=user.full_name)
    await _send_menu(message, db)


@router.callback_query(F.data == "home")
async def cb_home(callback: CallbackQuery, db: Database) -> None:
    cart_count = len(await db.cart_lines(callback.from_user.id))
    await callback.message.edit_text(WELCOME, reply_markup=main_menu(cart_count))
    await callback.answer()


@router.callback_query(F.data == "about")
async def cb_about(callback: CallbackQuery) -> None:
    await callback.message.edit_text(ABOUT, reply_markup=back_home())
    await callback.answer()


@router.callback_query(F.data == "catalog")
async def cb_catalog(callback: CallbackQuery, db: Database) -> None:
    products = await db.list_products()
    if not products:
        await callback.message.edit_text("Каталог пока пуст.", reply_markup=back_home())
        await callback.answer()
        return
    await callback.message.edit_text(
        "🛍 <b>Каталог услуг</b>\n\nВыбери интересующий товар:",
        reply_markup=catalog_keyboard(products),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("product:"))
async def cb_product_details(callback: CallbackQuery, db: Database) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    product = await db.get_product(product_id)
    if product is None or not product.is_active:
        await callback.answer("Товар не найден", show_alert=True)
        return
    text = (
        f"<b>{product.title}</b>\n\n"
        f"{product.description or ''}\n\n"
        f"💰 <b>Цена:</b> {product.price_stars} ⭐"
    )
    await callback.message.edit_text(text, reply_markup=product_keyboard(product.id))
    await callback.answer()


# ---------------- direct "Buy now" (skips cart) ----------------

@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    product = await db.get_product(product_id)
    if product is None or not product.is_active:
        await callback.answer("Товар не найден", show_alert=True)
        return

    order_id = await db.create_order_single(user_id=callback.from_user.id, product=product)
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=product.title,
        description=(product.description or product.title)[:255],
        payload=f"order:{order_id}",
        provider_token="",            # empty for Telegram Stars
        currency="XTR",
        prices=[LabeledPrice(label=product.title, amount=product.price_stars)],
    )
    await callback.answer()


# ---------------- payment plumbing ----------------

@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout: PreCheckoutQuery) -> None:
    await pre_checkout.answer(ok=True)


async def _deliver_item(bot: Bot, user_id: int, item: OrderItem) -> None:
    if item.delivery_type == "text" and item.delivery_text:
        await bot.send_message(user_id, f"🎁 <b>{item.product_title}</b>\n\n{item.delivery_text}")
    elif item.delivery_type == "file" and item.delivery_file_id:
        try:
            await bot.send_document(
                user_id, document=item.delivery_file_id,
                caption=f"🎁 {item.product_title}",
            )
        except Exception:
            # Fallback: maybe it's a photo file_id
            try:
                await bot.send_photo(user_id, photo=item.delivery_file_id,
                                     caption=f"🎁 {item.product_title}")
            except Exception as e:
                logger.error("Failed to deliver file for item %s: %s", item.product_title, e)


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message, db: Database, bot: Bot, config: Config
) -> None:
    payment = message.successful_payment
    payload = payment.invoice_payload or ""
    if not payload.startswith("order:"):
        return
    order_id = int(payload.split(":", 1)[1])

    await db.mark_order_paid(
        order_id=order_id,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
    )

    # clear cart (for cart-based orders it's safe; direct-buy has nothing in cart)
    await db.cart_clear(message.from_user.id)

    # deliver all items
    order = await db.get_order_full(order_id)
    if order:
        for item in order["items"]:
            await _deliver_item(bot, message.from_user.id, item)
        await db.mark_order_delivered(order_id)

    # confirmation
    await message.answer(
        f"✅ <b>Оплата получена, спасибо!</b>\n"
        f"Номер заказа: #{order_id}\n"
        f"Сумма: {payment.total_amount} ⭐",
        reply_markup=main_menu(0),
    )

    # referral bonus (10% of order total, rounded down)
    user_row = await db.get_user(message.from_user.id)
    if user_row and user_row.referrer_id:
        bonus = (payment.total_amount * REFERRAL_PERCENT) // 100
        if bonus > 0:
            await db.add_referral_bonus(user_row.referrer_id, bonus)
            try:
                await bot.send_message(
                    user_row.referrer_id,
                    f"💎 Твой реферал оплатил заказ! "
                    f"Тебе начислено <b>{bonus} ⭐</b> бонусных.",
                )
            except Exception:
                pass

    # admin notification
    items_text = ", ".join(f"{i.product_title}×{i.quantity}" for i in order["items"]) if order else ""
    await notify_admin_new_order(
        bot=bot,
        admin_id=config.admin_id,
        order_id=order_id,
        user_id=message.from_user.id,
        username=message.from_user.username,
        product_title=items_text or "—",
        amount_stars=payment.total_amount,
    )


# ---------------- my orders / referrals ----------------

@router.callback_query(F.data == "my_orders")
async def cb_my_orders(callback: CallbackQuery, db: Database) -> None:
    orders = await db.list_user_orders(callback.from_user.id, limit=10)
    if not orders:
        await callback.message.edit_text("У тебя пока нет заказов.", reply_markup=back_home())
        await callback.answer()
        return

    emoji = {"paid": "✅", "pending": "⏳", "cancelled": "❌", "refunded": "↩️"}
    lines = ["📦 <b>Твои последние заказы:</b>\n"]
    for o in orders:
        lines.append(f"{emoji.get(o.status, '•')} #{o.id} — {o.amount_stars} ⭐ ({o.status})")
    await callback.message.edit_text("\n".join(lines), reply_markup=back_home())
    await callback.answer()


@router.callback_query(F.data == "referrals")
async def cb_referrals(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{callback.from_user.id}"
    summary = await db.referral_summary(callback.from_user.id)

    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей и получай <b>{REFERRAL_PERCENT}%</b> с каждой их оплаты.\n\n"
        f"🔗 Твоя ссылка:\n<code>{link}</code>\n\n"
        f"👤 Приглашено: <b>{summary['invited']}</b>\n"
        f"💎 Накоплено бонусов: <b>{summary['bonus_stars']} ⭐</b>"
    )
    await callback.message.edit_text(text, reply_markup=back_home())
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()