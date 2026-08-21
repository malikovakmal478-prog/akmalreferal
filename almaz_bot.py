import asyncio
import logging
import sqlite3
import sys
import os
import re
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# =====================================================================
# 1. SOZLAMALAR
# =====================================================================
MAKER_TOKEN = os.environ.get("MAKER_TOKEN", "8635436262:AAF7BepP4Wf1v6-araw4IsyA-RWMZ8_W9hs")
INITIAL_ADMIN_ID = int(os.environ.get("ADMIN_ID", 7849637859))
PORT = int(os.environ.get("PORT", 8080))

# Render platformasiga proksi keraksiz - to'g'ridan-to me'yoriy ulanish beriladi
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

class ClientKinoFSM(StatesGroup):
    waiting_code = State()
    waiting_add_code = State()
    waiting_add_link = State()

class AdminBroadcastFSM(StatesGroup):
    waiting_message = State()

class MakerAdminFSM(StatesGroup):
    waiting_broadcast = State()
    waiting_new_admin_id = State()
    waiting_card_number = State()
    waiting_card_holder = State()
    waiting_create_price = State()
    waiting_renew_price = State()
    waiting_btn_name = State()
    waiting_btn_val = State()

# =====================================================================
# 4. MA'LUMOTLAR BAZASI & DYNAMIC SETTINGS
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maker_users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            joined_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_creations (
            owner_id INTEGER PRIMARY KEY,
            token TEXT,
            admin_user TEXT,
            template_id INTEGER
        )
    """)
    
    defaults = {
        "admin_id": str(INITIAL_ADMIN_ID),
        "card_number": "5440810319904917",
        "card_holder": "g/n",
        "create_price": "39990",
        "renew_price": "11990",
        "expire_days": "17",
        "btn_create": "🤖 Bot Yaratish",
        "btn_catalog": "📚 100 ta Botlar Katalogi",
        "btn_renew": "🔄 Obunani Uzaytirish",
        "btn_mybots": "📂 Mening Botlarim",
        "btn_support": "📞 Qo'llab-quvvatlash"
    }
    
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def add_maker_user(user_id, full_name, username):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR IGNORE INTO maker_users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
                   (user_id, full_name, username or "", now))
    conn.commit()
    conn.close()

def save_pending_creation(owner_id, token, admin_user, template_id):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO pending_creations (owner_id, token, admin_user, template_id) VALUES (?, ?, ?, ?)",
                   (owner_id, token, admin_user, template_id))
    conn.commit()
    conn.close()

def get_pending_creation(owner_id):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT token, admin_user, template_id FROM pending_creations WHERE owner_id = ?", (owner_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def add_user_bot(owner_id, token, admin_user, template_id):
    expire_days = int(get_setting("expire_days", "17"))
    expire = (datetime.now() + timedelta(days=expire_days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_bots (owner_id, bot_token, admin_username, template_id, expire_date, status)
        VALUES (?, ?, ?, ?, ?, 'active')
    """, (owner_id, token, admin_user, template_id, expire))
    bot_id = cursor.lastrowid
    cursor.execute("DELETE FROM pending_creations WHERE owner_id = ?", (owner_id,))
    conn.commit()
    conn.close()
    return bot_id, expire

def extend_bot_subscription(bot_id):
    expire_days = int(get_setting("expire_days", "17"))
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
        new_expire = (start_date + timedelta(days=expire_days)).strftime("%Y-%m-%d %H:%M:%S")
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
            await msg.answer("🎬 **KINO BOT PRO**ga xush kelibsiz!\n\nKino kodini yuboring yoki menyudan foydalaning:", reply_markup=kb.as_markup(resize_keyboard=True))

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
# 7. MAKER BOT HANDLERLARI VA DINAMIK MENYU
# =====================================================================
def main_maker_menu():
    c_price = int(get_setting("create_price", "39990"))
    r_price = int(get_setting("renew_price", "11990"))
    
    b_create = get_setting("btn_create", "🤖 Bot Yaratish")
    b_catalog = get_setting("btn_catalog", "📚 100 ta Botlar Katalogi")
    b_renew = get_setting("btn_renew", "🔄 Obunani Uzaytirish")
    b_mybots = get_setting("btn_mybots", "📂 Mening Botlarim")
    b_support = get_setting("btn_support", "📞 Qo'llab-quvvatlash")

    kb = ReplyKeyboardBuilder()
    kb.button(text=f"{b_create} ({c_price:,} so'm)")
    kb.button(text=b_catalog)
    kb.button(text=f"{b_renew} ({r_price:,} so'm)")
    kb.button(text=b_mybots)
    kb.button(text=b_support)
    kb.adjust(1, 2, 2)
    return kb.as_markup(resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    add_maker_user(msg.from_user.id, msg.from_user.full_name, msg.from_user.username)
    
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    admin_note = "\n\n⚡ Admin rejimiga kirish: /admin" if msg.from_user.id == admin_id else ""
    
    await msg.answer(
        f"🚀 **PRO MAX BOT CONSTRUCTOR**ga xush kelibsiz!\n\n"
        f"✨ Har xil turdagi 100 xil Telegram botlarni osongina yarating.\n"
        f"⏱ Barcha botlarning dastlabki ish muddati: **{get_setting('expire_days', '17')} kun**.{admin_note}",
        reply_markup=main_maker_menu()
    )

# --- BOSH ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_panel_cmd(msg: types.Message):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if msg.from_user.id != admin_id:
        await msg.answer("❌ Siz Bosh Administrator emassiz!")
        return

    b = InlineKeyboardBuilder()
    b.button(text="📢 Barchaga Xabar (Broadcast)", callback_data="admin_broadcast")
    b.button(text="📊 Maker Bot Statistikasi", callback_data="admin_stats")
    b.button(text="✏️ Tugmalar Matnini Tahrirlash", callback_data="admin_edit_btns")
    b.button(text="💳 Karta va Narxlarni O'zgartirish", callback_data="admin_edit_pricing")
    b.button(text="👑 Adminlikni Boshqaga O'tkazish", callback_data="admin_transfer")
    b.adjust(1)

    await msg.answer("👑 **MAKER BOT BOSH ADMIN PANELI:**\n\nKerakli bo'limni tanlang:", reply_markup=b.as_markup())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_call(call: types.CallbackQuery):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id: return

    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM maker_users")
    m_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_bots WHERE status = 'active'")
    a_bots = cursor.fetchone()[0]
    conn.close()

    await call.message.edit_text(
        f"📊 **MAKER BOT STATISTIKASI:**\n\n"
        f"👤 Jami foydalanuvchilar: **{m_users} ta**\n"
        f"🤖 Faol botlar soni: **{a_bots} ta**\n"
        f"👑 Hozirgi Admin ID: `{admin_id}`",
        reply_markup=call.message.reply_markup
    )
    await call.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_call(call: types.CallbackQuery, state: FSMContext):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id: return

    await call.message.answer("📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan **xabaringizni** yuboring:")
    await state.set_state(MakerAdminFSM.waiting_broadcast)
    await call.answer()

@dp.message(MakerAdminFSM.waiting_broadcast)
async def process_maker_broadcast(msg: types.Message, state: FSMContext):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM maker_users")
    users = [r[0] for r in cursor.fetchall()]
    conn.close()

    count = 0
    await msg.answer("⏳ Xabar yuborilmoqda...")
    for u_id in users:
        try:
            await msg.copy_to(chat_id=u_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await msg.answer(f"✅ Xabar **{count}** ta foydalanuvchiga muvaffaqiyatli yuborildi!")
    await state.clear()

@dp.callback_query(F.data == "admin_transfer")
async def admin_transfer_call(call: types.CallbackQuery, state: FSMContext):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id: return

    await call.message.answer("⚠️ **ADMINLIKNI O'TKAZISH:**\n\nYangi Bosh Admin bo'ladigan shaxsning **Telegram ID raqamini** kiriting:")
    await state.set_state(MakerAdminFSM.waiting_new_admin_id)
    await call.answer()

@dp.message(MakerAdminFSM.waiting_new_admin_id)
async def process_transfer_admin(msg: types.Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit():
        await msg.answer("❌ Noto'g'ri ID. Faqat raqamlardan iborat Telegram ID kiriting:")
        return

    new_admin_id = int(msg.text)
    set_setting("admin_id", new_admin_id)

    await msg.answer(f"✅ Adminlik muvaffaqiyatli o'tkazildi!\nYangi Admin ID: `{new_admin_id}`")
    try:
        await maker_bot.send_message(new_admin_id, "🎉 **Siz PRO MAX Bot Constructor'da Bosh Admin qilib tayinlandingiz!**\nAdmin paneldan foydalanish uchun /admin buyrug'ini bosing.")
    except Exception:
        pass
    await state.clear()

@dp.callback_query(F.data == "admin_edit_pricing")
async def admin_edit_pricing_call(call: types.CallbackQuery):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id: return

    b = InlineKeyboardBuilder()
    b.button(text="💳 Karta Raqamni o'zgartirish", callback_data="set_card_num")
    b.button(text="👤 Karta Egalik Ismini o'zgartirish", callback_data="set_card_holder")
    b.button(text="💵 Yaratish Narxini o'zgartirish", callback_data="set_create_price")
    b.button(text="🔄 Uzaytirish Narxini o'zgartirish", callback_data="set_renew_price")
    b.adjust(1)

    cur_card = get_setting("card_number")
    cur_holder = get_setting("card_holder")
    cur_c_price = get_setting("create_price")
    cur_r_price = get_setting("renew_price")

    await call.message.edit_text(
        f"💳 **HOZIRGI TO'LOV SOZLAMALARI:**\n\n"
        f"💳 Karta: `{cur_card}` ({cur_holder})\n"
        f"💵 Yaratish narxi: **{int(cur_c_price):,} so'm**\n"
        f"🔄 Uzaytirish narxi: **{int(cur_r_price):,} so'm**",
        reply_markup=b.as_markup()
    )
    await call.answer()

@dp.callback_query(F.data.startswith("set_"))
async def process_pricing_set_callbacks(call: types.CallbackQuery, state: FSMContext):
    act = call.data
    if act == "set_card_num":
        await call.message.answer("💳 Yangi **Karta raqamini** kiriting:")
        await state.set_state(MakerAdminFSM.waiting_card_number)
    elif act == "set_card_holder":
        await call.message.answer("👤 Yangi **Karta egasi ismini** kiriting:")
        await state.set_state(MakerAdminFSM.waiting_card_holder)
    elif act == "set_create_price":
        await call.message.answer("💵 Bot yaratish uchun **yangi narxni** kiriting:")
        await state.set_state(MakerAdminFSM.waiting_create_price)
    elif act == "set_renew_price":
        await call.message.answer("🔄 Obunani uzaytirish uchun **yangi narxni** kiriting:")
        await state.set_state(MakerAdminFSM.waiting_renew_price)
    await call.answer()

@dp.message(MakerAdminFSM.waiting_card_number)
async def set_card_number_val(msg: types.Message, state: FSMContext):
    set_setting("card_number", msg.text.strip())
    await msg.answer("✅ Karta raqami yangilandi!", reply_markup=main_maker_menu())
    await state.clear()

@dp.message(MakerAdminFSM.waiting_card_holder)
async def set_card_holder_val(msg: types.Message, state: FSMContext):
    set_setting("card_holder", msg.text.strip())
    await msg.answer("✅ Karta egasi ismi yangilandi!", reply_markup=main_maker_menu())
    await state.clear()

@dp.message(MakerAdminFSM.waiting_create_price)
async def set_create_price_val(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("❌ Faqat raqam kiriting:")
    set_setting("create_price", msg.text.strip())
    await msg.answer("✅ Bot yaratish narxi yangilandi!", reply_markup=main_maker_menu())
    await state.clear()

@dp.message(MakerAdminFSM.waiting_renew_price)
async def set_renew_price_val(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("❌ Faqat raqam kiriting:")
    set_setting("renew_price", msg.text.strip())
    await msg.answer("✅ Obuna uzaytirish narxi yangilandi!", reply_markup=main_maker_menu())
    await state.clear()

@dp.callback_query(F.data == "admin_edit_btns")
async def admin_edit_btns_call(call: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text=f"1. {get_setting('btn_create')}", callback_data="btn_edit:btn_create")
    b.button(text=f"2. {get_setting('btn_catalog')}", callback_data="btn_edit:btn_catalog")
    b.button(text=f"3. {get_setting('btn_renew')}", callback_data="btn_edit:btn_renew")
    b.button(text=f"4. {get_setting('btn_mybots')}", callback_data="btn_edit:btn_mybots")
    b.button(text=f"5. {get_setting('btn_support')}", callback_data="btn_edit:btn_support")
    b.adjust(1)
    await call.message.edit_text("✏️ O'zgartirmoqchi bo'lgan **tugmangizni** tanlang:", reply_markup=b.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("btn_edit:"))
async def btn_edit_choice(call: types.CallbackQuery, state: FSMContext):
    key = call.data.split(":")[1]
    await state.update_data(target_key=key)
    await call.message.answer(f"✏️ `{key}` uchun **yangi matnni** kiriting:")
    await state.set_state(MakerAdminFSM.waiting_btn_val)
    await call.answer()

@dp.message(MakerAdminFSM.waiting_btn_val)
async def btn_edit_save(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("target_key")
    set_setting(key, msg.text.strip())
    await msg.answer("✅ Tugma matni muvaffaqiyatli o'zgartirildi!", reply_markup=main_maker_menu())
    await state.clear()

# --- MENYU TUGMALARI HANDLERLARI ---
@dp.message(F.text.contains("100 ta Botlar Katalogi"))
async def show_catalog(msg: types.Message):
    text = "📚 **PRO MAX BOTLAR KATALOGI (1-100):**\n\n"
    for i in range(1, 11):
        info = BOT_TEMPLATES[i]
        text += f"**#{i}** - {info['name']} _({info['cat']})_\n"
    text += "\n... va yana 90 ta tayyor shablonlar xizmatingizda!"
    await msg.answer(text)

@dp.message(F.text.contains("Mening Botlarim"))
async def show_my_bots(msg: types.Message):
    bots = get_user_bots_by_owner(msg.from_user.id)
    if not bots:
        await msg.answer("📂 Sizda hali yaratilgan botlar mavjud emas.")
        return

    text = "📂 **MENING BOTLARIM:**\n\n"
    for b in bots:
        tpl = BOT_TEMPLATES.get(b[1], {"name": "Bot"})
        text += f"🆔 **Bot ID:** `{b[0]}`\n📌 Shablon: {tpl['name']}\n⏳ Amal qilish muddati: **{b[2]}**\n🟢 Holati: {b[3]}\n-------------------\n"
    await msg.answer(text)

@dp.message(F.text.contains("Qo'llab-quvvatlash"))
async def show_support(msg: types.Message):
    admin_id = get_setting("admin_id", str(INITIAL_ADMIN_ID))
    await msg.answer(f"📞 Savollar va takliflar bo'yicha Bosh Admin bilan bog'laning:\n🆔 Admin ID: `{admin_id}`")

# --- BOT YARATISH BOSQICHALARI ---
@dp.message(F.text.contains("Bot Yaratish"))
async def start_create_bot(msg: types.Message, state: FSMContext):
    await msg.answer("📚 Yaratmoqchi bo'lgan botingiz **shablon ID-sini** kiriting (1 dan 100 gacha, masalan: `1` yoki `2`):")
    await state.set_state(BotCreateFSM.waiting_template)

@dp.message(BotCreateFSM.waiting_template)
async def process_template_id(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit() or not (1 <= int(msg.text) <= 100):
        await msg.answer("❌ Noto'g'ri ID. 1 dan 100 gacha bo'lgan raqam kiriting:")
        return
    template_id = int(msg.text)
    await state.update_data(template_id=template_id)
    
    await msg.answer(
        "🤖 **Bot Tokenini kiriting:**\n\n"
        "1. @BotFather 'ga bering.\n"
        "2. `/newbot` buyrug'i orqali yangi bot yarating.\n"
        "3. Berilgan **API Token**ni bu yerga yuboring:"
    )
    await state.set_state(BotCreateFSM.waiting_token)

@dp.message(BotCreateFSM.waiting_token)
async def process_bot_token(msg: types.Message, state: FSMContext):
    token = msg.text.strip()
    if not re.match(r"^\d+:[A-Za-z0-9_-]+$", token):
        await msg.answer("❌ Noto'g'ri Token formati! Token `123456:ABC...` ko'rinishida bo'ladi. Qayta kiriting:")
        return
    await state.update_data(token=token)
    await msg.answer("👤 O'zingizning shaxsiy Telegram **username**ingizni kiriting (masalan: `durov` yoki `@durov`):")
    await state.set_state(BotCreateFSM.waiting_admin_user)

@dp.message(BotCreateFSM.waiting_admin_user)
async def process_admin_user(msg: types.Message, state: FSMContext):
    admin_user = msg.text.strip().replace("@", "")
    await state.update_data(admin_user=admin_user)

    data = await state.get_data()
    save_pending_creation(msg.from_user.id, data["token"], admin_user, data["template_id"])

    c_price = int(get_setting("create_price", "39990"))
    card_num = get_setting("card_number")
    card_holder = get_setting("card_holder")

    text = (
        f"💳 **BOT YARATISH TO'LOVI:**\n\n"
        f"🤖 Shablon ID: `{data['template_id']}`\n"
        f"💵 Narxi: **{c_price:,} so'm**\n"
        f"💳 Karta raqam: `{card_num}` ({card_holder})\n\n"
        f"📌 To'lovni amalga oshirib, **chekni rasm holatida** yuboring:"
    )
    await msg.answer(text)
    await state.set_state(BotCreateFSM.waiting_receipt)

@dp.message(BotCreateFSM.waiting_receipt)
async def process_create_receipt(msg: types.Message, state: FSMContext):
    photo_id = None
    if msg.photo:
        photo_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo_id = msg.document.file_id

    if not photo_id:
        await msg.answer("❌ Iltimos, chekni **rasm** holatida yuboring!")
        return

    data = await state.get_data()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Botni Tasdiqlash va Yaratish", callback_data=f"approve_create:{msg.from_user.id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject:{msg.from_user.id}")
    builder.adjust(1)

    caption = (
        f"📥 **YANGI BOT YARATISH CHEKI!**\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name} (`{msg.from_user.id}`)\n"
        f"🤖 Shablon ID: `{data.get('template_id')}`\n"
        f"🔑 Admin Username: @{data.get('admin_user')}"
    )

    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    try:
        await maker_bot.send_photo(chat_id=admin_id, photo=photo_id, caption=caption, reply_markup=builder.as_markup())
        await msg.answer("✅ Chek qabul qilindi. Bosh admin tasdiqlagach botingiz ishga tushiriladi!")
    except Exception as e:
        await msg.answer(f"❌ Adminga xabar yuborishda xatolik yuz berdi: {e}")
    
    await state.clear()

# --- OBUNANI UZAYTIRISH BOSQICHALARI ---
@dp.message(F.text.contains("Obunani Uzaytirish"))
async def start_renew(msg: types.Message, state: FSMContext):
    bots = get_user_bots_by_owner(msg.from_user.id)
    if not bots:
        await msg.answer("❌ Sizda uzaytiradigan botlar yo'q.")
        return
    await msg.answer("🔄 Obunasini uzaytirmoqchi bo'lgan **Bot ID-sini** kiriting:")
    await state.set_state(RenewFSM.waiting_bot_id)

@dp.message(RenewFSM.waiting_bot_id)
async def process_renew_bot_id(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit():
        await msg.answer("❌ Noto'g'ri Bot ID. Raqam kiriting:")
        return
    bot_id = int(msg.text)
    await state.update_data(renew_bot_id=bot_id)

    r_price = int(get_setting("renew_price", "11990"))
    card_num = get_setting("card_number")
    card_holder = get_setting("card_holder")

    text = (
        f"💳 **OBUNANI UZAYTIRISH TO'LOVI:**\n\n"
        f"🤖 Bot ID: `{bot_id}`\n"
        f"💵 Uzaytirish narxi: **{r_price:,} so'm**\n"
        f"💳 Karta: `{card_num}` ({card_holder})\n\n"
        f"📌 To'lovni amalga oshirib, **chekni rasm holatida** yuboring:"
    )
    await msg.answer(text)
    await state.set_state(RenewFSM.waiting_receipt)

@dp.message(RenewFSM.waiting_receipt)
async def process_renew_receipt(msg: types.Message, state: FSMContext):
    photo_id = None
    if msg.photo:
        photo_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo_id = msg.document.file_id

    if not photo_id:
        await msg.answer("❌ Iltimos, chekni **rasm** holatida yuboring!")
        return

    data = await state.get_data()
    bot_id = data.get("renew_bot_id")

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Obunani Uzaytirishni Tasdiqlash", callback_data=f"approve_renew:{bot_id}:{msg.from_user.id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject:{msg.from_user.id}")
    builder.adjust(1)

    caption = (
        f"📥 **OBUNANI UZAYTIRISH CHEKI!**\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name} (`{msg.from_user.id}`)\n"
        f"🤖 Bot ID: `{bot_id}`"
    )

    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    try:
        await maker_bot.send_photo(chat_id=admin_id, photo=photo_id, caption=caption, reply_markup=builder.as_markup())
        await msg.answer("✅ Chek qabul qilindi! Bosh admin tasdiqlashi bilan obuna uzaytiriladi.")
    except Exception as e:
        await msg.answer(f"❌ Adminga xabar yuborishda xatolik: {e}")
    await state.clear()

# --- ADMIN TASDIQLASH CALLBACKS ---
@dp.callback_query(F.data.startswith("approve_create:"))
async def approve_create_callback(call: types.CallbackQuery):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id: return

    owner_id = int(call.data.split(":")[1])
    pending = get_pending_creation(owner_id)

    if not pending:
        await call.message.edit_caption(caption=call.message.caption + "\n\n❌ **Xatolik:** Ariza ma'lumotlari topilmadi!")
        return

    token, admin_user, template_id = pending
    bot_id, expire = add_user_bot(owner_id, token, admin_user, template_id)

    await register_and_start_client_bot(bot_id, token, admin_user, owner_id, template_id)

    await call.message.edit_caption(caption=call.message.caption + f"\n\n✅ **BOT TASDIQLANDI VA ISHGA TUSHIRILDI!** (Bot ID: `{bot_id}`)")
    try:
        await maker_bot.send_message(owner_id, f"🎉 **Tabriklaymiz! Botingiz muvaffaqiyatli yaratildi va ishga tushdi!**\n\n🆔 Bot ID: `{bot_id}`\n⏳ Amal qilish muddati: **{expire}**")
    except Exception:
        pass
    await call.answer()

@dp.callback_query(F.data.startswith("approve_renew:"))
async def approve_renew_callback(call: types.CallbackQuery):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id: return

    parts = call.data.split(":")
    bot_id = int(parts[1])
    owner_id = int(parts[2])

    new_expire = extend_bot_subscription(bot_id)

    if new_expire:
        await call.message.edit_caption(caption=call.message.caption + f"\n\n✅ **OBUNA UZAYTIRILDI!**\nYangi muddat: **{new_expire}**")
        try:
            await maker_bot.send_message(owner_id, f"🎉 **Bot ID: {bot_id} obunasi uzaytirildi!**\nYangi tugash muddati: **{new_expire}**")
        except Exception:
            pass
    else:
        await call.message.edit_caption(caption=call.message.caption + "\n\n❌ **Xatolik:** Bot topilmadi!")
    await call.answer()

@dp.callback_query(F.data.startswith("reject:"))
async def reject_callback(call: types.CallbackQuery):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id: return

    owner_id = int(call.data.split(":")[1])
    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ **TO'LOV CHEKI RAD ETILDI!**")
    try:
        await maker_bot.send_message(owner_id, "❌ Siz yuborgan to'lov cheki admin tomonidan rad etildi. Qayta urinib ko'ring yoki adminga murojaat qiling.")
    except Exception:
        pass
    await call.answer()

# =====================================================================
# 8. ASOSIY ISHGA TUSHIRISH
# =====================================================================
async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    init_db()
    
    # Render Web Serverini ishga tushirish
    await start_dummy_server()
    
    # Barcha mavjud mijoz botlarini qayta tiklash
    await start_all_user_bots()
    
    # Maker Bot Webhook ni tozalash va Polling boshlash
    await maker_bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(maker_bot)

if __name__ == "__main__":
    asyncio.run(main())
