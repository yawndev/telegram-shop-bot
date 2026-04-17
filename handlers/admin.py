"""Admin panel: stats, orders, CRUD products, broadcast, refund."""
import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from database import Database
from keyboards.admin_kb import (
    admin_back,
    admin_main,
    cancel_kb,
    confirm_kb,
    delivery_type_kb,
    product_manage,
    products_list,
)
from states import AddProduct, Broadcast, EditProduct, Refund

logger = logging.getLogger(__name__)
router = Router(name="admin")


def _is_admin(user_id: int, config: Config) -> bool:
    return user_id == config.admin_id


@router.message(Command("admin"))
async def cmd_admin(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id, config):
        return
    await state.clear()
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_main())


@router.callback_query(F.data == "admin:close")
async def cb_close(callback: CallbackQuery, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer()
        return
    await callback.message.delete()
    await callback.answer("Закрыто")


@router.callback_query(F.data == "admin:back")
async def cb_back(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_main())
    await callback.answer()


# =================================================================
# STATS / ORDERS
# =================================================================

@router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    s = await db.stats()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{s['users']}</b>\n"
        f"✅ Оплаченных: <b>{s['paid_orders']}</b>\n"
        f"⏳ В ожидании: <b>{s['pending_orders']}</b>\n"
        f"↩️ Возвратов: <b>{s['refunded_orders']}</b>\n"
        f"💰 Выручка: <b>{s['revenue_stars']} ⭐</b>"
    )
    await callback.message.edit_text(text, reply_markup=admin_back())
    await callback.answer()


@router.callback_query(F.data == "admin:orders")
async def cb_orders(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    orders = await db.list_recent_orders(limit=10)
    if not orders:
        await callback.message.edit_text("Заказов ещё нет.", reply_markup=admin_back())
        await callback.answer(); return

    emoji = {"paid": "✅", "pending": "⏳", "cancelled": "❌", "refunded": "↩️"}
    lines = ["🧾 <b>Последние 10 заказов:</b>\n"]
    for o in orders:
        summary = (o["items_summary"] or "—")[:80]
        lines.append(
            f"{emoji.get(o['status'], '•')} #{o['id']} • "
            f"user {o['user_id']} • {summary} • {o['amount_stars']}⭐"
        )
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_back())
    await callback.answer()


# =================================================================
# PRODUCTS CRUD
# =================================================================

@router.callback_query(F.data == "admin:products")
async def cb_products_list(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    products = await db.list_products(include_inactive=True)
    text = "📦 <b>Товары</b>\n\nНажми на товар чтобы редактировать."
    await callback.message.edit_text(text, reply_markup=products_list(products))
    await callback.answer()


@router.callback_query(F.data.startswith("prod:view:"))
async def cb_product_view(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    pid = int(callback.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        await callback.answer("Товар не найден", show_alert=True); return

    text = (
        f"<b>[{p.id}] {p.title}</b>\n\n"
        f"{p.description or '—'}\n\n"
        f"💰 <b>Цена:</b> {p.price_stars} ⭐\n"
        f"📦 <b>Тип доставки:</b> {p.delivery_type}\n"
        f"Активен: {'🟢 да' if p.is_active else '⚪️ нет'}"
    )
    await callback.message.edit_text(text, reply_markup=product_manage(p.id, p.is_active))
    await callback.answer()


@router.callback_query(F.data.startswith("prod:hide:"))
async def cb_product_hide(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    pid = int(callback.data.split(":")[2])
    await db.update_product_field(pid, "is_active", False)
    await callback.answer("Скрыт")
    # refresh view
    callback.data = f"prod:view:{pid}"
    await cb_product_view(callback, db, config)


@router.callback_query(F.data.startswith("prod:show:"))
async def cb_product_show(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    pid = int(callback.data.split(":")[2])
    await db.update_product_field(pid, "is_active", True)
    await callback.answer("Возвращён в продажу")
    callback.data = f"prod:view:{pid}"
    await cb_product_view(callback, db, config)


# -------- ADD PRODUCT (FSM) --------

@router.callback_query(F.data == "prod:new")
async def cb_product_new(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    await state.set_state(AddProduct.title)
    await callback.message.edit_text(
        "➕ <b>Новый товар</b>\n\nВведи <b>название</b>:",
        reply_markup=cancel_kb("admin:back"),
    )
    await callback.answer()


@router.message(AddProduct.title)
async def add_product_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > 200:
        await message.answer("Название должно быть 1–200 символов. Попробуй ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(AddProduct.description)
    await message.answer("Теперь введи <b>описание</b> (или «-» чтобы пропустить):")


@router.message(AddProduct.description)
async def add_product_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    await state.update_data(description=desc)
    await state.set_state(AddProduct.price)
    await message.answer("Введи <b>цену в ⭐</b> (целое число, например 100):")


@router.message(AddProduct.price)
async def add_product_price(message: Message, state: FSMContext) -> None:
    try:
        price = int((message.text or "").strip())
        assert 1 <= price <= 1_000_000
    except (ValueError, AssertionError):
        await message.answer("Цена должна быть целым числом от 1 до 1 000 000. Повтори.")
        return
    await state.update_data(price=price)
    await state.set_state(AddProduct.delivery_type)
    await message.answer("Выбери <b>тип автодоставки</b>:", reply_markup=delivery_type_kb())


@router.callback_query(AddProduct.delivery_type, F.data.startswith("dtype:"))
async def add_product_dtype(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    dtype = callback.data.split(":")[1]
    await state.update_data(delivery_type=dtype)
    if dtype == "none":
        await _finalize_add_product(callback, state, db)
        return
    await state.set_state(AddProduct.delivery_content)
    hint = "текст" if dtype == "text" else "файл или фото"
    await callback.message.edit_text(
        f"Пришли <b>{hint}</b>, который будет отправлен клиенту после оплаты:",
        reply_markup=cancel_kb("admin:back"),
    )
    await callback.answer()


@router.message(AddProduct.delivery_content)
async def add_product_content(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    dtype = data.get("delivery_type")
    text_payload = None
    file_id = None

    if dtype == "text":
        if not message.text:
            await message.answer("Жду обычное текстовое сообщение."); return
        text_payload = message.text
    elif dtype == "file":
        if message.document:
            file_id = message.document.file_id
        elif message.photo:
            file_id = message.photo[-1].file_id
        else:
            await message.answer("Пришли файл (document) или фото."); return

    await state.update_data(delivery_text=text_payload, delivery_file_id=file_id)
    await _finalize_add_product(message, state, db)


async def _finalize_add_product(event, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    pid = await db.create_product(
        title=data["title"],
        description=data.get("description", ""),
        price_stars=data["price"],
        delivery_type=data.get("delivery_type", "none"),
        delivery_text=data.get("delivery_text"),
        delivery_file_id=data.get("delivery_file_id"),
    )
    await state.clear()

    text = f"✅ Товар добавлен (id #{pid}).\n\nВозврат в админку — /admin"
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=admin_back())
        await event.answer()
    else:
        await event.answer(text, reply_markup=admin_back())


@router.callback_query(F.data == "prod:cancel")
async def prod_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отменено.", reply_markup=admin_back())
    await callback.answer()


# -------- EDIT PRODUCT FIELD --------

@router.callback_query(F.data.startswith("prod:edit:"))
async def cb_product_edit(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    _, _, pid, field = callback.data.split(":", 3)
    pid = int(pid)

    if field == "delivery_type":
        await state.set_state(EditProduct.new_value)
        await state.update_data(pid=pid, field="delivery_type")
        await callback.message.edit_text(
            "Выбери новый тип доставки:", reply_markup=delivery_type_kb()
        )
        await callback.answer(); return

    if field == "delivery_content":
        # We'll expect text or file, and also toggle delivery_type accordingly.
        await state.set_state(EditProduct.new_value)
        await state.update_data(pid=pid, field="delivery_content")
        await callback.message.edit_text(
            "Пришли новый контент доставки (текст или файл/фото).",
            reply_markup=cancel_kb("admin:back"),
        )
        await callback.answer(); return

    await state.set_state(EditProduct.new_value)
    await state.update_data(pid=pid, field=field)
    pretty = {"title": "название", "description": "описание", "price_stars": "цену (число)"}.get(field, field)
    await callback.message.edit_text(
        f"Введи новое значение — <b>{pretty}</b>:", reply_markup=cancel_kb("admin:back"),
    )
    await callback.answer()


@router.callback_query(EditProduct.new_value, F.data.startswith("dtype:"))
async def edit_dtype(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    new_type = callback.data.split(":")[1]
    await db.update_product_field(data["pid"], "delivery_type", new_type)
    await state.clear()
    await callback.message.edit_text("✅ Тип доставки обновлён.", reply_markup=admin_back())
    await callback.answer()


@router.message(EditProduct.new_value)
async def edit_new_value(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    pid, field = data["pid"], data["field"]

    if field == "price_stars":
        try:
            value = int((message.text or "").strip())
            assert 1 <= value <= 1_000_000
        except Exception:
            await message.answer("Цена — целое число от 1 до 1 000 000."); return
        await db.update_product_field(pid, "price_stars", value)

    elif field == "delivery_content":
        if message.text:
            await db.update_product_field(pid, "delivery_text", message.text)
            await db.update_product_field(pid, "delivery_type", "text")
            await db.update_product_field(pid, "delivery_file_id", None)
        elif message.document or message.photo:
            fid = message.document.file_id if message.document else message.photo[-1].file_id
            await db.update_product_field(pid, "delivery_file_id", fid)
            await db.update_product_field(pid, "delivery_type", "file")
            await db.update_product_field(pid, "delivery_text", None)
        else:
            await message.answer("Жду текст или файл."); return

    else:  # title / description
        await db.update_product_field(pid, field, (message.text or "").strip())

    await state.clear()
    await message.answer("✅ Обновлено.", reply_markup=admin_back())


# =================================================================
# BROADCAST
# =================================================================

@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    await state.set_state(Broadcast.waiting_text)
    await callback.message.edit_text(
        "📣 <b>Рассылка</b>\n\n"
        "Пришли сообщение, которое разошлём всем пользователям. "
        "Поддерживается HTML.",
        reply_markup=cancel_kb("admin:back"),
    )
    await callback.answer()


@router.message(Broadcast.waiting_text)
async def broadcast_got_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пришли текстовое сообщение."); return
    await state.update_data(text=message.html_text)
    await state.set_state(Broadcast.confirm)
    preview = message.html_text[:500]
    await message.answer(
        f"Предпросмотр:\n\n{preview}\n\n<i>Отправить всем?</i>",
        reply_markup=confirm_kb("bc:go", "admin:back"),
    )


@router.callback_query(Broadcast.confirm, F.data == "bc:go")
async def broadcast_go(
    callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot
) -> None:
    data = await state.get_data()
    text = data.get("text", "")
    await state.clear()

    user_ids = await db.all_user_ids()
    await callback.message.edit_text(
        f"⏳ Рассылка идёт: 0 / {len(user_ids)}", reply_markup=None,
    )
    await callback.answer()

    delivered, failed = 0, 0
    for i, uid in enumerate(user_ids, 1):
        try:
            await bot.send_message(uid, text)
            delivered += 1
        except TelegramAPIError as e:
            logger.warning("Broadcast failed for %s: %s", uid, e)
            failed += 1
        # keep well under Telegram's 30 msg/sec limit
        await asyncio.sleep(0.05)
        if i % 25 == 0:
            try:
                await callback.message.edit_text(
                    f"⏳ Рассылка идёт: {i} / {len(user_ids)}"
                )
            except Exception:
                pass

    await bot.send_message(
        callback.from_user.id,
        f"✅ Рассылка завершена.\nДоставлено: <b>{delivered}</b>\nОшибок: <b>{failed}</b>",
        reply_markup=admin_back(),
    )


# =================================================================
# REFUND
# =================================================================

@router.callback_query(F.data == "admin:refund")
async def cb_refund_start(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer(); return
    await state.set_state(Refund.waiting_order_id)
    await callback.message.edit_text(
        "↩️ <b>Возврат средств</b>\n\nПришли <b>номер заказа</b>, который нужно вернуть:",
        reply_markup=cancel_kb("admin:back"),
    )
    await callback.answer()


@router.message(Refund.waiting_order_id)
async def refund_got_id(message: Message, state: FSMContext, db: Database) -> None:
    m = re.search(r"\d+", message.text or "")
    if not m:
        await message.answer("Ожидаю число — номер заказа."); return
    order_id = int(m.group())
    order = await db.get_order_full(order_id)
    if not order:
        await message.answer("Заказ не найден."); return
    if order["status"] != "paid":
        await message.answer(f"Нельзя вернуть — статус: {order['status']}."); return
    if not order.get("telegram_payment_charge_id"):
        await message.answer("Нет payment_charge_id — возврат невозможен."); return

    await state.update_data(order_id=order_id)
    await state.set_state(Refund.confirm)
    await message.answer(
        f"Подтверди возврат заказа <b>#{order_id}</b> на сумму "
        f"<b>{order['amount_stars']} ⭐</b> пользователю <code>{order['user_id']}</code>?",
        reply_markup=confirm_kb("rf:go", "admin:back"),
    )


@router.callback_query(Refund.confirm, F.data == "rf:go")
async def refund_go(
    callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot
) -> None:
    data = await state.get_data()
    order_id = data["order_id"]
    await state.clear()

    order = await db.get_order_full(order_id)
    if not order:
        await callback.message.edit_text("Заказ не найден.", reply_markup=admin_back())
        await callback.answer(); return

    try:
        await bot.refund_star_payment(
            user_id=order["user_id"],
            telegram_payment_charge_id=order["telegram_payment_charge_id"],
        )
    except TelegramAPIError as e:
        await callback.message.edit_text(
            f"❌ Ошибка возврата: <code>{e}</code>", reply_markup=admin_back()
        )
        await callback.answer(); return

    await db.mark_order_refunded(order_id)

    # notify user
    try:
        await bot.send_message(
            order["user_id"],
            f"↩️ По заказу #{order_id} выполнен возврат "
            f"<b>{order['amount_stars']} ⭐</b>.",
        )
    except Exception:
        pass

    await callback.message.edit_text(
        f"✅ Возврат по заказу #{order_id} выполнен.", reply_markup=admin_back(),
    )
    await callback.answer()