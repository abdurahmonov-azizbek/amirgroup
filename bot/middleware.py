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
    """
    Bot restart bo'lgandan keyin FSM state yo'qoladi.
    Bu middleware har bir xabar/callback kelganda state ni tekshiradi,
    agar None bo'lsa — foydalanuvchi roliga qarab state ni tiklaydi,
    keyin asl handleriga yo'naltiradi (swallow qilmaydi!).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Faqat Message va CallbackQuery uchun ishlaydi
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        # /start ni o'zi handle qiladi
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        state: FSMContext = data.get("state")
        if state is None:
            return await handler(event, data)

        current_state = await state.get_state()

        # State allaqachon bor — hech narsa qilma
        if current_state is not None:
            return await handler(event, data)

        # ── State None: restart bo'lgan, tiklash kerak ──
        if isinstance(event, Message):
            user_id = event.from_user.id
        else:
            user_id = event.from_user.id

        # Admin
        if user_id in settings.ADMIN_IDS:
            await state.set_state(AdminStates.main_menu)
            logger.info("Auto-restored AdminStates.main_menu for user %s", user_id)
            # State tiklandi — asl handler ishlayveradi
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

        if not user:
            return await handler(event, data)

        # Auditor
        if user.role == UserRole.auditor:
            await state.set_state(AuditorStates.main_menu)
            logger.info("Auto-restored AuditorStates.main_menu for user %s", user_id)
            return await handler(event, data)

        # Tasdiqlangan mijoz
        if user.verification_status == VerificationStatus.verified:
            await state.set_state(ClientStates.main_menu)
            logger.info("Auto-restored ClientStates.main_menu for user %s", user_id)
            return await handler(event, data)

        # Kutilmoqda yoki yangi — /start ga yo'naltirish
        if isinstance(event, Message):
            await state.set_state(RegistrationStates.waiting_for_approval)
        return await handler(event, data)
