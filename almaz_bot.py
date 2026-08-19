import asyncio
import logging
import sqlite3
import sys
import os
import re
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# =====================================================================
# 1. SOZLAMALAR (O'zingiz moslab chiqishingiz mumkin)
# =====================================================================
MAKER_TOKEN = os.environ.get("MAKER_TOKEN", "BOT_TOKENINGIZNI_SHU_YERGA_YOZING")

# Admin ID va Karta ma'lumotlari
ADMIN_ID = int(os.environ.get("899045766", 0))  # <-- ADMIN ID'INGIZNI SHU YERGA YOZING (Masalan: 123456789)
CARD_NUMBER = os.environ.get("5440810319904917", "5440810319904917")
CARD_HOLDER = os.environ.get("g/n", "KARTA EGGASI")

CREATE_PRICE = 39990
RENEW_PRICE = 11990
EXPIRE_DAYS = 17

PORT = int(os.environ.get("PORT", 8080))

maker_bot = Bot(token=MAKER_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

client_bots = {}

# =====================================================================
# 2. RENDER UCHUN DUMMY WEB SERVER
# =====================================================================
async def handle(request):
    return web.Response(text="Bot muvaffaqiyatli ishlamoqda!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# =====================================================================
# 3. FSM HOLATLARI
# =====================================================================
class BotCreateFSM(StatesGroup):
    waiting_template = State()
    waiting_token = State()
    waiting_admin_user = State()
    waiting_receipt = State()

class RenewFSM(StatesGroup):
    waiting_bot_id = State()
    waiting_receipt = State()

class ClientOrderFSM(StatesGroup):
    waiting_address = State()
    waiting_phone = State()

class ClientKinoFSM(StatesGroup):
    waiting_code = State()
    waiting_add_code = State()
    waiting_add_link = State()

class AdminBroadcastFSM(StatesGroup):
    waiting_message = State()

# =====================================================================
# 4. MA'LUMOTLAR BAZASI
# =====================================================================
def init_db():
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            bot_token TEXT UNIQUE,
            admin_username TEXT,
            template_id INTEGER,
            expire_date TEXT,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    conn.close()

def add_user_bot(owner_id, token, admin_user, template_id):
    expire = (datetime.now() + timedelta(days=EXPIRE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_bots (owner_id, bot_token, admin_username, template_id, expire_date, status)
        VALUES (?, ?, ?, ?, ?, 'active')
    """, (owner_id, token, admin_user, template_id, expire))
    bot_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return bot_id, expire

def extend_bot_subscription(bot_id):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM user_bots WHERE id = ?", (bot_id,))
    row = cursor.fetchone()
    if row:
        try:
            current_expire = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            current_expire = datetime.now()
        start_date = max(current_expire, datetime.now())
        new_expire = (start_date + timedelta(days=EXPIRE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE user_bots SET expire_date = ?, status = 'active' WHERE id = ?", (new_expire, bot_id))
        conn.commit()
        conn.close()
        return new_expire
    conn.close()
    return None

def get_user_bots_by_owner(owner_id):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, template_id, expire_date, status FROM user_bots WHERE owner_id = ?", (owner_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# =====================================================================
# 5. BOT SHABLONLARI KATALOGI
# =====================================================================
BOT_TEMPLATES = {
    1: {"name": "💎 Almaz & FF Bot (Spin-less Pro)", "cat": "O'yinlar"},
    2: {"name": "🎬 KINO BOT PRO (Kino qidiruv & Kodlar)", "cat": "Mediya"},
    3: {"name": "🎵 Musiqa / Shazam Bot PRO", "cat": "Mediya"},
    4: {"name": "🏬 Telegram Internet Magazin (E-Commerce)", "cat": "Biznes"},
    5: {"name": "🤖 Sun'iy Intellekt ChatGPT Pro Bot", "cat": "AI Tool"},
    6: {"name": "📥 Instagram/TikTok Video Downloader", "cat": "Yuklovchi"},
    7: {"name": "💵 SMS Qabul qilish & SMM Panel Bot", "cat": "Xizmatlar"},
    8: {"name": "📝 Anonim Chat & Tanishuv Boti", "cat": "Muloqot"},
    9: {"name": "🎓 Test va Imtihon Topshirish Boti", "cat": "Ta'lim"},
    10: {"name": "🍕 Taom / Posilka Yetkazish (Delivery)", "cat": "Biznes"},
}
for i in range(11, 101):
    BOT_TEMPLATES[i] = {"name": f"⚡ Pro Max Specialized Template #{i}", "cat": "Xizmatlar & Biznes"}

# =====================================================================
# 6. MIJOZ BOT DISPATCHERLARI
# =====================================================================
def init_client_db(db_id):
    conn = sqlite3.connect(f"client_data_{db_id}.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            balance INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            file_link TEXT
        )
    """)
    conn.commit()
    conn.close()

def build_client_dispatcher(template_id, db_id, admin_user, owner_id):
    c_dp = Dispatcher(storage=MemoryStorage())
    tpl_info = BOT_TEMPLATES.get(template_id, {"name": "Telegram Bot", "cat": "Xizmatlar"})

    if template_id == 1:
        @c_dp.message(CommandStart())
        async def almaz_start(msg: types.Message):
            kb = ReplyKeyboardBuilder()
            kb.button(text="💎 Almaz ishlash")
            kb.button(text="📊 Profilim")
            kb.button(text="🛒 O'yin Do'koni")
            if msg.from_user.id == owner_id:
                kb.button(text="🔑 Admin Panel")
            kb.adjust(2, 1)
            await msg.answer(f"👋 Salom {msg.from_user.full_name}!\n💎 **Almaz Bot Pro**ga xush kelibsiz!", reply_markup=kb.as_markup(resize_keyboard=True))

        @c_dp.message(F.text == "💎 Almaz ishlash")
        async def almaz_work(msg: types.Message, bot: Bot):
            me = await bot.get_me()
            await msg.answer(f"💎 Do'stlaringizga havola yuboring va bepul almaz oling:\nhttps://t.me/{me.username}?start={msg.from_user.id}")

        @c_dp.message(F.text == "📊 Profilim")
        async def almaz_prof(msg: types.Message):
            await msg.answer(f"📊 **Profil:** {msg.from_user.full_name}\n🆔 ID: `{msg.from_user.id}`\n💎 Balans: 0 almaz")

        @c_dp.message(F.text == "🛒 O'yin Do'koni")
        async def almaz_shop(msg: types.Message):
            b = InlineKeyboardBuilder()
            b.button(text="👨‍💻 Admin bilan bog'lanish", url=f"https://t.me/{admin_user}")
            await msg.answer("🛒 **O'yin Do'koni:**\n\n💎 100 Almaz - 15,000 so'm\n💎 310 Almaz - 42,000 so'm", reply_markup=b.as_markup())

    elif template_id == 2:
        @c_dp.message(CommandStart())
        async def kino_start(msg: types.Message):
            kb = ReplyKeyboardBuilder()
            kb.button(text="🔍 Kino qidirish (Kod bo'yicha)")
            kb.button(text="🔥 Top Kinolar")
            if msg.from_user.id == owner_id:
                kb.button(text="➕ Kino Qo'shish (Admin)")
                kb.button(text="🔑 Admin Panel")
            kb.adjust(2, 1)
            await msg.answer(f"🎬 **KINO BOT PRO**ga xush kelibsiz!\n\nKino kodini yuboring yoki menyudan foydalaning:", reply_markup=kb.as_markup(resize_keyboard=True))

        @c_dp.message(F.text == "🔍 Kino qidirish (Kod bo'yicha)")
        async def kino_search_prompt(msg: types.Message, state: FSMContext):
            await msg.answer("🔍 Qidirayotgan kinoyingiz **kodini** kiriting (Masalan: `101`):")
            await state.set_state(ClientKinoFSM.waiting_code)

        @c_dp.message(ClientKinoFSM.waiting_code)
        async def kino_get_by_code(msg: types.Message, state: FSMContext):
            code = msg.text.strip()
            conn = sqlite3.connect(f"client_data_{db_id}.db")
            cursor = conn.cursor()
            cursor.execute("SELECT file_link FROM movies WHERE code = ?", (code,))
            res = cursor.fetchone()
            conn.close()

            if res:
                await msg.answer(f"🎬 **Kino topildi! (Kod: {code})**\n\n🍿 Tomosha qilish havolasi / video: {res[0]}")
            else:
                await msg.answer(f"❌ `{code}` kodli kino topilmadi.")
            await state.clear()

        @c_dp.message(F.text == "➕ Kino Qo'shish (Admin)")
        async def kino_add_prompt(msg: types.Message, state: FSMContext):
            if msg.from_user.id != owner_id:
                return
            await msg.answer("➕ Yangi kino uchun **KOD** kiriting:")
            await state.set_state(ClientKinoFSM.waiting_add_code)

        @c_dp.message(ClientKinoFSM.waiting_add_code)
        async def kino_add_code(msg: types.Message, state: FSMContext):
            await state.update_data(new_code=msg.text.strip())
            await msg.answer("📹 Endi kino **videosi havolasi** yoki **Telegram post havolasini** yuboring:")
            await state.set_state(ClientKinoFSM.waiting_add_link)

        @c_dp.message(ClientKinoFSM.waiting_add_link)
        async def kino_save(msg: types.Message, state: FSMContext):
            data = await state.get_data()
            code = data.get("new_code")
            link = msg.text.strip()

            conn = sqlite3.connect(f"client_data_{db_id}.db")
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO movies (code, file_link) VALUES (?, ?)", (code, link))
            conn.commit()
            conn.close()

            await msg.answer(f"✅ **Kino saqlandi!**\nKod: `{code}`\nHavola: {link}")
            await state.clear()

    else:
        @c_dp.message(CommandStart())
        async def universal_start(msg: types.Message):
            kb = ReplyKeyboardBuilder()
            kb.button(text="🚀 Xizmatdan foydalanish")
            kb.button(text="ℹ️ Bot haqida")
            kb.button(text="📞 Aloqa")
            if msg.from_user.id == owner_id:
                kb.button(text="🔑 Admin Panel")
            kb.adjust(2, 1)
            await msg.answer(f"👋 **{tpl_info['name']}** botiga xush kelibsiz!", reply_markup=kb.as_markup(resize_keyboard=True))

        @c_dp.message(F.text == "🚀 Xizmatdan foydalanish")
        async def universal_use(msg: types.Message):
            await msg.answer(f"⚡ **{tpl_info['name']}** muvaffaqiyatli ishlamoqda.")

        @c_dp.message(F.text == "ℹ️ Bot haqida")
        async def universal_info(msg: types.Message):
            await msg.answer(f"ℹ️ **Bot Yo'nalishi:** {tpl_info['cat']}\n📌 **Shablon ID:** {template_id}")

        @c_dp.message(F.text == "📞 Aloqa")
        async def universal_contact(msg: types.Message):
            await msg.answer(f"📞 Bosh administrator: @{admin_user}")

    # --- ADMIN PANEL ---
    @c_dp.message(F.text == "🔑 Admin Panel")
    async def common_admin_panel(msg: types.Message):
        if msg.from_user.id != owner_id:
            return
        kb = ReplyKeyboardBuilder()
        kb.button(text="📢 Barchaga Xabar Yuborish")
        kb.button(text="📊 Obunachilar Soni")
        kb.button(text="🔙 Bosh menyu")
        kb.adjust(2, 1)
        await msg.answer("🛠 **ADMIN PANEL:**", reply_markup=kb.as_markup(resize_keyboard=True))

    @c_dp.message(F.text == "📢 Barchaga Xabar Yuborish")
    async def common_broadcast_start(msg: types.Message, state: FSMContext):
        if msg.from_user.id != owner_id:
            return
        await msg.answer("📢 Yubormoqchi bo'lgan xabaringizni kiriting:")
        await state.set_state(AdminBroadcastFSM.waiting_message)

    @c_dp.message(AdminBroadcastFSM.waiting_message)
    async def common_broadcast_send(msg: types.Message, state: FSMContext, bot: Bot):
        conn = sqlite3.connect(f"client_data_{db_id}.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [r[0] for r in cursor.fetchall()]
        conn.close()

        count = 0
        for u_id in users:
            try:
                await bot.send_message(u_id, msg.text)
                count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
        await msg.answer(f"✅ Xabar **{count}** ta foydalanuvchiga yuborildi!")
        await state.clear()

    @c_dp.message(F.text == "📊 Obunachilar Soni")
    async def common_stats(msg: types.Message):
        if msg.from_user.id != owner_id:
            return
        conn = sqlite3.connect(f"client_data_{db_id}.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        conn.close()
        await msg.answer(f"📊 Jami obunachilar soni: **{total} ta**")

    @c_dp.message(F.text == "🔙 Bosh menyu")
    async def common_back(msg: types.Message, state: FSMContext):
        await state.clear()
        await msg.answer("🔙 Bosh menyuga qaytdingiz.")

    return c_dp

async def register_and_start_client_bot(db_id, token, admin_user, owner_id, template_id=1):
    init_client_db(db_id)
    try:
        c_bot = Bot(token=token)
        await c_bot.delete_webhook(drop_pending_updates=True)
        c_dp = build_client_dispatcher(template_id, db_id, admin_user, owner_id)
        client_bots[db_id] = c_bot
        asyncio.create_task(c_dp.start_polling(c_bot))
        logging.info(f"Client bot #{db_id} (Shablon #{template_id}) ishga tushdi.")
    except Exception as e:
        logging.error(f"Client bot start error (ID: {db_id}): {e}")

async def start_all_user_bots():
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, bot_token, admin_username, template_id, owner_id FROM user_bots WHERE status = 'active'")
    bots = cursor.fetchall()
    conn.close()

    for b in bots:
        await register_and_start_client_bot(b[0], b[1], b[2], b[4], template_id=b[3])

# =====================================================================
# 7. MAKER BOT HANDLERLARI
# =====================================================================
def main_maker_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🤖 Bot Yaratish (39,990 so'm)")
    kb.button(text="📚 100 ta Botlar Katalogi")
    kb.button(text="🔄 Obunani Uzaytirish (11,990 so'm)")
    kb.button(text="📂 Mening Botlarim")
    kb.button(text="📞 Qo'llab-quvvatlash")
    kb.adjust(1, 2, 2)
    return kb.as_markup(resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    await msg.answer(
        f"🚀 **PRO MAX BOT CONSTRUCTOR**ga xush kelibsiz!\n\n"
        f"✨ Har xil turdagi 100 xil Telegram botlarni osongina yarating.\n"
        f"⏱ Barcha botlarning dastlabki ish muddati: **17 kun**.",
        reply_markup=main_maker_menu()
    )

@dp.message(F.text == "📚 100 ta Botlar Katalogi")
async def show_catalog(msg: types.Message):
    text = "📚 **PRO MAX BOTLAR KATALOGI:**\n\n"
    for k in range(1, 11):
        text += f"🔹 **ID: {k}** — {BOT_TEMPLATES[k]['name']}\n"
    text += f"\n...va yana 90 ta maxsus bot shablonlari mavjud!"
    await msg.answer(text)

@dp.message(F.text == "📂 Mening Botlarim")
async def my_bots(msg: types.Message):
    user_bots = get_user_bots_by_owner(msg.from_user.id)
    if not user_bots:
        await msg.answer("❌ Sizda hali yaratilgan botlar yo'q.")
        return
    text = "📂 **Sizning Botlaringiz:**\n\n"
    for b in user_bots:
        template_name = BOT_TEMPLATES.get(b[1], {}).get("name", f"Shablon #{b[1]}")
        text += f"🆔 **Bot ID:** `{b[0]}`\n🤖 **Tur:** {template_name}\n⏳ **Tugash sanasi:** {b[2]}\n------------------------------\n"
    await msg.answer(text)

@dp.message(F.text == "📞 Qo'llab-quvvatlash")
async def support_info(msg: types.Message):
    await msg.answer("📞 Qo'llab-quvvatlash markazi: @AdminUsername")

# --- BOT YARATISH OQIMI ---
@dp.message(F.text == "🤖 Bot Yaratish (39,990 so'm)")
async def start_bot_creation(msg: types.Message, state: FSMContext):
    await msg.answer("1️⃣ Yaratmoqchi bo'lgan botingiz **Shablon ID**sini kiriting (1 dan 100 gacha raqam):")
    await state.set_state(BotCreateFSM.waiting_template)

@dp.message(BotCreateFSM.waiting_template)
async def process_template_choice(msg: types.Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit() or int(msg.text) not in BOT_TEMPLATES:
        await msg.answer("❌ Noto'g'ri ID. 1 va 100 orasida raqam kiriting:")
        return
    await state.update_data(template_id=int(msg.text))
    await msg.answer("2️⃣ BotFather'dan olingan **Bot Token**ni yuboring:")
    await state.set_state(BotCreateFSM.waiting_token)

@dp.message(BotCreateFSM.waiting_token)
async def process_token_input(msg: types.Message, state: FSMContext):
    if not msg.text or ":" not in msg.text:
        await msg.answer("❌ Noto'g'ri Token formati. Qayta kiriting:")
        return
    await state.update_data(token=msg.text.strip())
    await msg.answer("3️⃣ Telegram **username**ingizni yuboring ('@' belgisiz):")
    await state.set_state(BotCreateFSM.waiting_admin_user)

@dp.message(BotCreateFSM.waiting_admin_user)
async def process_admin_user_input(msg: types.Message, state: FSMContext):
    clean_username = msg.text.strip().lstrip("@")
    await state.update_data(admin_user=clean_username)
    text = (
        f"💳 **TO'LOV QILISH BOSQICHI:**\n\n"
        f"💵 Narxi: **{CREATE_PRICE:,} so'm**\n"
        f"💳 Karta raqam: `{CARD_NUMBER}` ({CARD_HOLDER})\n\n"
        f"📌 To'lovni amalga oshirib, **chekni rasm holatida** yuboring:"
    )
    await msg.answer(text)
    await state.set_state(BotCreateFSM.waiting_receipt)

@dp.message(BotCreateFSM.waiting_receipt)
async def process_receipt_and_send_admin(msg: types.Message, state: FSMContext):
    if not msg.photo and not msg.document:
        await msg.answer("❌ Iltimos, chekni **rasm** holatida yuboring!")
        return

    data = await state.get_data()
    photo_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash va Yaratish", callback_data=f"approve_create:{msg.from_user.id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject:{msg.from_user.id}")
    builder.adjust(1)
    
    caption = (
        f"📥 YANGI BOT YARATISH CHEKI!\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name}\n"
        f"🆔 ID: {msg.from_user.id}\n"
        f"📌 Shablon ID: {data.get('template_id')}\n"
        f"🔑 Token: {data.get('token')}\n"
        f"👨‍💻 Admin: @{data.get('admin_user')}"
    )
    
    try:
        if msg.photo:
            await maker_bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=caption, reply_markup=builder.as_markup())
        else:
            await maker_bot.send_document(chat_id=ADMIN_ID, document=photo_id, caption=caption, reply_markup=builder.as_markup())
        await msg.answer("⌛ Chek adminga yuborildi! Tasdiqlangach botingiz avtomatik ishga tushadi.")
        await state.clear()
    except Exception as e:
        logging.error(f"Error sending receipt: {e}")
        await msg.answer("⚠️ Admin botni ishga tushirmagan yoki xatolik yuz berdi.")

# --- OBUNANI UZAYTIRISH OQIMI ---
@dp.message(F.text == "🔄 Obunani Uzaytirish (11,990 so'm)")
async def start_renew_process(msg: types.Message, state: FSMContext):
    await msg.answer("🔄 Obunasini uzaytirmoqchi bo'lgan **Bot ID**sini kiriting:")
    await state.set_state(RenewFSM.waiting_bot_id)

@dp.message(RenewFSM.waiting_bot_id)
async def process_renew_bot_id(msg: types.Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit():
        await msg.answer("❌ Noto'g'ri Bot ID. Faqat raqam kiriting:")
        return
    await state.update_data(renew_bot_id=int(msg.text))
    text = (
        f"💳 **OBUNANI UZAYTIRISH TO'LOVI:**\n\n"
        f"💵 Narxi: **{RENEW_PRICE:,} so'm** (+17 kun)\n"
        f"💳 Karta raqam: `{CARD_NUMBER}` ({CARD_HOLDER})\n\n"
        f"📌 To'lovni amalga oshirib, **chekni rasm holatida** yuboring:"
    )
    await msg.answer(text)
    await state.set_state(RenewFSM.waiting_receipt)

@dp.message(RenewFSM.waiting_receipt)
async def process_renew_receipt(msg: types.Message, state: FSMContext):
    if not msg.photo and not msg.document:
        await msg.answer("❌ Iltimos, chekni **rasm** holatida yuboring!")
        return

    data = await state.get_data()
    photo_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Obunani Uzaytirish", callback_data=f"approve_renew:{msg.from_user.id}:{data.get('renew_bot_id')}")
    builder.button(text="❌ Rad etish", callback_data=f"reject:{msg.from_user.id}")
    builder.adjust(1)
    
    caption = (
        f"🔄 OBUNANI UZAYTIRISH CHEKI!\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name}\n"
        f"🆔 ID: {msg.from_user.id}\n"
        f"🤖 Bot ID: {data.get('renew_bot_id')}"
    )
    
    try:
        if msg.photo:
            await maker_bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=caption, reply_markup=builder.as_markup())
        else:
            await maker_bot.send_document(chat_id=ADMIN_ID, document=photo_id, caption=caption, reply_markup=builder.as_markup())
        await msg.answer("⌛ Chek adminga yuborildi! Tasdiqlangach obunangiz uzaytiriladi.")
        await state.clear()
    except Exception as e:
        logging.error(f"Error sending receipt: {e}")
        await msg.answer("⚠️ Admin botga xabar yuborishda xatolik.")

# --- ADMIN CALLBACK HANDLERLARI ---
@dp.callback_query(F.data.startswith("approve_create:"))
async def approve_bot_creation(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    owner_id = int(call.data.split(":")[1])
    caption = call.message.caption or ""
    
    try:
        template_match = re.search(r"Shablon ID:\s*(\d+)", caption)
        token_match = re.search(r"Token:\s*([^\s\n]+)", caption)
        admin_match = re.search(r"Admin:\s*@?([^\s\n]+)", caption)

        template_id = int(template_match.group(1))
        token = token_match.group(1).strip()
        admin_user = admin_match.group(1).strip().replace("@", "")
    except Exception:
        await call.answer("❌ Ma'lumotlarni ajratishda xatolik!", show_alert=True)
        return

    bot_db_id, expire_date = add_user_bot(owner_id, token, admin_user, template_id)
    await register_and_start_client_bot(bot_db_id, token, admin_user, owner_id, template_id=template_id)
    
    template_name = BOT_TEMPLATES.get(template_id, {}).get('name', f"Shablon #{template_id}")
    await maker_bot.send_message(
        owner_id,
        f"🎉 **Botingiz muvaffaqiyatli yaratildi va ishga tushdi!**\n\n"
        f"🤖 Bot turi: **{template_name}**\n"
        f"🔑 Admin Panel: Botingizda `/start` bosing.\n"
        f"⏱ Tugash muddati: **{expire_date}**"
    )
    await call.message.edit_caption(caption=caption + "\n\n✅ **TASDIQLANDI VA BOT ISHGA TUSHIRILDI!**")
    await call.answer("Tasdiqlandi va ishga tushirildi!", show_alert=True)

@dp.callback_query(F.data.startswith("approve_renew:"))
async def approve_renew_subscription(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    parts = call.data.split(":")
    owner_id = int(parts[1])
    bot_id = int(parts[2])

    new_expire = extend_bot_subscription(bot_id)
    if new_expire:
        await maker_bot.send_message(
            owner_id,
            f"🎉 **Bot obunasi muvaffaqiyatli uzaytirildi!**\n\n"
            f"🆔 Bot ID: `{bot_id}`\n"
            f"⏳ Yangi tugash sanasi: **{new_expire}**"
        )
        await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n✅ **OBUNA UZAYTIRILDI!**")
        await call.answer("Obuna uzaytirildi!", show_alert=True)
    else:
        await call.answer("❌ Bot topilmadi!", show_alert=True)

@dp.callback_query(F.data.startswith("reject:"))
async def reject_payment(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    owner_id = int(call.data.split(":")[1])
    await maker_bot.send_message(owner_id, "❌ **To'lovingiz rad etildi.** Chek xato yoki to'lov kelib tushmadi.")
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n❌ **RAD ETILDI.**")
    await call.answer("Rad etildi!", show_alert=True)

# =====================================================================
# 8. MAIN
# =====================================================================
async def main():
    init_db()
    await start_dummy_server()
    
    # TelegramConflictError oldini olish uchun webhook'ni o'chirish
    await maker_bot.delete_webhook(drop_pending_updates=True)
    
    await start_all_user_bots()
    logging.info("Main bot started...")
    await dp.start_polling(maker_bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
