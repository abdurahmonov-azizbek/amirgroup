import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.fsm.context import FSMContext
from sqlalchemy.future import select

from database.models import User, VerificationStatus, UserRole
from database.session import AsyncSessionLocal
from bot.states import RegistrationStates, ClientStates, AuditorStates, AdminStates
from core.config import settings

logger = logging.getLogger(__name__)


class AutoRestoreStateMiddleware(BaseMiddleware):
    """
    If a known user sends any message while the FSM state is None
    (e.g. after a server restart), automatically restore their correct
    state and resend their main menu — so they never need to /start again.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Only apply to plain Message events
        if not isinstance(event, Message):
            return await handler(event, data)

        # Let /start pass through normally — it handles itself
        if event.text and event.text.startswith("/start"):
            return await handler(event, data)

        state: FSMContext = data.get("state")
        if state is None:
            return await handler(event, data)

        current_state = await state.get_state()

        # State is already set → normal flow, nothing to do
        if current_state is not None:
            return await handler(event, data)

        # ── State is None: user sent something after a restart ──
        user_id = event.from_user.id

        # Admin check (no DB record needed)
        if user_id in settings.ADMIN_IDS:
            from bot.keyboards import admin_main_kb
            await state.set_state(AdminStates.main_menu)
            await event.answer(
                "👑 Admin panelga xush kelibsiz! (Sessiya tiklandi)",
                reply_markup=admin_main_kb(),
            )
            logger.info("Auto-restored AdminStates.main_menu for user %s", user_id)
            return  # swallow the original message; menu is now shown

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()

        if not user:
            # Unknown user — let the original handler deal with it
            return await handler(event, data)

        # ── Route by role / verification status ──

        if user.role == UserRole.auditor:
            from bot.keyboards import auditor_main_kb
            await state.set_state(AuditorStates.main_menu)
            await event.answer(
                "🎖 Auditor menyusiga xush kelibsiz! (Sessiya tiklandi)",
                reply_markup=auditor_main_kb(),
            )
            logger.info("Auto-restored AuditorStates.main_menu for user %s", user_id)
            return

        if user.verification_status == VerificationStatus.verified:
            from bot.keyboards import client_main_kb
            await state.set_state(ClientStates.main_menu)
            await event.answer(
                "✅ Asosiy menyu: (Sessiya tiklandi)",
                reply_markup=client_main_kb(),
            )
            logger.info("Auto-restored ClientStates.main_menu for user %s", user_id)
            return

        if user.verification_status == VerificationStatus.verification_pending:
            await state.set_state(RegistrationStates.waiting_for_approval)
            await event.answer(
                "⏳ Sizning ma'lumotlaringiz ko'rib chiqilmoqda.\n"
                "Tasdiqlanganidan so'ng sizga xabar beramiz."
            )
            return

        if user.verification_status == VerificationStatus.rejected:
            await event.answer(
                "❌ Sizning arizangiz rad etildi.\n"
                "Qaytadan ro'yxatdan o'tish uchun /start ni bosing."
            )
            return

        # New / unfinished registration — nudge them to /start
        await event.answer(
            "👋 Botdan foydalanish uchun /start ni bosing."
        )
