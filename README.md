# Amir Group - Audit & Debt Control Bot

Bu loyiha Amir Group ulgurji smartfon savdosi kompaniyasining mijozlariga mo'ljallangan qarzlari monitoringini olib boruvchi Telegram bot hisoblanadi.

## Texnologik Stack
* **Python 3.11+**
* **Aiogram 3.x** - Telegram Bot Framework
* **SQLAlchemy (async) + Alembic** - Ma'lumotlar bazasi ORM va migratsiyasi
* **asyncpg** - PostgreSQL drayveri
* **APScheduler** - Avtomatik bildirishnomalar (cron tasks)
* **aiohttp** - 1C:Enterprise API bilan integratsiya uchun
* **Pandas & Openpyxl** - Excel hisobotlarni generatsiya qilish uchun

---

## O'rnatish tartibi

### 1. Talablar
Serverda o'rnatilgan bo'lishi kerak:
- Python 3.11 yoki 3.12
- PostgreSQL 14+

### 2. Loyihani yuklab olish va VENV ochish
```bash
git clone <repo_url>
cd amirgroup
python -m venv venv
# Windows uchun
.\venv\Scripts\activate
# Linux uchun
source venv/bin/activate
```

### 3. Kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```

### 4. Sozlamalar (.env)
Loyihaning ildiz papkasiga `.env` faylini quyidagi parametrlar bilan saqlang:
```env
TELEGRAM_TOKEN="BOT_TOKENI"
DB_URL="postgresql+asyncpg://user:pass@host:port/dbname"
API_1C_URL="http://195.158.10.103:8081/api_path/"
API_1C_LOGIN="LOGIN"
API_1C_PASSWORD="PASSWORD"
PUBLIC_OFFER_URL="DOC_URL"
```

### 5. Ma'lumotlar bazasi migratsiyalari
```bash
alembic upgrade head
```

### 6. Botni ishga tushirish
```bash
python -m bot.main
```

---

## Asosiy imkoniyatlar

### 👤 Mijozlar uchun:
- **Profil**: Do'kon ma'lumotlari va joriy qarz holati.
- **Sverka**: Auditorlar tomonidan yuborilgan qarz ma'lumotlarini tasdiqlash yoki e'tiroz bildirish.
- **Eslatmalar**: Muddati o'tgan qarzlar haqida avtomatik ogohlantirishlar.

### 👨‍💼 Auditorlar uchun:
- **Sverka yuborish**: Barcha yoki tanlangan mijozlarga oylik hisob-kitoblarni yuborish.
- **Qarzdorlarga eslatma**: Bir tugma orqali barcha qarzdorlarga to'lov haqida eslatma yuborish.
- **Qidiruv**: Mijozlarni ID, telefon yoki do'kon nomi bo'yicha topish.

### ⚙️ Adminlar uchun:
- **Statistika**: Umumiy qarzlar va foydalanuvchilar soni.
- **Excel Export**: O'tkazilgan sverka natijalarini Excel shaklida yuklab olish.
- **Sozlamalar**: Chat ID'lar va boshqa tizim parametrlarini Telegram'dan boshqarish.

---

## Integratsiyalar
Bot 1C:Enterprise platformasi bilan quyidagi metodlar ustida to'g'ridan-to'g'ri aloqa bog'laydi:
- `/check_user/{phone}` - Qarz, telefon va shartnomalar ro'yxatini yuklaydi.
- `/update_status` - Foydalanuvchi qarz haqidagi sverkani e'tirozsiz/e'tiroz bilan qabul qilganda qaytaradi.
