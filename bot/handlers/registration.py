import logging
import os
from aiogram import Router, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext

from sqlalchemy.future import select

from database.models import User, VerificationStatus, UserRole
from database.session import AsyncSessionLocal
from bot.states import RegistrationStates, ClientStates, AuditorStates, AdminStates
from bot.keyboards import offer_kb, phone_request_kb, client_main_kb, auditor_main_kb, cancel_inline_kb, regions_kb
from services.api_1c import one_c
from services.config_db import get_config
from core.config import settings

router = Router()

os.makedirs("media", exist_ok=True)


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


# ─────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    # Deep link rejection flow — masalan: /start rej_12
    start_arg = command.args or ""
    if start_arg.startswith("rej_"):
        await handle_rejection_start(message, state, start_arg)
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                verification_status=VerificationStatus.new
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

    # Admin
    if is_admin(user.user_id):
        from bot.keyboards import admin_main_kb
        from bot.states import AdminStates
        await message.answer("👑 Admin panelga xush kelibsiz!", reply_markup=admin_main_kb())
        await state.set_state(AdminStates.main_menu)
        return

    # Auditor
    if user.role == UserRole.auditor:
        await message.answer("🎖 Auditor menyusiga xush kelibsiz!", reply_markup=auditor_main_kb())
        await state.set_state(AuditorStates.main_menu)
        return

    # Tasdiqlangan mijoz
    if user.verification_status == VerificationStatus.verified:
        await message.answer("✅ Asosiy menyu:", reply_markup=client_main_kb())
        await state.set_state(ClientStates.main_menu)
        return

    # Kutilmoqda
    if user.verification_status == VerificationStatus.verification_pending:
        await message.answer(
            "⏳ Sizning ma'lumotlaringiz ko'rib chiqilmoqda.\n"
            "Tasdiqlanganidan so'ng sizga xabar beramiz."
        )
        return

    # Rad etilgan
    if user.verification_status == VerificationStatus.rejected:
        await message.answer(
            "❌ Sizning arizangiz rad etildi.\n"
            "Qo'shimcha ma'lumot uchun auditorga murojaat qiling."
        )
        return

    # Yangi foydalanuvchi — Offer ko'rsatish
    public_offer_url = await get_config("public_offer", "")
    await message.answer(
        f"👋 Xush kelibsiz!\n\n"
        f"Botdan foydalanish uchun ommaviy ofertani qabul qilishingiz kerak.\n\n"
        f"📄 Oferta: {public_offer_url}",
        reply_markup=offer_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_offer)


# ─────────────────────────────────────────────
# Oferta qabul
# ─────────────────────────────────────────────
@router.callback_query(RegistrationStates.waiting_for_offer, F.data == "offer_accepted")
async def offer_accepted_cb(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Phone request button only works in private chats
    if callback.message.chat.type != "private":
        # Send DM to user instead
        await callback.bot.send_message(
            callback.from_user.id,
            "📞 Telefon raqamingizni yuboring:",
            reply_markup=phone_request_kb()
        )
        await callback.answer("📱 Telefon raqamini yuborish uchun botga DM ni oching", show_alert=False)
    else:
        await callback.message.answer(
            "📞 Telefon raqamingizni yuboring:",
            reply_markup=phone_request_kb()
        )
        await callback.answer()
    
    await state.set_state(RegistrationStates.waiting_for_phone)


# ─────────────────────────────────────────────
# Telefon raqam
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text

    phone = phone.replace("+", "").replace(" ", "").replace("-", "").strip()

    await message.answer("🔍 1C bazasidan tekshirilmoqda, iltimos kuting...")

    client_data = await one_c.check_user(phone)

    if not client_data or "error" in client_data:
        await message.answer(
            "❌ Bu raqam tizimda topilmadi.\n\n"
            "Iltimos, to'g'ri raqam kiriting yoki auditorga murojaat qiling."
        )
        return

    # 1C dan olingan ma'lumotlarni FSM ga saqlaymiz
    client_name = client_data.get("ClientName", "")
    tax_id = client_data.get("TaxID", "")

    # Bazaga telefon raqamni yozamiz
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.phone_number = phone
        await session.commit()

    await state.update_data(
        phone=phone,
        one_c_client_name=client_name,
        one_c_tax_id=tax_id,
    )

    await message.answer(
        f"✅ Raqam tasdiqlandi!\n"
        f"1C dan topilgan mijoz: <b>{client_name}</b>\n\n"
        f"🏪 Do'kon nomini kiriting\n"
        f"<i>(1C dan: {client_name})</i>",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_market_name)


# ─────────────────────────────────────────────
# Do'kon nomi
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_market_name, F.text)
async def process_market_name(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.market_name = message.text.strip()
        await session.commit()

    await message.answer("📍 Viloyatingizni tanlang:", reply_markup=regions_kb())
    await state.set_state(RegistrationStates.waiting_for_region)


# ─────────────────────────────────────────────
# Viloyat
# ─────────────────────────────────────────────
@router.callback_query(RegistrationStates.waiting_for_region, F.data.startswith("reg_"))
async def process_region(callback: CallbackQuery, state: FSMContext):
    region = callback.data.replace("reg_", "")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one()
        user.region = region
        await session.commit()

    await callback.message.edit_text(f"📍 Viloyat: <b>{region}</b>", parse_mode="HTML")
    await callback.message.answer("👤 Ismingizni kiriting:")
    await state.set_state(RegistrationStates.waiting_for_first_name)
    await callback.answer()


# ─────────────────────────────────────────────
# Ism (First name)
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_first_name, F.text)
async def process_first_name(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.first_name = message.text.strip()
        await session.commit()

    await message.answer("👤 Familiyangizni kiriting:")
    await state.set_state(RegistrationStates.waiting_for_last_name)


# ─────────────────────────────────────────────
# Familiya (Last name)
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_last_name, F.text)
async def process_last_name(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.last_name = message.text.strip()
        await session.commit()

    await message.answer("👤 Sharifingizni kiriting (Otasining ismi):")
    await state.set_state(RegistrationStates.waiting_for_middle_name)


# ─────────────────────────────────────────────
# Otasining ismi (Middle name)
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_middle_name, F.text)
async def process_middle_name(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.middle_name = message.text.strip()
        await session.commit()


    await message.answer(
        f"🪪 PINFL raqamingizni kiriting:\n",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_pinfl)


# ─────────────────────────────────────────────
# PINFL
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_pinfl, F.text)
async def process_pinfl(message: Message, state: FSMContext):
    pinfl = message.text.strip()

    if not pinfl.isdigit() or len(pinfl) != 14:
        await message.answer(
            "❌ PINFL noto'g'ri formatda! 14 ta raqamdan iborat bo'lishi kerak.\n"
            "Iltimos qaytadan kiriting:"
        )
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.pinfl = pinfl
        await session.commit()

    await message.answer(
        "📷 Pasportingizning <b>old tomonini</b> (birinchi sahifasini) rasmga olib yuboring:",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_passport_front)


# ─────────────────────────────────────────────
# Passport old tomoni
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_passport_front, F.photo)
async def process_passport_front(message: Message, state: FSMContext):
    photo = message.photo[-1]
    file_info = await message.bot.get_file(photo.file_id)
    file_path = f"media/{message.from_user.id}_passport_front.jpg"
    await message.bot.download_file(file_info.file_path, file_path)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.passport_front_side = file_path
        await session.commit()

    await message.answer(
        "📷 Pasportingizning <b>orqa tomonini</b> (propiska sahifasini) rasmga olib yuboring:",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_passport_back)


# ─────────────────────────────────────────────
# Passport orqa tomoni
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_passport_back, F.photo)
async def process_passport_back(message: Message, state: FSMContext):
    photo = message.photo[-1]
    file_info = await message.bot.get_file(photo.file_id)
    file_path = f"media/{message.from_user.id}_passport_back.jpg"
    await message.bot.download_file(file_info.file_path, file_path)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.passport_back_side = file_path
        await session.commit()

    await message.answer(
        "🤳 Yuzingiz aniq ko'ringan <b>selfie</b> rasmingizni yuboring:"
        "\n<i>(Pasportingiz bilan birgalikda suratga tushsangiz ham bo'ladi)</i>",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_selfie)


# ─────────────────────────────────────────────
# Selfie → Guruhga yuborish
# ─────────────────────────────────────────────
@router.message(RegistrationStates.waiting_for_selfie, F.photo)
async def process_selfie(message: Message, state: FSMContext):
    from aiogram.utils.media_group import MediaGroupBuilder
    from aiogram.types import FSInputFile
    from bot.keyboards import verify_action_kb

    photo = message.photo[-1]
    file_info = await message.bot.get_file(photo.file_id)
    file_path = f"media/{message.from_user.id}_selfie.jpg"
    await message.bot.download_file(file_info.file_path, file_path)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one()
        user.selfie_photo = file_path
        user.verification_status = VerificationStatus.verification_pending
        await session.commit()
        await session.refresh(user)

    username_str = f"@{user.username}" if user.username else "yo'q"

    # Guruhga yuboriladigan xabar matni
    group_text = (
        f"🔔 Yangi verifikatsiya so'rovi!\n\n"
        f"🏪 Do'kon: {user.market_name}\n"
        f"📍 Viloyat: {user.region or '—'}\n"
        f"👤 F.I.Sh: {user.last_name} {user.first_name} {user.middle_name or ''}\n"
        f"📞 Telefon: +{user.phone_number}\n"
        f"🪪 PINFL: {user.pinfl}\n"
        f"🆔 Telegram: {username_str} (ID: {user.user_id})\n\n"
        f"Iltimos, hujjatlarni tekshiring va tasdiqlang."
    )

    # Rasmlarni guruhga yuborish
    data_chat_id_str = await get_config("data_chat_id", "0")
    try:
        data_chat_id = int(data_chat_id_str)
    except ValueError:
        data_chat_id = 0

    if data_chat_id != 0:
        try:
            media = MediaGroupBuilder(caption=f"📸 {user.market_name} — hujjatlar")
            media.add_photo(FSInputFile(user.passport_front_side))
            media.add_photo(FSInputFile(user.passport_back_side))
            media.add_photo(FSInputFile(user.selfie_photo))
            await message.bot.send_media_group(chat_id=data_chat_id, media=media.build())
        except Exception as e:
            print(f"Guruhga rasm yuborishda xato: {e}")

        try:
            # Rad etish uchun deeplink yaratish
            bot_me = await message.bot.get_me()
            deep_link = f"https://t.me/{bot_me.username}?start=rej_{user.id}"
            
            # Keyboard: Qabul - oddiy callback, Rad etish - deeplink
            verification_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"grpv_accept_{user.id}"),
                        InlineKeyboardButton(text="❌ Bekor qilish", url=deep_link)
                    ]
                ]
            )
            
            msg = await message.bot.send_message(
                chat_id=data_chat_id,
                text=group_text,
                reply_markup=verification_kb
            )
            
            # Message_id va chat_id ni saqlash (rad etishda kerak bo'ladi)
            async with AsyncSessionLocal() as session:
                u = await session.get(User, user.id)
                if u:
                    u.verification_group_message_id = msg.message_id
                    u.verification_group_chat_id = data_chat_id
                    await session.commit()
        except Exception as e:
            print(f"Guruhga xabar yuborishda xato: {e}")
    else:
        print("OGOHLANTIRISH: data_chat_id konfiguratsiyada topilmadi yoki nol!")

    await message.answer(
        "✅ Barcha ma'lumotlar qabul qilindi!\n\n"
        "📋 Ma'lumotlaringiz auditorlar tomonidan ko'rib chiqilmoqda.\n"
        "Tasdiqlangandan so'ng sizga xabar yuboramiz. 🙏"
    )
    await state.set_state(RegistrationStates.waiting_for_approval)


# ─────────────────────────────────────────────
# Rad etish oqimi (deep link orqali)
# ─────────────────────────────────────────────
async def handle_rejection_start(message: Message, state: FSMContext, arg: str):
    # Faqat admin yoki auditor bo'lishi kerak
    is_adm = message.from_user.id in settings.ADMIN_IDS
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.user_id == message.from_user.id)
        )
        caller = result.scalar_one_or_none()

    if not is_adm and (not caller or caller.role not in [UserRole.auditor, UserRole.admin]):
        await message.answer("❌ Sizda bu amalni bajarish huquqi yo'q!")
        return

    # arg = "rej_12" formatida keladi
    try:
        target_db_id = int(arg.split("_")[1])
    except (IndexError, ValueError):
        await message.answer("❌ Noto'g'ri havola.")
        return

    # Tekshiramiz — user bazada bormi
    async with AsyncSessionLocal() as session:
        target_user = await session.get(User, target_db_id)

    if not target_user:
        await message.answer("❌ Foydalanuvchi allaqachon o'chirilgan yoki topilmadi.")
        return

    if target_user.verification_status != VerificationStatus.verification_pending:
        await message.answer(
            f"⚠️ Bu foydalanuvchi holati allaqachon o'zgartirilgan: "
            f"{target_user.verification_status.value}"
        )
        return

    await state.update_data(rejecting_user_db_id=target_db_id)
    await state.set_state(AdminStates.waiting_for_rejection_reason)

    await message.answer(
        f"🗑 <b>{target_user.market_name or target_user.first_name}</b> "
        f"ro'yxatdan o'tish arizasini rad etmoqchisiz.\n\n"
        f"✍️ Rad etish sababini yozing:\n"
        f"<i>(Masalan: Pasport rasmi noto'g'ri, PINFL mos kelmadi va h.k)</i>",
        parse_mode="HTML",
        reply_markup=cancel_inline_kb()
    )


@router.callback_query(AdminStates.waiting_for_rejection_reason, F.data == "cancel_action")
async def cancel_rejection(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Rad etish bekor qilindi.")
    await state.clear()
    await callback.answer()


@router.message(AdminStates.waiting_for_rejection_reason, F.text)
async def process_rejection_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    target_db_id = data.get("rejecting_user_db_id")
    reason = message.text.strip()

    async with AsyncSessionLocal() as session:
        target_user = await session.get(User, target_db_id)
        if not target_user:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            await state.clear()
            return

        tg_user_id = target_user.user_id
        user_name = target_user.market_name or target_user.first_name or "Noma'lum"
        group_msg_id = target_user.verification_group_message_id
        group_chat_id = target_user.verification_group_chat_id

        # Guruh xabari uchun ma'lumotlarni oldindan yig'ib olamiz
        username_str = f"@{target_user.username}" if target_user.username else "yo'q"
        original_text = (
            f"🔔 Yangi verifikatsiya so'rovi!\n\n"
            f"🏪 Do'kon: {target_user.market_name}\n"
            f"📍 Viloyat: {target_user.region or '—'}\n"
            f"👤 F.I.Sh: {target_user.last_name} {target_user.first_name} {target_user.middle_name or ''}\n"
            f"📞 Telefon: +{target_user.phone_number}\n"
            f"🪪 PINFL: {target_user.pinfl}\n"
            f"🆔 Telegram: {username_str} (ID: {target_user.user_id})\n\n"
            f"Iltimos, hujjatlarni tekshiring va tasdiqlang."
        )

        # Userni DB dan o'chiramiz — /start bossa yangi ro'yxatdan o'ta olsin
        await session.delete(target_user)
        await session.commit()

    # Userga xabar yuboramiz
    try:
        await message.bot.send_message(
            tg_user_id,
            f"❌ <b>Arizangiz rad etildi.</b>\n\n"
            f"📋 Sabab:\n<i>{reason}</i>\n\n"
            f"Xatoni to'g'irlab, qaytadan ro'yxatdan o'tishingiz mumkin.\n"
            f"Buning uchun /start ni bosing.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Guruhda message-ni edit qilish (agar group_msg_id bor bo'lsa)
    if group_msg_id and group_chat_id:
        try:
            updated_text = f"{original_text}\n\n❌ Bekor qilindi\n📋 Sabab: {reason}"
            await message.bot.edit_message_text(
                chat_id=group_chat_id,
                message_id=group_msg_id,
                text=updated_text,
                reply_markup=None  # Tugmalarni olib tashlaymiz
            )
        except Exception as e:
            print(f"Group message edit qilishda xato: {e}")

    await message.answer(
        f"✅ <b>{user_name}</b> rad etildi.\n"
        f"Foydalanuvchiga sabab ko'rsatilgan xabar yuborildi.\n"
        f"Foydalanuvchi ma'lumotlari tizimdan o'chirildi.",
        parse_mode="HTML"
    )

    await state.clear()


    await state.clear()
