import asyncio
import logging
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert

from database.session import AsyncSessionLocal
from database.models import User, UserRole, VerificationStatus, FSMState, UserStatus
from bot.states import AdminStates, AuditorStates, ClientStates
from core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fill_missing_states():
    logger.info("Starting to fill missing FSM states...")
    count = 0
    
    async with AsyncSessionLocal() as session:
        # Faqat faol foydalanuvchilarni olamiz
        result = await session.execute(
            select(User).where(User.status == UserStatus.active)
        )
        users = result.scalars().all()
        
        for user in users:
            target_state = None
            
            # 1. Admin tekshiruvi (config dagi IDlar orqali)
            if user.user_id in settings.ADMIN_IDS:
                target_state = AdminStates.main_menu.state
            
            # 2. Auditor roli
            elif user.role == UserRole.auditor:
                target_state = AuditorStates.main_menu.state
            
            # 3. Tasdiqlangan mijoz
            elif user.role == UserRole.user and user.verification_status == VerificationStatus.verified:
                target_state = ClientStates.main_menu.state
            
            if target_state:
                # FSMState jadvaliga yozamiz yoki yangilaymiz
                # chat_id va user_id bir xil deb hisoblaymiz (shaxsiy bot uchun)
                stmt = insert(FSMState).values(
                    user_id=user.user_id,
                    chat_id=user.user_id,
                    state=target_state,
                    data="{}"
                ).on_conflict_do_update(
                    index_elements=['user_id', 'chat_id'],
                    set_={'state': target_state}
                )
                await session.execute(stmt)
                count += 1
        
        await session.commit()
    
    logger.info(f"Successfully processed {count} users and set their states to main_menu.")

if __name__ == "__main__":
    asyncio.run(fill_missing_states())
