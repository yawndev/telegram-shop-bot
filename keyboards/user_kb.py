"""Inline keyboards for user-facing flows."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import CartLine, Product


def main_menu(cart_count: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍  Каталог", callback_data="catalog")
    cart_label = "🧺  Корзина" + (f" ({cart_count})" if cart_count else "")
    kb.button(text=cart_label, callback_data="cart")
    kb.button(text="📦  Мои заказы", callback_data="my_orders")
    kb.button(text="👥  Рефералы", callback_data="referrals")
    kb.button(text="ℹ️  О сервисе", callback_data="about")
    kb.adjust(1)
    return kb.as_markup()


def catalog_keyboard(products: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in products:
        kb.button(
            text=f"{p.title} — {p.price_stars} ⭐",
            callback_data=f"product:{p.id}",
        )
    kb.button(text="« Назад", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


def product_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳  Купить сразу", callback_data=f"buy:{product_id}")
    kb.button(text="➕  В корзину", callback_data=f"cart_add:{product_id}")
    kb.button(text="« К каталогу", callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


def cart_keyboard(lines: list[CartLine]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for l in lines:
        kb.row(
            InlineKeyboardButton(text="➖", callback_data=f"cart_dec:{l.product_id}"),
            InlineKeyboardButton(
                text=f"{l.title} ×{l.quantity}",
                callback_data="noop",
            ),
            InlineKeyboardButton(text="➕", callback_data=f"cart_add:{l.product_id}"),
            InlineKeyboardButton(text="❌", callback_data=f"cart_rm:{l.product_id}"),
        )
    if lines:
        kb.row(InlineKeyboardButton(text="💳  Оформить заказ", callback_data="cart_checkout"))
        kb.row(InlineKeyboardButton(text="🗑  Очистить", callback_data="cart_clear"))
    kb.row(InlineKeyboardButton(text="« В меню", callback_data="home"))
    return kb.as_markup()


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« В меню", callback_data="home")]]
    )