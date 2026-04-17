"""Entry point: launch the Telegram shop bot."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from database import Database
from handlers import admin, cart, user


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("bot")

    config = load_config()
    if not config.bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example → .env and fill it in.")

    db = Database(config)
    await db.connect()
    log.info("Connected to MySQL at %s", config.db_host)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp["db"] = db
    dp["config"] = config

    # admin first so /admin and admin callbacks win priority
    dp.include_router(admin.router)
    dp.include_router(cart.router)
    dp.include_router(user.router)

    try:
        log.info("Starting polling…")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass