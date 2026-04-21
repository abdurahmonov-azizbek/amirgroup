import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.config import settings
from services.api_1c import one_c
from aiogram import Bot
from database.session import AsyncSessionLocal
from database.models import User, UserRole
from sqlalchemy.future import select

async def auto_debt_alert(bot: Bot):
    """
    Automated check of 1C debts. Sends alert if overdue_days > 15.
    """
    logging.info("Running automatic debt check from 1C...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.role == UserRole.user))
        clients = result.scalars().all()
        
        for client in clients:
            if not client.phone_number or not client.user_id:
                continue
                
            data = await one_c.check_user(client.phone_number)
            if not data or 'Contracts' not in data:
                continue
                
            for c in data['Contracts']:
                overdue_days = c.get('OverdueDays', 0)
                overdue_debt = c.get('OverdueDebt', 0)
                
                if overdue_days > 15 and overdue_debt > 0:
                    try:
                        alert = (
                            f"🔔 DIQQAT!\n"
                            f"Hurmatli mijoz, {c.get('Contract')} bo'yicha qarz muddati o'tdi.\n"
                            f"Qarz miqdori: {overdue_debt:,.2f} so'm.\n"
                            f"Bloklanmaslik uchun to'lovni zudlik bilan amalga oshiring!"
                        )
                        await bot.send_message(client.user_id, alert)
                    except Exception as e:
                        logging.warning(f"Error sending auto debt alert to {client.user_id}: {e}")

def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    # Runs everyday at 10 AM (adjust timezone as needed)
    scheduler.add_job(auto_debt_alert, "cron", hour=10, args=[bot])
    scheduler.start()
