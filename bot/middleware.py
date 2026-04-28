import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.fsm.context import FSMContext
from sqlalchemy.future import select

from database.models import User, VerificationStatus, UserRole
from database.session import AsyncSessionLocal
from bot.states import RegistrationStates, ClientStates, AuditorStates, AdminStates
from core.config import settings

logger = logging.getLogger(__name__)

class AutoRestoreStateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Faqat Message va CallbackQuery uchun
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        # /start komandasi bo'lsa middleware aralashmaydi
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        state: FSMContext = data.get("state")
        if state is None:
            return await handler(event, data)

        current_state = await state.get_state()
        
        # Agar state allaqachon mavjud bo'lsa, davom etamiz
        if current_state is not None:
            return await handler(event, data)

        # State yo'q (restartdan keyin) - uni tiklashimiz kerak
        user_id = event.from_user.id

        # 1. Admin tekshiruvi
        if user_id in settings.ADMIN_IDS:
            await state.set_state(AdminStates.main_menu)
            logger.info(f"Restored Admin state for {user_id}")
            return await handler(event, data)

        # 2. Bazadan foydalanuvchini tekshirish
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

        if not user:
            return await handler(event, data)

        # 3. Roliga qarab state-ni tiklash (HECH QANDAY XABAR YUBORMASDAN)
        if user.role == UserRole.auditor:
            await state.set_state(AuditorStates.main_menu)
        elif user.verification_status == VerificationStatus.verified:
            await state.set_state(ClientStates.main_menu)
        elif user.verification_status == VerificationStatus.verification_pending:
            await state.set_state(RegistrationStates.waiting_for_approval)
        
        # State tiklandi, endi asl handler ishga tushadi va tugma bosilganini sezadi
        return await handler(event, data)
