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

# =====================================================================
# 1. SOZLAMALAR
# =====================================================================
MAKER_TOKEN = os.environ.get("MAKER_TOKEN", "8635436262:AAEhA-k6BioT73wRC8dgWujS_6g3FH83GTg")
INITIAL_ADMIN_ID = int(os.environ.get("ADMIN_ID", 7849637859))
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
    
    # Yaratilgan botlar bazasi
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
    
    # Maker bot foydalanuvchilari
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maker_users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            joined_at TEXT
        )
    """)
    
    # Sozlamalar va Tugmalar matnlari
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Boshlang'ich sozlamalarni o'rnatish
    defaults = {
        "admin_id": str(INITIAL_ADMIN_ID),
        "card_number": "5440810319904917",
        "card_holder": "g/n",
        "create_price": "39990",
        "renew_price": "11990",
        "expire_days": "17",
        # Tugmalar matnlari
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

    # --- CLIENT BOTS ADMIN PANEL ---
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

# --- BOSH ADMIN PANEL (COMMAND & HANDLERLAR) ---
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

    await call.message.answer("📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan **xabaringizni** (tekst, rasm, va h.k.) yuboring:")
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

# --- ADMINLIKNI O'TKAZISH ---
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

# --- KARTA VA NARXLARNI TAHRIRLASH ---
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
        await call.message.answer("💵 Bot yaratish uchun **yangi narxni** kiriting (faqat raqam, masalan: 39990):")
        await state.set_state(MakerAdminFSM.waiting_create_price)
    elif act == "set_renew_price":
        await call.message.answer("🔄 Obunani uzaytirish uchun **yangi narxni** kiriting (faqat raqam):")
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

# --- TUGMALARNI TAHRIRLASH ---
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
    await call.message.answer(f"✏️ `{key}` uchun **yangi matnni** kiriting (masalan: `🤖 Yangi Bot Yaratish`):")
    await state.set_state(MakerAdminFSM.waiting_btn_val)
    await call.answer()

@dp.message(MakerAdminFSM.waiting_btn_val)
async def btn_edit_save(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("target_key")
    set_setting(key, msg.text.strip())
    await msg.answer("✅ Tugma matni muvaffaqiyatli o'zgartirildi!", reply_markup=main_maker_menu())
    await state.clear()

# --- ASOSIY MENYU XIZMATLARI (DYNAMIC MATCHING) ---
@dp.message(F.text.contains("100 ta Botlar Katalogi"))
async def show_catalog(msg: types.Message):
    text = "📚 **PRO MAX BOTLAR KATALOGI:**\n\n"
    for k in range(1, 11):
        text += f"🔹 **ID: {k}** — {BOT_TEMPLATES[k]['name']}\n"
    text += f"\n...va yana 90 ta maxsus bot shablonlari mavjud!"
    await msg.answer(text)

@dp.message(F.text.contains("Mening Botlarim"))
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

@dp.message(F.text.contains("Qo'llab-quvvatlash"))
async def support_info(msg: types.Message):
    admin_id = get_setting("admin_id", str(INITIAL_ADMIN_ID))
    await msg.answer(f"📞 Qo'llab-quvvatlash markazi admin ID: `{admin_id}`")

# --- BOT YARATISH OQIMI ---
@dp.message(F.text.contains("Bot Yaratish"))
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

    c_price = int(get_setting("create_price", "39990"))
    card_num = get_setting("card_number")
    card_holder = get_setting("card_holder")

    text = (
        f"💳 **TO'LOV QILISH BOSQICHI:**\n\n"
        f"💵 Narxi: **{c_price:,} so'm**\n"
        f"💳 Karta raqam: `{card_num}` ({card_holder})\n\n"
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

    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    try:
        if msg.photo:
            await maker_bot.send_photo(chat_id=admin_id, photo=photo_id, caption=caption, reply_markup=builder.as_markup())
        else:
            await maker_bot.send_document(chat_id=admin_id, document=photo_id, caption=caption, reply_markup=builder.as_markup())
        await msg.answer("⌛ Chek adminga yuborildi! Tasdiqlangach botingiz avtomatik ishga tushadi.")
        await state.clear()
    except Exception as e:
        logging.error(f"Error sending receipt: {e}")
        await msg.answer(f"⚠️ Xatolik yuz berdi:\n`{e}`")

# --- OBUNANI UZAYTIRISH OQIMI ---
@dp.message(F.text.contains("Obunani Uzaytirish"))
async def start_renew_process(msg: types.Message, state: FSMContext):
    await msg.answer("🔄 Obunasini uzaytirmoqchi bo'lgan **Bot ID**sini kiriting:")
    await state.set_state(RenewFSM.waiting_bot_id)

@dp.message(RenewFSM.waiting_bot_id)
async def process_renew_bot_id(msg: types.Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit():
        await msg.answer("❌ Noto'g'ri Bot ID. Faqat raqam kiriting:")
        return
    await state.update_data(renew_bot_id=int(msg.text))
    
    r_price = int(get_setting("renew_price", "11990"))
    card_num = get_setting("card_number")
    card_holder = get_setting("card_holder")
    expire_days = get_setting("expire_days", "17")

    text = (
        f"💳 **OBUNANI UZAYTIRISH TO'LOVI:**\n\n"
        f"💵 Narxi: **{r_price:,} so'm** (+{expire_days} kun)\n"
        f"💳 Karta raqam: `{card_num}` ({card_holder})\n\n"
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

    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    try:
        if msg.photo:
            await maker_bot.send_photo(chat_id=admin_id, photo=photo_id, caption=caption, reply_markup=builder.as_markup())
        else:
            await maker_bot.send_document(chat_id=admin_id, document=photo_id, caption=caption, reply_markup=builder.as_markup())
        await msg.answer("⌛ Chek adminga yuborildi! Tasdiqlangach obunangiz uzaytiriladi.")
        await state.clear()
    except Exception as e:
        logging.error(f"Error sending receipt: {e}")
        await msg.answer(f"⚠️ Admin botga xabar yuborishda xatolik:\n`{e}`")

# --- CALLBACK HANDLERLAR (TASDIQLASH VA RAD ETISH) ---
@dp.callback_query(F.data.startswith("approve_create:"))
async def approve_bot_creation(call: types.CallbackQuery):
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id:
        await call.answer("❌ Siz Bosh Admin emassiz!", show_alert=True)
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
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id:
        await call.answer("❌ Siz Bosh Admin emassiz!", show_alert=True)
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
    admin_id = int(get_setting("admin_id", str(INITIAL_ADMIN_ID)))
    if call.from_user.id != admin_id:
        await call.answer("❌ Siz Bosh Admin emassiz!", show_alert=True)
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

    # Webhook va eski so'rovlarni avtomatik tozalash
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
