from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from sqlalchemy.future import select

from database.models import User, Reconciliation, ReconciliationLog, UserRole, VerificationStatus, ReconLogStatus
from database.session import AsyncSessionLocal
from bot.states import AuditorStates
from bot.keyboards import auditor_main_kb, reconciliation_action_kb, auditor_statistics_inline_kb, build_reconciliation_pagination_kb
from services.api_1c import one_c
from aiogram.types import FSInputFile
from sqlalchemy import func
import math
import pandas as pd
import os

router = Router()


# ─────────────────────────────────────────────
# 📊 Statistika menyusi
# ─────────────────────────────────────────────
@router.message(AuditorStates.main_menu, F.text == "📊 Statistika")
async def auditor_statistics_menu(message: Message):
    await message.answer(
        "📊 Statistika va hisobotlar:",
        reply_markup=auditor_statistics_inline_kb()
    )


@router.callback_query(F.data.startswith("aud_stat_"))
async def process_auditor_stat(callback: CallbackQuery):
    stat_type = callback.data.split("_")[-1]

    await callback.message.edit_text("⏳ 1C bazasidan ma'lumotlar yuklanmoqda...")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User)
            .where(User.role == UserRole.user)
            .where(User.verification_status == VerificationStatus.verified)
        )
        users = result.scalars().all()

    if stat_type == "all":
        if not users:
            await callback.message.edit_text("👥 Tasdiqlangan mijozlar yo'q.")
            return
        text = f"👥 <b>Barcha tasdiqlangan mijozlar</b> ({len(users)} ta):\n\n"
        for i, u in enumerate(users, 1):
            name = u.market_name or u.first_name or "—"
            phone = f"+{u.phone_number}" if u.phone_number else "—"
            text += f"{i}. {name} | {phone}\n"
        try:
            await callback.message.edit_text(text[:4096], parse_mode="HTML")
        except Exception:
            await callback.message.answer(text[:4096], parse_mode="HTML")

    elif stat_type in ["debtors", "overdue"]:
        label = "⚠️ Qarzdorlar" if stat_type == "debtors" else "🚨 Muddati o'tgan mijozlar"
        text = f"<b>{label}:</b>\n\n"
        count = 0

        for u in users:
            if not u.phone_number:
                continue
            data = await one_c.check_user(u.phone_number)
            if not data or "Contracts" not in data:
                continue

            total_debt = sum(c.get("TotalDebt", 0) for c in data["Contracts"])
            total_overdue = sum(c.get("OverdueDebt", 0) for c in data["Contracts"])
            name = u.market_name or u.first_name or "—"

            if stat_type == "debtors" and total_debt > 0:
                text += f"▫️ {name} | Qarz: {total_debt:,.0f} $\n"
                count += 1
            elif stat_type == "overdue" and total_overdue > 0:
                text += f"▫️ {name} | Muddati o'tgan: {total_overdue:,.0f} $\n"
                count += 1

        if count == 0:
            text += "Hech kim topilmadi."

        try:
            await callback.message.edit_text(text[:4096], parse_mode="HTML")
        except Exception:
            await callback.message.answer(text[:4096], parse_mode="HTML")

    await callback.answer()


# ─────────────────────────────────────────────
# 📨 Sverka yuborish
# ─────────────────────────────────────────────
@router.message(AuditorStates.main_menu, F.text == "📨 Sverka yuborish")
async def auditor_broadcast_recon(message: Message, state: FSMContext):
    msg = await message.answer("⏳ Barcha mijozlarga sverka so'rovi yuborilmoqda...")

    async with AsyncSessionLocal() as session:
        recon = Reconciliation()
        session.add(recon)
        await session.flush()

        users_result = await session.execute(
            select(User)
            .where(User.role == UserRole.user)
            .where(User.verification_status == VerificationStatus.verified)
        )
        clients = users_result.scalars().all()

        sent_count = 0
        for client in clients:
            if not client.user_id or not client.phone_number:
                continue

            client_data = await one_c.check_user(client.phone_number)
            if not client_data or "Contracts" not in client_data:
                continue

            total_debt = sum(c.get("TotalDebt", 0) for c in client_data["Contracts"])
            overdue_debt = sum(c.get("OverdueDebt", 0) for c in client_data["Contracts"])

            text = (
                f"📋 <b>Hurmatli {client.market_name or client.first_name}!</b>\n\n"
                f"Oy yakuni bo'yicha hisob-kitob:\n\n"
                f"💳 Umumiy qarz: <b>{total_debt:,.0f} $</b>\n"
                f"⚠️ Muddati o'tgan: <b>{overdue_debt:,.0f} $</b>\n\n"
                f"Iltimos, ushbu ma'lumotni tasdiqlang yoki e'tiroz bildiring."
            )
            try:
                await message.bot.send_message(
                    client.user_id,
                    text,
                    parse_mode="HTML",
                    reply_markup=reconciliation_action_kb(recon.id)
                )
                log = ReconciliationLog(
                    reconciliation_id=recon.id,
                    tele_user_id=client.id,
                    total_debt=total_debt,
                    overdue_debt=overdue_debt
                )
                session.add(log)
                sent_count += 1
            except Exception:
                pass

        await session.commit()

    await msg.edit_text(f"✅ Sverka yuborildi! {sent_count} ta mijozga yetkazildi.")


# ─────────────────────────────────────────────
# 📢 Ommaviy xabar yuborish
# ─────────────────────────────────────────────
@router.message(AuditorStates.main_menu, F.text == "📢 Ommaviy xabar yuborish")
async def auditor_mass_message(message: Message, state: FSMContext):
    await message.answer(
        "✍️ Mijozlarga yubormoqchi bo'lgan xabaringizni yozing:\n"
        "<i>(Matn, rasm yoki video bo'lishi mumkin)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="cancel_broadcast")]]
        )
    )
    await state.set_state(AuditorStates.waiting_for_broadcast_message)


@router.callback_query(AuditorStates.waiting_for_broadcast_message, F.data == "cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.message.answer("Auditor menyusi:", reply_markup=auditor_main_kb())
    await state.set_state(AuditorStates.main_menu)
    await callback.answer()


@router.message(AuditorStates.waiting_for_broadcast_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        users_result = await session.execute(
            select(User)
            .where(User.role == UserRole.user)
            .where(User.verification_status == VerificationStatus.verified)
        )
        clients = users_result.scalars().all()

    sent_count = 0
    for client in clients:
        if client.user_id:
            try:
                await message.copy_to(client.user_id)
                sent_count += 1
            except Exception:
                pass

    await message.answer(
        f"✅ Ommaviy xabar <b>{sent_count}</b> ta mijozga yuborildi.",
        parse_mode="HTML",
        reply_markup=auditor_main_kb()
    )
    await state.set_state(AuditorStates.main_menu)


# ─────────────────────────────────────────────
# ⚠️ Qarzdorlarga eslatma yuborish
# ─────────────────────────────────────────────
@router.message(AuditorStates.main_menu, F.text == "⚠️ Qarzdorlarga eslatma")
async def auditor_debt_reminder(message: Message):
    status_msg = await message.answer("🔍 Qarzdorlar ro'yxati shakllantirilmoqda, iltimos kuting...")

    async with AsyncSessionLocal() as session:
        users_result = await session.execute(
            select(User)
            .where(User.role == UserRole.user)
            .where(User.verification_status == VerificationStatus.verified)
        )
        clients = users_result.scalars().all()

    sent_count = 0
    for client in clients:
        if not client.user_id or not client.phone_number:
            continue

        # 1C dan qarzni tekshirish
        client_data = await one_c.check_user(client.phone_number)
        if not client_data or "Contracts" not in client_data:
            continue

        total_debt = sum(c.get("TotalDebt", 0) for c in client_data["Contracts"])

        if total_debt > 0:
            reminder_text = (
                f"🔔 <b>DIQQAT!</b>\n\n"
                f"Hurmatli mijoz, sizning qarzdorligingiz mavjud.\n"
                f"Iltimos, to'lovlarni o'z vaqtida amalga oshiring."
            )
            try:
                await message.bot.send_message(client.user_id, reminder_text, parse_mode="HTML")
                sent_count += 1
            except Exception:
                pass

    await status_msg.edit_text(
        f"✅ <b>{sent_count}</b> ta qarzdor mijozga eslatma yuborildi.",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────
# 📁 Sverkalar (Excel export) - Auditor uchun
# ─────────────────────────────────────────────
@router.message(AuditorStates.main_menu, F.text == "📁 Sverkalar")
async def auditor_reconciliations(message: Message, state: FSMContext):
    await render_recon_list(message, page=1)


async def render_recon_list(message_or_call, page: int = 1):
    async with AsyncSessionLocal() as session:
        # Sverka sonini sanash
        total_count = (await session.execute(select(func.count(Reconciliation.id)))).scalar()
        limit = 10
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
        page = max(1, min(page, total_pages))

        recons = (await session.execute(
            select(Reconciliation)
            .order_by(Reconciliation.created_at.desc())
            .offset((page - 1) * limit).limit(limit)
        )).scalars().all()

    kb = build_reconciliation_pagination_kb(recons, page, total_pages)
    text = "📅 Sverka yuborilgan sanalar (Excel yuklab olish uchun bosing):" if recons else "Sverkalar tarixi topilmadi."

    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.edit_text(text, reply_markup=kb)
    else:
        await message_or_call.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("admin_recon_page_"))
async def auditor_recon_pagination(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    await render_recon_list(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_recon_export_"))
async def auditor_recon_export(callback: CallbackQuery):
    recon_id = int(callback.data.split("_")[-1])
    loading_msg = await callback.message.answer("⏳ Excel tayyorlanmoqda, iltimos kuting...")
    await callback.answer()

    async with AsyncSessionLocal() as session:
        recon = await session.get(Reconciliation, recon_id)
        if not recon:
            await loading_msg.edit_text("❌ Xatolik: Sverka topilmadi.")
            return

        result = await session.execute(
            select(ReconciliationLog, User)
            .join(User, ReconciliationLog.tele_user_id == User.id)
            .where(ReconciliationLog.reconciliation_id == recon_id)
        )
        rows = result.all()

        if not rows:
            await loading_msg.edit_text("📭 Ushbu sverka bo'yicha ma'lumotlar topilmadi.")
            return

        data = []
        status_map = {
            ReconLogStatus.sent: "Kutilmoqda",
            ReconLogStatus.confirmed: "Tasdiqlangan",
            ReconLogStatus.disowned: "E'tiroz bildirilgan",
            ReconLogStatus.failed: "Xatolik"
        }

        for log, user in rows:
            data.append({
                "Do'kon nomi": user.market_name or "—",
                "Telefon": f"+{user.phone_number}" if user.phone_number else "—",
                "Umumiy qarz": log.total_debt,
                "Muddati o'tgan qarz": log.overdue_debt,
                "Holati": status_map.get(log.status, "Noma'lum"),
                "E'tiroz matni": log.disown_text or "—",
                "Sana": log.created_at.strftime("%d.%m.%Y %H:%M") if log.created_at else "—"
            })

        df = pd.DataFrame(data)
        date_str = recon.created_at.strftime("%Y-%m-%d_%H-%M")
        filename = f"Sverka_{date_str}.xlsx"
        filepath = os.path.join("media", filename)
        os.makedirs("media", exist_ok=True)
        df.to_excel(filepath, index=False, engine='openpyxl')

        try:
            await callback.message.answer_document(
                FSInputFile(filepath),
                caption=f"📅 {date_str} dagi sverka hisoboti"
            )
            await loading_msg.delete()
        except Exception as e:
            await loading_msg.edit_text(f"❌ Fayl yuborishda xatolik: {str(e)}")
        
    await callback.answer()


# ══════════════════════════════════════════════════════════════
# 🔍  QIDIRUV — keyword bo'yicha (ID / telefon / ism / familiya)
# ══════════════════════════════════════════════════════════════

PAGE_SIZE = 5       # Natijalar ro'yhatida bir sahifada nechta user
SUB_PAGE_SIZE = 3   # Shartnomalar / Qarzlar sahifasida nechta element


# ── Yordamchi: Qidiruv natijalari ro'yhati klaviaturasi ──────
def _build_search_kb(users_page: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    for u in users_page:
        full = f"{u.last_name or ''} {u.first_name or ''}".strip() or u.market_name or f"ID:{u.id}"
        phone = f" | +{u.phone_number}" if u.phone_number else ""
        buttons.append([InlineKeyboardButton(
            text=f"👤 {full}{phone}",
            callback_data=f"srch_open_{u.id}"
        )])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"srch_list_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"srch_list_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Yordamchi: User detail klaviaturasi ─────────────────────
def _build_user_detail_kb(user_db_id: int, list_page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 Shartnomalar", callback_data=f"srch_contracts_{user_db_id}_1"),
            InlineKeyboardButton(text="💰 Qarzlar",      callback_data=f"srch_debts_{user_db_id}_1"),
        ],
        [InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data=f"srch_list_{list_page}")],
    ])


# ── Yordamchi: Sub-list (Shartnomalar/Qarzlar) klaviaturasi ──
def _build_sub_kb(prefix: str, user_db_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"srch_{prefix}_{user_db_id}_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"srch_{prefix}_{user_db_id}_{page + 1}"))

    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(
        text="🔙 Foydalanuvchiga qaytish",
        callback_data=f"srch_open_{user_db_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Yordamchi: DB qidiruv ────────────────────────────────────
async def _do_search(keyword: str) -> list:
    kw = keyword.strip().lower()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.role == UserRole.user))
        all_users = result.scalars().all()

    matched = []
    for u in all_users:
        haystack = " ".join(filter(None, [
            str(u.id),
            u.phone_number or "",
            u.first_name or "",
            u.last_name or "",
            u.middle_name or "",
            u.market_name or "",
            u.username or "",
        ])).lower()
        if kw in haystack:
            matched.append(u)
    return matched


async def _get_user_by_id(uid: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == uid))
        return result.scalar_one_or_none()


def _user_detail_text(u: User, one_c_data: dict | None) -> str:
    full = f"{u.last_name or ''} {u.first_name or ''} {u.middle_name or ''}".strip() or "—"
    phone = f"+{u.phone_number}" if u.phone_number else "—"
    status_map = {
        "verified": "✅ Tasdiqlangan",
        "new": "🆕 Yangi",
        "verification_pending": "⏳ Kutilmoqda",
        "rejected": "❌ Rad etilgan",
    }
    vstatus = status_map.get(u.verification_status.value if u.verification_status else "", "—")

    text = (
        f"👤 <b>Foydalanuvchi ma'lumotlari</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: <code>{u.id}</code>\n"
        f"👤 F.I.Sh: <b>{full}</b>\n"
        f"🏪 Do'kon: <b>{u.market_name or '—'}</b>\n"
        f"📞 Telefon: <b>{phone}</b>\n"
        f"🔖 Username: @{u.username or '—'}\n"
        f"📋 Status: {vstatus}\n"
    )
    if one_c_data:
        total_debt = sum(c.get("TotalDebt", 0) for c in one_c_data.get("Contracts", []))
        overdue = sum(c.get("OverdueDebt", 0) for c in one_c_data.get("Contracts", []))
        text += (
            f"━━━━━━━━━━━━━━━━\n"
            f"💳 Umumiy qarz: <b>{total_debt:,.0f} $</b>\n"
            f"⚠️ Muddati o'tgan: <b>{overdue:,.0f} $</b>\n"
            f"📄 Shartnomalar soni: <b>{len(one_c_data.get('Contracts', []))}</b>\n"
        )
    return text


# ── 1. Qidiruv boshlash ──────────────────────────────────────
@router.message(AuditorStates.main_menu, F.text == "🔍 Qidiruv")
async def auditor_search_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AuditorStates.waiting_for_search_query)
    await message.answer(
        "🔍 <b>Mijoz qidirish</b>\n\n"
        "Quyidagilardan birini kiriting:\n"
        "  • <b>ID</b> (raqam)\n"
        "  • <b>Telefon raqami</b> (masalan: 998901234567)\n"
        "  • <b>Ism yoki familiya</b> (yoki bir qismi)\n"
        "  • <b>Do'kon nomi</b>\n\n"
        "<i>Masalan: «A» — ismida A harfi bo'lgan barcha mijozlar</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="srch_cancel")]]
        )
    )


# ── 2. Bekor qilish ──────────────────────────────────────────
@router.callback_query(F.data == "srch_cancel")
async def search_cancel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuditorStates.main_menu)
    await callback.message.edit_text("❌ Qidiruv bekor qilindi.")
    await callback.message.answer("Auditor menyusi:", reply_markup=auditor_main_kb())
    await callback.answer()


# ── 3. Keyword qabul qilish va qidirish ─────────────────────
@router.message(AuditorStates.waiting_for_search_query, F.text)
async def process_search_query(message: Message, state: FSMContext):
    keyword = message.text.strip()
    if not keyword:
        await message.answer("⚠️ Iltimos, qidiruv so'rovini kiriting.")
        return

    msg = await message.answer("⏳ Qidirilmoqda...")
    found = await _do_search(keyword)

    if not found:
        await msg.edit_text(
            f"❌ <b>«{keyword}»</b> bo'yicha hech kim topilmadi.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔄 Qayta qidirish", callback_data="srch_retry")]]
            )
        )
        await state.update_data(keyword=keyword, found_ids=[], current_list_page=1)
        await state.set_state(AuditorStates.viewing_search_results)
        return

    found_ids = [u.id for u in found]
    total_pages = max(1, -(-len(found) // PAGE_SIZE))  # ceiling division

    await state.update_data(keyword=keyword, found_ids=found_ids, current_list_page=1)
    await state.set_state(AuditorStates.viewing_search_results)

    await msg.edit_text(
        f"🔍 <b>«{keyword}»</b> bo'yicha <b>{len(found)}</b> ta mijoz topildi:",
        parse_mode="HTML",
        reply_markup=_build_search_kb(found[:PAGE_SIZE], 1, total_pages)
    )


# ── 4. Qayta qidirish ────────────────────────────────────────
@router.callback_query(F.data == "srch_retry")
async def search_retry(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuditorStates.waiting_for_search_query)
    await callback.message.edit_text(
        "🔍 Qidiruv so'rovini qayta kiriting:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="srch_cancel")]]
        )
    )
    await callback.answer()


# ── 5. Ro'yhat sahifasini almashtirish (barcha sub-holatlardan) ──
@router.callback_query(AuditorStates.viewing_search_results, F.data.startswith("srch_list_"))
@router.callback_query(AuditorStates.viewing_user_detail,    F.data.startswith("srch_list_"))
@router.callback_query(AuditorStates.viewing_user_contracts, F.data.startswith("srch_list_"))
@router.callback_query(AuditorStates.viewing_user_sales,     F.data.startswith("srch_list_"))
async def search_list_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    data = await state.get_data()
    found_ids = data.get("found_ids", [])
    keyword = data.get("keyword", "")

    if not found_ids:
        await callback.answer("Natijalar topilmadi.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id.in_(found_ids)))
        by_id = {u.id: u for u in result.scalars().all()}

    ordered = [by_id[uid] for uid in found_ids if uid in by_id]
    total_pages = max(1, -(-len(ordered) // PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    page_users = ordered[start: start + PAGE_SIZE]

    await state.update_data(current_list_page=page)
    await state.set_state(AuditorStates.viewing_search_results)

    await callback.message.edit_text(
        f"🔍 <b>«{keyword}»</b> bo'yicha <b>{len(ordered)}</b> ta mijoz topildi:",
        parse_mode="HTML",
        reply_markup=_build_search_kb(page_users, page, total_pages)
    )
    await callback.answer()


# ── 6. User detail ko'rish ───────────────────────────────────
@router.callback_query(F.data.startswith("srch_open_"))
async def search_open_user(callback: CallbackQuery, state: FSMContext):
    user_db_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    list_page = data.get("current_list_page", 1)

    u = await _get_user_by_id(user_db_id)
    if not u:
        await callback.answer("Foydalanuvchi topilmadi!", show_alert=True)
        return

    one_c_data = None
    if u.phone_number:
        one_c_data = await one_c.check_user(u.phone_number)

    await state.update_data(viewing_user_id=user_db_id)
    await state.set_state(AuditorStates.viewing_user_detail)

    await callback.message.edit_text(
        _user_detail_text(u, one_c_data),
        parse_mode="HTML",
        reply_markup=_build_user_detail_kb(user_db_id, list_page)
    )
    await callback.answer()


# ── 7. Shartnomalar sahifasi ─────────────────────────────────
@router.callback_query(F.data.startswith("srch_contracts_"))
async def search_contracts(callback: CallbackQuery, state: FSMContext):
    # callback_data format: srch_contracts_<user_db_id>_<page>
    parts = callback.data.split("_")
    user_db_id = int(parts[2])
    page = int(parts[3])

    u = await _get_user_by_id(user_db_id)
    if not u or not u.phone_number:
        await callback.answer("Ma'lumot topilmadi!", show_alert=True)
        return

    one_c_data = await one_c.check_user(u.phone_number)
    contracts = (one_c_data or {}).get("Contracts", [])

    if not contracts:
        await callback.answer("Shartnomalar mavjud emas.", show_alert=True)
        return

    total_pages = max(1, -(-len(contracts) // SUB_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    chunk = contracts[(page - 1) * SUB_PAGE_SIZE: page * SUB_PAGE_SIZE]

    full = f"{u.last_name or ''} {u.first_name or ''}".strip() or u.market_name or f"ID:{u.id}"
    text = f"📄 <b>{full} — Shartnomalar</b> ({page}/{total_pages}):\n━━━━━━━━━━━━━━━━\n"
    for c in chunk:
        debt = c.get("TotalDebt", 0)
        overdue = c.get("OverdueDebt", 0)
        days = c.get("OverdueDays", 0)
        line = (
            f"\n🔹 <b>{c.get('Contract', '—')}</b>\n"
            f"   💳 Qarz: <b>{debt:,.0f} $</b>\n"
            f"   ⚠️ Muddati o'tgan: <b>{overdue:,.0f} $</b>"
        )
        if days:
            line += f" ({days} kun)"
        text += line + "\n"

    await state.set_state(AuditorStates.viewing_user_contracts)
    await callback.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=_build_sub_kb("contracts", user_db_id, page, total_pages)
    )
    await callback.answer()


# ── 8. Qarzlar sahifasi ──────────────────────────────────────
@router.callback_query(F.data.startswith("srch_debts_"))
async def search_debts(callback: CallbackQuery, state: FSMContext):
    # callback_data format: srch_debts_<user_db_id>_<page>
    parts = callback.data.split("_")
    user_db_id = int(parts[2])
    page = int(parts[3])

    u = await _get_user_by_id(user_db_id)
    if not u or not u.phone_number:
        await callback.answer("Ma'lumot topilmadi!", show_alert=True)
        return

    one_c_data = await one_c.check_user(u.phone_number)
    contracts = (one_c_data or {}).get("Contracts", [])
    debts = [c for c in contracts if c.get("TotalDebt", 0) > 0 or c.get("OverdueDebt", 0) > 0]

    if not debts:
        await callback.answer("Qarzlar mavjud emas ✅", show_alert=True)
        return

    total_pages = max(1, -(-len(debts) // SUB_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    chunk = debts[(page - 1) * SUB_PAGE_SIZE: page * SUB_PAGE_SIZE]

    full = f"{u.last_name or ''} {u.first_name or ''}".strip() or u.market_name or f"ID:{u.id}"
    text = f"💰 <b>{full} — Qarzlar</b> ({page}/{total_pages}):\n━━━━━━━━━━━━━━━━\n"
    for c in chunk:
        debt = c.get("TotalDebt", 0)
        overdue = c.get("OverdueDebt", 0)
        days = c.get("OverdueDays", 0)
        line = (
            f"\n🔸 <b>{c.get('Contract', '—')}</b>\n"
            f"   💳 Umumiy qarz: <b>{debt:,.0f} $</b>\n"
            f"   ⚠️ Muddati o'tgan: <b>{overdue:,.0f} $</b>"
        )
        if days:
            line += f" ({days} kun)"
        text += line + "\n"

    await state.set_state(AuditorStates.viewing_user_sales)
    await callback.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=_build_sub_kb("debts", user_db_id, page, total_pages)
    )
    await callback.answer()
