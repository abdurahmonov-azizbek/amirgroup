import asyncio
import logging
from aiogram import Bot, Dispatcher
from core.config import settings
from bot.handlers import registration, client, auditor, admin
from bot.scheduler import setup_scheduler
from bot.middleware import AutoRestoreStateMiddleware


logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=settings.TELEGRAM_TOKEN)
    dp = Dispatcher()


    dp.include_router(registration.router)
    dp.include_router(client.router)
    dp.include_router(auditor.router)
    dp.include_router(admin.router)

    # Restart dan keyin state tiklash (outer = routing DAN OLDIN ishlaydi)
    dp.message.outer_middleware(AutoRestoreStateMiddleware())
    dp.callback_query.outer_middleware(AutoRestoreStateMiddleware())

    logging.info("Starting task schedules...")
    setup_scheduler(bot)

    logging.info("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
