"""Admin panel keyboards."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Product


def admin_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊  Статистика", callback_data="admin:stats")
    kb.button(text="🧾  Последние заказы", callback_data="admin:orders")
    kb.button(text="📦  Товары", callback_data="admin:products")
    kb.button(text="📣  Рассылка", callback_data="admin:broadcast")
    kb.button(text="↩️  Возврат средств", callback_data="admin:refund")
    kb.button(text="« Закрыть", callback_data="admin:close")
    kb.adjust(1)
    return kb.as_markup()


def admin_back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="« Назад", callback_data="admin:back")
    return kb.as_markup()


def products_list(products: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in products:
        tag = "🟢" if p.is_active else "⚪️"
        kb.button(
            text=f"{tag} [{p.id}] {p.title} — {p.price_stars}⭐",
            callback_data=f"prod:view:{p.id}",
        )
    kb.button(text="➕  Добавить товар", callback_data="prod:new")
    kb.button(text="« Назад", callback_data="admin:back")
    kb.adjust(1)
    return kb.as_markup()


def product_manage(product_id: int, is_active: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️  Название", callback_data=f"prod:edit:{product_id}:title")
    kb.button(text="✏️  Описание", callback_data=f"prod:edit:{product_id}:description")
    kb.button(text="💰  Цена", callback_data=f"prod:edit:{product_id}:price_stars")
    kb.button(text="📦  Тип доставки", callback_data=f"prod:edit:{product_id}:delivery_type")
    kb.button(text="🧩  Контент доставки", callback_data=f"prod:edit:{product_id}:delivery_content")
    if is_active:
        kb.button(text="🚫  Скрыть товар", callback_data=f"prod:hide:{product_id}")
    else:
        kb.button(text="✅  Вернуть в продажу", callback_data=f"prod:show:{product_id}")
    kb.button(text="« К списку", callback_data="admin:products")
    kb.adjust(1)
    return kb.as_markup()


def delivery_type_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Без доставки", callback_data="dtype:none")
    kb.button(text="Текст", callback_data="dtype:text")
    kb.button(text="Файл", callback_data="dtype:file")
    kb.button(text="« Отмена", callback_data="prod:cancel")
    kb.adjust(1)
    return kb.as_markup()


def confirm_kb(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅  Да", callback_data=yes_cb),
        InlineKeyboardButton(text="❌  Отмена", callback_data=no_cb),
    ]])


def cancel_kb(cb: str = "prod:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="« Отмена", callback_data=cb),
    ]])