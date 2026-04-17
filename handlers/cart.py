"""Cart flow: add/decrement/remove, view, checkout as single invoice."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, LabeledPrice

from database import Database
from keyboards.user_kb import back_home, cart_keyboard

logger = logging.getLogger(__name__)
router = Router(name="cart")


async def _render_cart(callback: CallbackQuery, db: Database) -> None:
    lines = await db.cart_lines(callback.from_user.id)
    if not lines:
        await callback.message.edit_text(
            "🧺 Корзина пуста.\nЗагляни в каталог и добавь что-нибудь.",
            reply_markup=back_home(),
        )
        return

    total = sum(l.subtotal for l in lines)
    text_lines = ["🧺 <b>Твоя корзина:</b>\n"]
    for l in lines:
        text_lines.append(f"• {l.title} — {l.price_stars}⭐ × {l.quantity} = {l.subtotal}⭐")
    text_lines.append(f"\n💰 <b>Итого: {total} ⭐</b>")
    await callback.message.edit_text("\n".join(text_lines), reply_markup=cart_keyboard(lines))


@router.callback_query(F.data == "cart")
async def cb_cart_view(callback: CallbackQuery, db: Database) -> None:
    await _render_cart(callback, db)
    await callback.answer()


@router.callback_query(F.data.startswith("cart_add:"))
async def cb_cart_add(callback: CallbackQuery, db: Database) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    product = await db.get_product(product_id)
    if product is None or not product.is_active:
        await callback.answer("Товар недоступен", show_alert=True)
        return
    await db.cart_add(callback.from_user.id, product_id, delta=1)
    await callback.answer(f"Добавлено: {product.title}")

    # If the user is currently on the cart page, refresh it.
    current_text = callback.message.text or ""
    if current_text.startswith("🧺"):
        await _render_cart(callback, db)


@router.callback_query(F.data.startswith("cart_dec:"))
async def cb_cart_dec(callback: CallbackQuery, db: Database) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    await db.cart_decrement(callback.from_user.id, product_id)
    await _render_cart(callback, db)
    await callback.answer()


@router.callback_query(F.data.startswith("cart_rm:"))
async def cb_cart_rm(callback: CallbackQuery, db: Database) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    await db.cart_remove(callback.from_user.id, product_id)
    await _render_cart(callback, db)
    await callback.answer("Удалено")


@router.callback_query(F.data == "cart_clear")
async def cb_cart_clear(callback: CallbackQuery, db: Database) -> None:
    await db.cart_clear(callback.from_user.id)
    await _render_cart(callback, db)
    await callback.answer("Корзина очищена")


@router.callback_query(F.data == "cart_checkout")
async def cb_cart_checkout(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    lines = await db.cart_lines(callback.from_user.id)
    if not lines:
        await callback.answer("Корзина пуста", show_alert=True)
        return

    order_id, total = await db.create_order_from_cart(callback.from_user.id)

    # Build invoice prices — one LabeledPrice per line * quantity
    prices = [
        LabeledPrice(label=f"{l.title} ×{l.quantity}", amount=l.subtotal)
        for l in lines
    ]
    invoice_title = "Заказ #" + str(order_id)
    invoice_description = ", ".join(f"{l.title}×{l.quantity}" for l in lines)[:255]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=invoice_title,
        description=invoice_description or invoice_title,
        payload=f"order:{order_id}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )
    await callback.answer(f"Оформляем заказ на {total} ⭐")