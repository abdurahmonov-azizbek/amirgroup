from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from sqlalchemy.future import select
from sqlalchemy import func

from database.models import User, VerificationStatus, UserRole, Config, Reconciliation, ReconciliationLog, ReconLogStatus
from database.session import AsyncSessionLocal
from bot.states import AdminStates
from bot.keyboards import admin_main_kb, admin_manage_auditors_kb, build_users_pagination_kb, cancel_inline_kb
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from services.api_1c import one_c
import pandas as pd
import io
import os
from core.config import settings
import math

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


# ─────────────────────────────────────────────
# Admin panelga kirish
# ─────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Sizda admin huquqi yo'q!")
        return

    await message.answer("Admin paneliga xush kelibsiz!", reply_markup=admin_main_kb())
    await state.set_state(AdminStates.main_menu)


# ─────────────────────────────────────────────
# Guruh ichidagi verifikatsiya tugmalari
# Bu handler state'ga bog'liq emas — guruhdan keladi
# ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("grpv_"))
async def group_verification_cb(callback: CallbackQuery):
    """
    callback_data format: grpv_accept_<user_db_id>  yoki  grpv_reject_<user_db_id>
    """
    parts = callback.data.split("_")  # ['grpv', 'accept', '12']
    if len(parts) != 3:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    action = parts[1]        # 'accept' yoki 'reject'
    target_db_id = int(parts[2])

    # Bosgan odamni tekshirish — faqat Admin yoki Auditor bo'lishi kerak
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.user_id == callback.from_user.id)
        )
        caller = result.scalar_one_or_none()

    caller_is_admin = callback.from_user.id in settings.ADMIN_IDS
    if not caller_is_admin and (not caller or caller.role not in [UserRole.auditor, UserRole.admin]):
        await callback.answer("Sizda ushbu amalni bajarish huquqi yo'q!", show_alert=True)
        return

    # Foydalanuvchini yangilash
    async with AsyncSessionLocal() as session:
        u = await session.get(User, target_db_id)
        if not u:
            await callback.answer("Foydalanuvchi bazadan topilmadi.", show_alert=True)
            return

        if u.verification_status != VerificationStatus.verification_pending:
            await callback.answer(
                f"Bu foydalanuvchi holati allaqachon o'zgartirilgan: {u.verification_status.value}",
                show_alert=True
            )
            return

        auditor_name = callback.from_user.first_name or "Auditor"

        if action == "accept":
            u.verification_status = VerificationStatus.verified
            status_line = f"✅ Tasdiqlandi — {auditor_name}"
            user_msg = (
                "✅ Tabriklaymiz! Ma'lumotlaringiz tasdiqlandi.\n\n"
                "Botdan foydalanish uchun /start ni bosing."
            )
            await session.commit()

            # Foydalanuvchiga xabar yuborish
            try:
                await callback.bot.send_message(u.user_id, user_msg)
            except Exception:
                pass

            # Guruh xabaridagi tugmalarni o'chirib, status qo'shish
            try:
                original = callback.message.text or ""
                updated_text = original + f"\n\n{status_line}"
                await callback.message.edit_text(updated_text, reply_markup=None)
            except Exception:
                pass

            await callback.answer("Mijoz tasdiqlandi!", show_alert=False)

        else:  # reject — botga yo'naltirish
            await session.close()

            bot_me = await callback.bot.get_me()
            deep_link = f"https://t.me/{bot_me.username}?start=rej_{u.id}"

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            url_kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="📝 Sababni kiritish", url=deep_link)
                ]]
            )

            # Guruh xabarining tugmalarini o'chirmaymiz — faqat accept qolsin belgisi
            try:
                original = callback.message.text or ""
                await callback.message.edit_text(
                    original + f"\n\n⏳ Rad etilmoqda... ({auditor_name})",
                    reply_markup=None
                )
            except Exception:
                pass

            # Auditorga DM yuboring
            try:
                await callback.bot.send_message(
                    callback.from_user.id,
                    f"✍️ Rad etish sababini kiriting.\n"
                    f"Sababni kiritish uchun quyidagi tugmani bosing:",
                    reply_markup=url_kb
                )
            except Exception:
                pass

            await callback.answer(
                "Sababni kiritish uchun botga o'ting (DM ga xabar yuborildi)",
                show_alert=True
            )


# ─────────────────────────────────────────────
# Umumiy statistika
# ─────────────────────────────────────────────
@router.message(AdminStates.main_menu, F.text == "📈 Umumiy statistika")
async def admin_statistics(message: Message):
    async with AsyncSessionLocal() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar()
        total_auditors = (await session.execute(
            select(func.count(User.id)).where(User.role == UserRole.auditor)
        )).scalar()
        pending = (await session.execute(
            select(func.count(User.id))
            .where(User.verification_status == VerificationStatus.verification_pending)
        )).scalar()
        verified = (await session.execute(
            select(func.count(User.id))
            .where(User.verification_status == VerificationStatus.verified)
        )).scalar()

    text = (
        "📊 Umumiy Statistika:\n\n"
        f"👥 Jami foydalanuvchilar: {total_users}\n"
        f"✅ Tasdiqlangan: {verified}\n"
        f"⏳ Kutilayotgan: {pending}\n"
        f"🎖 Auditorlar: {total_auditors}"
    )
    await message.answer(text)


# ─────────────────────────────────────────────
# Tizim sozlamalari
# ─────────────────────────────────────────────
@router.message(AdminStates.main_menu, F.text == "⚙️ Tizim sozlamalari")
async def admin_settings(message: Message, state: FSMContext):
    await state.set_state(AdminStates.main_menu)  # state ni saqlab qo'yamiz
    await show_settings(message)


async def show_settings(message_or_call):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Config))
        configs = result.scalars().all()

        if not configs:
            seeds = [
                Config(key="one_c_url",       label="1C API URL",              value="http://195.158.10.103:8081/teleline25/hs/cd/"),
                Config(key="one_c_login",     label="1C API Login",            value="Integration_API"),
                Config(key="one_c_pass",      label="1C API Parol",            value="FCKi6t1_kw"),
                Config(key="public_offer",    label="Ommaviy offerta (havola)", value="https://telegra.ph/"),
                Config(key="auditor_chat_id", label="Auditorlar chati (ID)",   value="-5102207734"),
                Config(key="data_chat_id",    label="Verifikatsiya chati (ID)", value="-5016413769"),
            ]
            session.add_all(seeds)
            await session.commit()
            result = await session.execute(select(Config))
            configs = result.scalars().all()

    text = "⚙️ Tizim sozlamalari:\n\n"
    for c in configs:
        text += f"▪️ {c.label}:\n`{c.value}`\n\n"

    btns = [
        [InlineKeyboardButton(text=f"✏️ {c.label}", callback_data=f"edit_cfg_{c.id}")]
        for c in configs
    ]

    kb = InlineKeyboardMarkup(inline_keyboard=btns)

    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message_or_call.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("edit_cfg_"))
async def edit_config_cb(callback: CallbackQuery, state: FSMContext):
    cfg_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        c = await session.get(Config, cfg_id)
        label = c.label if c else "?"
        current_val = c.value if c else ""

    await state.update_data(editing_cfg_id=cfg_id)
    await state.set_state(AdminStates.editing_config)

    await callback.message.answer(
        f"✏️ <b>{label}</b> ni tahrirlash\n\n"
        f"Joriy qiymat: <code>{current_val}</code>\n\n"
        "Yangi qiymatni yuboring:",
        reply_markup=cancel_inline_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(AdminStates.editing_config, F.data == "cancel_action")
async def cancel_config_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.main_menu)
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()
    await show_settings(callback)


@router.message(AdminStates.editing_config, F.text)
async def save_config_value(message: Message, state: FSMContext):
    data = await state.get_data()
    cfg_id = data.get("editing_cfg_id")

    async with AsyncSessionLocal() as session:
        c = await session.get(Config, cfg_id)
        if c:
            c.value = message.text.strip()
            await session.commit()
            await message.answer(
                f"✅ Saqlandi!\n\n<b>{c.label}</b>:\n<code>{c.value}</code>",
                parse_mode="HTML"
            )

    await state.set_state(AdminStates.main_menu)
    await show_settings(message)


# ─────────────────────────────────────────────
# Auditorlar boshqaruvi
# ─────────────────────────────────────────────
@router.message(AdminStates.main_menu, F.text == "👨‍💼 Auditorlar (Qo'shish/O'chirish)")
async def admin_auditors(message: Message, state: FSMContext):
    await message.answer("Boshqaruv turini tanlang:", reply_markup=admin_manage_auditors_kb())


async def render_auditors_list(message_or_call, page: int = 1):
    async with AsyncSessionLocal() as session:
        total_count = (await session.execute(
            select(func.count(User.id)).where(User.role == UserRole.auditor)
        )).scalar()
        limit = 10
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
        page = max(1, min(page, total_pages))

        auditors = (await session.execute(
            select(User).where(User.role == UserRole.auditor)
            .offset((page - 1) * limit).limit(limit)
        )).scalars().all()

    kb = build_users_pagination_kb(auditors, page, total_pages, "revoke_auditor", "admin_main_auditor_menu")
    text = "👔 Mavjud Auditorlar (O'chirish uchun ustiga bosing):" if auditors else "Hozircha auditorlar yo'q."

    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.edit_text(text, reply_markup=kb)
    else:
        await message_or_call.answer(text, reply_markup=kb)


async def render_users_list(message_or_call, page: int = 1):
    async with AsyncSessionLocal() as session:
        total_count = (await session.execute(
            select(func.count(User.id)).where(User.role == UserRole.user)
        )).scalar()
        limit = 10
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
        page = max(1, min(page, total_pages))

        users = (await session.execute(
            select(User).where(User.role == UserRole.user)
            .order_by(User.id.desc())
            .offset((page - 1) * limit).limit(limit)
        )).scalars().all()

    kb = build_users_pagination_kb(users, page, total_pages, "make_auditor", "admin_main_auditor_menu")
    text = "👤 Barcha foydalanuvchilar (Auditor qilish uchun bosing):" if users else "Hozircha foydalanuvchilar yo'q."

    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.edit_text(text, reply_markup=kb)
    else:
        await message_or_call.answer(text, reply_markup=kb)


@router.callback_query(F.data == "admin_main_auditor_menu")
async def back_to_auditor_menu(callback: CallbackQuery):
    await callback.message.edit_text("Boshqaruv turini tanlang:", reply_markup=admin_manage_auditors_kb())


@router.callback_query(F.data == "admin_list_auditors")
async def list_auditors_cb(callback: CallbackQuery):
    await render_auditors_list(callback, page=1)


@router.callback_query(F.data.startswith("page_revoke_auditor_"))
async def list_auditors_page_cb(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    await render_auditors_list(callback, page=page)


@router.callback_query(F.data == "admin_list_users")
async def list_users_cb(callback: CallbackQuery):
    await render_users_list(callback, page=1)


@router.callback_query(F.data.startswith("page_make_auditor_"))
async def list_users_page_cb(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    await render_users_list(callback, page=page)


@router.callback_query(F.data.startswith("make_auditor_"))
async def cb_make_auditor(callback: CallbackQuery):
    uid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await session.get(User, uid)
        if u:
            u.role = UserRole.auditor
            await session.commit()
            await callback.answer(f"✅ {u.first_name} auditor etib tayinlandi!", show_alert=True)
            try:
                await callback.bot.send_message(
                    u.user_id,
                    "🎖 Tabriklaymiz! Siz auditor etib tayinlandingiz.\n\n"
                    "Auditor menyusiga o'tish uchun /start ni bosing."
                )
            except Exception:
                pass
        else:
            await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
    await render_users_list(callback, page=1)


@router.callback_query(F.data.startswith("revoke_auditor_"))
async def cb_revoke_auditor(callback: CallbackQuery):
    uid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await session.get(User, uid)
        if u and u.role == UserRole.auditor:
            u.role = UserRole.user
            await session.commit()
            await callback.answer(f"🚫 {u.first_name} auditorlikdan olib tashlandi!", show_alert=True)
        else:
            await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
    await render_auditors_list(callback, page=1)


# ─────────────────────────────────────────────
# 📢 Ommaviy xabar yuborish
# ─────────────────────────────────────────────
@router.message(AdminStates.main_menu, F.text == "📢 Ommaviy xabar yuborish")
async def admin_mass_message(message: Message, state: FSMContext):
    await message.answer(
        "✍️ Mijozlarga yubormoqchi bo'lgan xabaringizni yozing:\n"
        "<i>(Matn, rasm yoki video bo'lishi mumkin)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_cancel_broadcast")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_broadcast_message)


@router.callback_query(AdminStates.waiting_for_broadcast_message, F.data == "admin_cancel_broadcast")
async def admin_cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.message.answer("Admin paneliga xush kelibsiz!", reply_markup=admin_main_kb())
    await state.set_state(AdminStates.main_menu)
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast_message)
async def admin_process_broadcast_message(message: Message, state: FSMContext):
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
        reply_markup=admin_main_kb()
    )
    await state.set_state(AdminStates.main_menu)


# ─────────────────────────────────────────────
# ⚠️ Qarzdorlarga eslatma yuborish
# ─────────────────────────────────────────────
@router.message(AdminStates.main_menu, F.text == "⚠️ Qarzdorlarga eslatma")
async def admin_debt_reminder(message: Message):
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
