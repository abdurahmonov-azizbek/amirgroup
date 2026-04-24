from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from sqlalchemy.future import select

from database.models import User, ReconciliationLog, ReconLogStatus, UserRole, VerificationStatus
from database.session import AsyncSessionLocal
from bot.states import ClientStates
from bot.keyboards import client_main_kb, reconciliation_action_kb, auditor_contact_kb, contact_reviewed_kb, recon_reviewed_kb
from services.api_1c import one_c
from services.config_db import get_config
from core.config import settings

router = Router()

ITEMS_PER_PAGE = 4

# ─────────────────────────────────────────────
# Holat nomini o'zbek tilida
# ─────────────────────────────────────────────
STATUS_LABELS = {
    VerificationStatus.new: "🆕 Yangi",
    VerificationStatus.verification_pending: "⏳ Ko'rib chiqilmoqda",
    VerificationStatus.verified: "✅ Tasdiqlangan",
    VerificationStatus.rejected: "❌ Rad etilgan",
}


def build_pagination_kb(prefix: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"{prefix}_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore_nav"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"{prefix}_{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[nav]) if nav else None


# ─────────────────────────────────────────────
# 💰 Mening balansim
# ─────────────────────────────────────────────
@router.message(ClientStates.main_menu, F.text == "💰 Mening balansim")
async def client_balance(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()

    if not user or not user.phone_number:
        await message.answer("❌ Sizning ma'lumotlaringiz to'liq emas.")
        return

    msg = await message.answer("⏳ Ma'lumotlar 1C bazasidan yuklanmoqda...")
    client_data = await one_c.check_user(user.phone_number)

    if not client_data or "Contracts" not in client_data:
        await msg.edit_text("❌ 1C bazasidan ma'lumot olib bo'lmadi. Keyinroq urinib ko'ring.")
        return

    full_name = f"{user.last_name or ''} {user.first_name or ''} {user.middle_name or ''}".strip()
    total_debt = sum(c.get("TotalDebt", 0) for c in client_data["Contracts"])
    total_overdue = sum(c.get("OverdueDebt", 0) for c in client_data["Contracts"])

    text = (
        f"💰 <b>Balans ma'lumotlari</b>\n\n"
        f"👤 F.I.Sh: <b>{full_name}</b>\n"
        f"🏪 Do'kon: <b>{user.market_name or '—'}</b>\n"
        f"📞 Telefon: +{user.phone_number}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💳 Umumiy qarz: <b>{total_debt:,.0f} $</b>\n"
        f"⚠️ Muddati o'tgan: <b>{total_overdue:,.0f} $</b>\n"
    )
    await msg.edit_text(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# 📄 Shartnomalarim (pagination)
# ─────────────────────────────────────────────
async def send_contracts_page(target, phone: str, page: int):
    client_data = await one_c.check_user(phone)

    if not client_data or "Contracts" not in client_data or not client_data["Contracts"]:
        text = "📄 Sizda hozircha shartnomalar mavjud emas."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)
        return

    contracts = client_data["Contracts"]
    total_pages = max(1, -(-len(contracts) // ITEMS_PER_PAGE))  # ceil division
    page = max(1, min(page, total_pages))
    chunk = contracts[(page - 1) * ITEMS_PER_PAGE: page * ITEMS_PER_PAGE]

    text = f"📄 <b>Shartnomalarim</b> ({page}/{total_pages}):\n\n"
    for i, c in enumerate(chunk, start=(page - 1) * ITEMS_PER_PAGE + 1):
        text += (
            f"🔹 <b>{i}. {c.get('Contract', '—')}</b>\n"
            f"   💳 Umumiy qarz: {c.get('TotalDebt', 0):,.0f} $\n"
            f"   ⚠️ Muddati o'tgan: {c.get('OverdueDebt', 0):,.0f} $"
            f"   ({c.get('OverdueDays', 0)} kun)\n\n"
        )

    kb = build_pagination_kb("contracts_page", page, total_pages)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(ClientStates.main_menu, F.text == "📄 Shartnomalarim")
async def client_contracts(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
    await send_contracts_page(message, user.phone_number, 1)


@router.callback_query(F.data.startswith("contracts_page_"))
async def contracts_page_cb(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one()
    await send_contracts_page(callback, user.phone_number, page)


# ─────────────────────────────────────────────
# 🕒 Xaridlar tarixi (pagination)
# ─────────────────────────────────────────────
async def send_sales_page(target, phone: str, page: int):
    client_data = await one_c.check_user(phone)

    if not client_data or "SalesHistory" not in client_data or not client_data["SalesHistory"]:
        text = "🕒 Sizda hozircha xaridlar tarixi mavjud emas."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)
        return

    sales = client_data["SalesHistory"]
    total_pages = max(1, -(-len(sales) // ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))
    chunk = sales[(page - 1) * ITEMS_PER_PAGE: page * ITEMS_PER_PAGE]

    text = f"🕒 <b>Xaridlar tarixi</b> ({page}/{total_pages}):\n\n"
    for s in chunk:
        text += (
            f"🔖 <b>{s.get('Document', '—')} №{s.get('Number', '—')}</b>\n"
            f"   📅 Sana: {s.get('Date', '—')}\n"
            f"   💵 Summa: {s.get('Amount', 0):,.0f} $\n"
            f"   📂 Shartnoma: {s.get('Contract', '—')}\n\n"
        )

    kb = build_pagination_kb("sales_page", page, total_pages)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(ClientStates.main_menu, F.text == "🕒 Xaridlar tarixi")
async def client_sales_history(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
    await send_sales_page(message, user.phone_number, 1)


@router.callback_query(F.data.startswith("sales_page_"))
async def sales_page_cb(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one()
    await send_sales_page(callback, user.phone_number, page)


# ─────────────────────────────────────────────
# 📞 Auditor bilan aloqa
# ─────────────────────────────────────────────
@router.message(ClientStates.main_menu, F.text == "📞 Auditor bilan aloqa")
async def client_contact_auditor(message: Message, state: FSMContext):
    await message.answer(
        "✍️ Auditorga murojaatingizni yozing.\n"
        "Xabaringiz ma'lumotlaringiz bilan birga guruhga yuboriladi.",
        reply_markup=auditor_contact_kb()
    )
    await state.set_state(ClientStates.waiting_for_auditor_message)


@router.message(ClientStates.waiting_for_auditor_message, F.text == "🔙 Bekor qilish")
async def cancel_auditor_contact(message: Message, state: FSMContext):
    await message.answer("❌ Bekor qilindi.", reply_markup=client_main_kb())
    await state.set_state(ClientStates.main_menu)


@router.message(ClientStates.waiting_for_auditor_message, F.text)
async def process_auditor_message(message: Message, state: FSMContext):

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()

    full_name = f"{user.last_name or ''} {user.first_name or ''} {user.middle_name or ''}".strip() if user else "Noma'lum"
    username_str = f"@{user.username}" if user and user.username else "yo'q"

    contact_text = (
        f"📩 <b>Mijozdan murojaat!</b>\n\n"
        f"👤 F.I.Sh: <b>{full_name}</b>\n"
        f"🏪 Do'kon: <b>{user.market_name or '—'}</b>\n"
        f"📞 Telefon: +{user.phone_number if user else '—'}\n"
        f"🆔 Telegram: {username_str} (ID: {user.user_id if user else '—'})\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💬 <b>Murojaat matni:</b>\n"
        f"{message.text}"
    )

    auditor_chat_id_str = await get_config("auditor_chat_id", "0")
    try:
        auditor_chat_id = int(auditor_chat_id_str)
    except ValueError:
        auditor_chat_id = 0

    if auditor_chat_id != 0:
        await message.bot.send_message(
            auditor_chat_id,
            contact_text,
            parse_mode="HTML",
            reply_markup=contact_reviewed_kb()
        )

    await message.answer(
        "✅ Murojaatingiz auditorga yuborildi!\nTez orada siz bilan bog'lanishadi.",
        reply_markup=client_main_kb()
    )
    await state.set_state(ClientStates.main_menu)


# ─────────────────────────────────────────────
# Ko'rib chiqildi / Bog'lanildi (guruhda)
# ─────────────────────────────────────────────
@router.callback_query(F.data == "contact_called")
async def contact_status_cb(callback: CallbackQuery):
    # Faqat admin yoki auditor bosa bo'ladi
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        caller = result.scalar_one_or_none()

    is_admin = callback.from_user.id in settings.ADMIN_IDS
    if not is_admin and (not caller or caller.role not in [UserRole.auditor, UserRole.admin]):
        await callback.answer("Sizda bu amalni bajarish huquqi yo'q!", show_alert=True)
        return

    action_name = callback.from_user.first_name or "Auditor"
    status_line = f"\n\n📞 Bog'lanildi — {action_name}"

    try:
        current = callback.message.text or ""
        await callback.message.edit_text(current + status_line, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass

    await callback.answer("Bajarildi!", show_alert=False)


@router.callback_query(F.data == "recon_reviewed")
async def recon_reviewed_cb(callback: CallbackQuery):
    # Faqat admin yoki auditor bosa bo'ladi
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        caller = result.scalar_one_or_none()

    is_admin = callback.from_user.id in settings.ADMIN_IDS
    if not is_admin and (not caller or caller.role not in [UserRole.auditor, UserRole.admin]):
        await callback.answer("Sizda bu amalni bajarish huquqi yo'q!", show_alert=True)
        return

    action_name = callback.from_user.first_name or "Auditor"
    status_line = f"\n\n✅ Ko'rib chiqildi — {action_name}"

    try:
        current = callback.message.text or ""
        await callback.message.edit_text(current + status_line, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass

    await callback.answer("Bajarildi!", show_alert=False)


# ─────────────────────────────────────────────
# 👤 Profilim
# ─────────────────────────────────────────────
@router.message(ClientStates.main_menu, F.text == "👤 Profilim")
async def client_profile(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()

    full_name = f"{user.last_name or ''} {user.first_name or ''} {user.middle_name or ''}".strip() or "—"
    status_label = STATUS_LABELS.get(user.verification_status, "Noma'lum")
    username_str = f"@{user.username}" if user.username else "yo'q"

    text = (
        f"👤 <b>Mening profilim</b>\n\n"
        f"📛 F.I.Sh: <b>{full_name}</b>\n"
        f"🏪 Do'kon nomi: <b>{user.market_name or '—'}</b>\n"
        f"📞 Telefon: +{user.phone_number or '—'}\n"
        f"🪪 PINFL: <code>{user.pinfl or '—'}</code>\n"
        f"🆔 Telegram: {username_str}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📋 Holati: {status_label}"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# Sverka tasdiqlash / E'tiroz
# ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("recon_confirm_"))
async def recon_confirm_cb(callback: CallbackQuery):
    recon_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ReconciliationLog)
            .join(User, ReconciliationLog.tele_user_id == User.id)
            .where(ReconciliationLog.reconciliation_id == recon_id)
            .where(User.user_id == callback.from_user.id)
        )
        log = result.scalar_one_or_none()
        if log:
            log.status = ReconLogStatus.confirmed
            await session.commit()
            await callback.message.edit_text(
                (callback.message.text or "") + "\n\n✅ Siz sverkani tasdiqladingiz.",
                reply_markup=None
            )
        else:
            await callback.answer("Xatolik. So'rov topilmadi.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("recon_disown_"))
async def recon_disown_cb(callback: CallbackQuery, state: FSMContext):
    recon_id = int(callback.data.split("_")[-1])
    await state.update_data(disown_recon_id=recon_id)
    await callback.message.answer("✍️ Qarzga e'tirozingiz sababini yozing:")
    await state.set_state(ClientStates.waiting_for_recon_disown_text)
    await callback.answer()


@router.message(ClientStates.waiting_for_recon_disown_text, F.text)
async def process_recon_disown_text(message: Message, state: FSMContext):

    data = await state.get_data()
    recon_id = data.get("disown_recon_id")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ReconciliationLog, User)
            .join(User, ReconciliationLog.tele_user_id == User.id)
            .where(ReconciliationLog.reconciliation_id == recon_id)
            .where(User.user_id == message.from_user.id)
        )
        row = result.first()
        if row:
            log, u = row
            log.status = ReconLogStatus.disowned
            log.disown_text = message.text[:500]
            await session.commit()

            # 1C dan joriy qarz ma'lumotlarini olish (hisobot uchun)
            total_debt = 0
            overdue_debt = 0
            if u.phone_number:
                client_data = await one_c.check_user(u.phone_number)
                if client_data and "Contracts" in client_data:
                    total_debt = sum(c.get("TotalDebt", 0) for c in client_data["Contracts"])
                    overdue_debt = sum(c.get("OverdueDebt", 0) for c in client_data["Contracts"])

            full_name = f"{u.last_name or ''} {u.first_name or ''} {u.middle_name or ''}".strip() or "—"
            username_str = f"@{u.username}" if u.username else "yo'q"

            objection_msg = (
                f"⚠️ <b>Sverka bo'yicha e'tiroz!</b>\n\n"
                f"👤 <b>Mijoz ma'lumotlari:</b>\n"
                f"▪️ F.I.Sh: <b>{full_name}</b>\n"
                f"▪️ Do'kon: <b>{u.market_name or '—'}</b>\n"
                f"▪️ Telefon: +{u.phone_number}\n"
                f"▪️ Telegram: {username_str} (ID: {u.user_id})\n\n"
                f"📊 <b>Sverka ma'lumotlari (1C):</b>\n"
                f"▪️ Umumiy qarz: <b>{total_debt:,.0f} $</b>\n"
                f"▪️ Muddati o'tgan: <b>{overdue_debt:,.0f} $</b>\n\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💬 <b>E'tiroz matni:</b>\n"
                f"<i>{message.text}</i>"
            )

            auditor_chat_id_str = await get_config("auditor_chat_id", "0")
            try:
                auditor_chat_id = int(auditor_chat_id_str)
                if auditor_chat_id != 0:
                    await message.bot.send_message(
                        auditor_chat_id, 
                        objection_msg, 
                        parse_mode="HTML",
                        reply_markup=recon_reviewed_kb()
                    )
            except Exception:
                pass

    await message.answer(
        "✅ E'tirozingiz qabul qilindi va auditorga yuborildi.",
        reply_markup=client_main_kb()
    )
    await state.set_state(ClientStates.main_menu)


@router.callback_query(F.data == "ignore_nav")
async def ignore_nav(callback: CallbackQuery):
    await callback.answer()
