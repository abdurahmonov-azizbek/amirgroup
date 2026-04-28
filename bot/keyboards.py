from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import math

def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def offer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Tasdiqlayman", callback_data="offer_accepted")]]
    )

def client_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Mening balansim"), KeyboardButton(text="📄 Shartnomalarim")],
            [KeyboardButton(text="🕒 Xaridlar tarixi"), KeyboardButton(text="📞 Auditor bilan aloqa")],
            [KeyboardButton(text="👤 Profilim")]
        ],
        resize_keyboard=True
    )

def auditor_contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Bekor qilish")]],
        resize_keyboard=True
    )

def contact_reviewed_kb(chat_username: str = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Bog'lanildi", callback_data="contact_called"),
            ]
        ]
    )

def recon_reviewed_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ko'rib chiqildi", callback_data="recon_reviewed"),
            ]
        ]
    )

def auditor_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🔍 Qidiruv")],
            [KeyboardButton(text="📨 Sverka yuborish"), KeyboardButton(text="📁 Sverkalar")],
            [KeyboardButton(text="📢 Ommaviy xabar yuborish")],
            [KeyboardButton(text="⚠️ Qarzdorlarga eslatma")]
        ],
        resize_keyboard=True
    )

def auditor_statistics_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Barcha mijozlar", callback_data="aud_stat_all")],
            [InlineKeyboardButton(text="⚠️ Qarzdorlar", callback_data="aud_stat_debtors")],
            [InlineKeyboardButton(text="🚨 Muddati o'tgan mijozlar", callback_data="aud_stat_overdue")]
        ]
    )

def admin_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📈 Umumiy statistika")],
            [KeyboardButton(text="👨‍💼 Auditorlar (Qo'shish/O'chirish)")],
            [KeyboardButton(text="📢 Ommaviy xabar yuborish"), KeyboardButton(text="⚠️ Qarzdorlarga eslatma")],
            [KeyboardButton(text="⚙️ Tizim sozlamalari")]
        ],
        resize_keyboard=True
    )

def build_reconciliation_pagination_kb(reconciliations, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    
    for r in reconciliations:
        # Date format: 2024-04-21 15:30
        date_str = r.created_at.strftime("%Y-%m-%d %H:%M")
        buttons.append([InlineKeyboardButton(text=f"📅 {date_str}", callback_data=f"admin_recon_export_{r.id}")])
        
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin_recon_page_{page-1}"))
    
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
    
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin_recon_page_{page+1}"))
        
    if nav_row:
        buttons.append(nav_row)
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_manage_auditors_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Auditor tayinlash", callback_data="admin_list_users")],
            [InlineKeyboardButton(text="👔 Auditorlarni o'chirish", callback_data="admin_list_auditors")]
        ]
    )

def build_users_pagination_kb(users, page: int, total_pages: int, action_prefix: str, back_callback: str = None) -> InlineKeyboardMarkup:
    buttons = []
    
    for u in users:
        name = f"{u.first_name or ''} {u.last_name or ''} {u.middle_name or ''}"
        name += f" ({u.user_id})"
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"{action_prefix}_{u.id}")])
        
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page_{action_prefix}_{page-1}"))
        
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
    
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page_{action_prefix}_{page+1}"))
        
    if nav_row:
        buttons.append(nav_row)
        
    if back_callback:
        buttons.append([InlineKeyboardButton(text="🔙 Ortga", callback_data=back_callback)])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def reconciliation_action_kb(reconciliation_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlayman", callback_data=f"recon_confirm_{reconciliation_id}"),
                InlineKeyboardButton(text="❌ E'tirozim bor", callback_data=f"recon_disown_{reconciliation_id}")
            ]
        ]
    )

def verify_action_kb(user_db_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"grpv_accept_{user_db_id}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"grpv_reject_{user_db_id}")
            ]
        ]
    )

def cancel_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="cancel_action")]]
    )


