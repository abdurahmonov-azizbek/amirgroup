import asyncio
import logging
from aiogram import Bot, Dispatcher
from core.config import settings
from bot.handlers import registration, client, auditor, admin
from bot.scheduler import setup_scheduler
from database.storage import SQLAlchemyStorage
from fill_fsm_states import fill_missing_states

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=settings.TELEGRAM_TOKEN)
    
    # Bazada saqlanadigan storage (restartdan qo'rqmaydi)
    storage = SQLAlchemyStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(registration.router)
    dp.include_router(client.router)
    dp.include_router(auditor.router)
    dp.include_router(admin.router)

    # Middleware endi shart emas, chunki statelar o'chib ketmaydi
    logging.info("Starting task schedules...")
    setup_scheduler(bot)

    # Restartdan keyin barcha foydalanuvchilar state'ini tiklash
    try:
        await fill_missing_states()
    except Exception as e:
        logging.error(f"Error filling states: {e}")

    logging.info("Bot is starting with Persistent Storage...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
