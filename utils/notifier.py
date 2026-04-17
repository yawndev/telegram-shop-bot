"""Admin notification helpers."""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


async def notify_admin_new_order(
    bot: Bot,
    admin_id: int,
    *,
    order_id: int,
    user_id: int,
    username: str | None,
    product_title: str,
    amount_stars: int,
) -> None:
    """Send a formatted new-order alert to the admin."""
    username_str = f"@{username}" if username else f"id {user_id}"
    text = (
        "🆕 <b>Новый оплаченный заказ</b>\n\n"
        f"<b>Номер:</b> #{order_id}\n"
        f"<b>Клиент:</b> {username_str}\n"
        f"<b>Товар:</b> {product_title}\n"
        f"<b>Сумма:</b> {amount_stars} ⭐"
    )
    try:
        await bot.send_message(admin_id, text)
    except TelegramAPIError as e:
        logger.error("Failed to notify admin: %s", e)