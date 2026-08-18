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
# 1. SOZLAMALAR VA RENDER PORTI
# =====================================================================
MAKER_TOKEN = os.environ.get("MAKER_TOKEN", "8635436262:AAEmx_NdkOA1Ek9HaejFM2ivSpQplKUXz40")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 7849637859))  # Constructor Admin Telegram ID si
CARD_NUMBER = os.environ.get("CARD_NUMBER", "5440 8103 1990 4917")
CARD_HOLDER = os.environ.get("CARD_HOLDER", "g/n")

CREATE_PRICE = 39990
RENEW_PRICE = 11990
EXPIRE_DAYS = 17

PORT = int(os.environ.get("PORT", 8080))

maker_bot = Bot(token=MAKER_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Mijoz botlarini boshqarish uchun dinamik dispatcher va botlar lug'ati
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

class AdminBroadcastFSM(StatesGroup):
    waiting_message = State()

class AdminGiveBonusFSM(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()

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
    BOT_TEMPLATES[i] = {"name": f"⚡ Pro Max Specialized Template #{i}", "cat": "Sanoat va Xizmatlar"}

# =====================================================================
# 6. MIJOZ BOTLARI DISPATCHER VA HANDLERLARI
# =====================================================================
def init_client_db(db_id):
    conn = sqlite3.connect(f"client_data_{db_id}.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            balance INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0,
            level TEXT DEFAULT '🥉 Boshlang''ich',
            referred_by INTEGER
        )
    """)
    conn.commit()
    conn.close()

def build_client_dispatcher(db_id, admin_user, owner_id):
    c_dp = Dispatcher(storage=MemoryStorage())

    def get_user(u_id):
        conn = sqlite3.connect(f"client_data_{db_id}.db")
        cursor = conn.cursor()
        cursor.execute("SELECT balance, referrals, level FROM users WHERE user_id = ?", (u_id,))
        res = cursor.fetchone()
        conn.close()
        return res

    def add_user(u_id, fname, ref_id):
        conn = sqlite3.connect(f"client_data_{db_id}.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (u_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (user_id, full_name, balance, referrals, referred_by) VALUES (?, ?, 0, 0, ?)", (u_id, fname, ref_id))
            if ref_id and ref_id != u_id:
                cursor.execute("UPDATE users SET balance = balance + 5, referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False

    def get_top_users():
        conn = sqlite3.connect(f"client_data_{db_id}.db")
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, balance FROM users ORDER BY balance DESC LIMIT 10")
        res = cursor.fetchall()
        conn.close()
        return res

    def get_all_users():
        conn = sqlite3.connect(f"client_data_{db_id}.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [r[0] for r in cursor.fetchall()]
        conn.close()
        return users

    def update_balance(u_id, amount):
        conn = sqlite3.connect(f"client_data_{db_id}.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, u_id))
        conn.commit()
        conn.close()

    @c_dp.message(CommandStart())
    async def c_start(msg: types.Message):
        args = msg.text.split()
        ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
        add_user(msg.from_user.id, msg.from_user.full_name, ref_id)
        
        kb = ReplyKeyboardBuilder()
        kb.button(text="💎 Almaz ishlash")
        kb.button(text="🤝 Sheriklar")
        kb.button(text="⚙️ Telefonga Nastroyka")
        kb.button(text="📊 Profilim")
        kb.button(text="👑 Mening darajam")
        kb.button(text="🏆 Reyting")
        kb.button(text="🤝 Sherik Topish")
        kb.button(text="🛒 O'yin Do'koni")
        kb.button(text="🎬 Youtuber Xizmatlari")
        kb.button(text="🤖 Sun'iy Intellekt")
        
        if msg.from_user.id == owner_id:
            kb.button(text="🔑 Admin Panel")

        kb.adjust(2, 2, 2, 2, 2, 1)
        await msg.answer(f"👋 Salom {msg.from_user.full_name}!\n💎 **Almaz Bot Pro Max**ga xush kelibsiz!", reply_markup=kb.as_markup(resize_keyboard=True))

    @c_dp.message(F.text == "💎 Almaz ishlash")
    async def c_almaz(msg: types.Message, bot: Bot):
        me = await bot.get_me()
        await msg.answer(f"💎 **Almaz ishlash**\n\nSizning taklif havolangiz:\nhttps://t.me/{me.username}?start={msg.from_user.id}\n\nHar bir taklif qilgan do'stingiz uchun **5 almaz** beriladi!")

    @c_dp.message(F.text == "📊 Profilim")
    async def c_prof(msg: types.Message):
        u = get_user(msg.from_user.id)
        b, r, l = (u[0], u[1], u[2]) if u else (0, 0, "🥉 Boshlang'ich")
        await msg.answer(f"📊 **Sizning Profilingiz:**\n\n👤 Ism: **{msg.from_user.full_name}**\n🆔 ID: `{msg.from_user.id}`\n💎 Balans: **{b} almaz**\n👥 Referallar: **{r} ta**\n👑 Darajangiz: **{l}**")

    @c_dp.message(F.text == "⚙️ Telefonga Nastroyka")
    async def c_settings(msg: types.Message):
        await msg.answer("⚙️ **Telefonga Nastroyka Bo'limi:**\n\n🎮 Free Fire o'yini uchun eng yaxshi otish va sezgirlik (чувствительность) sozlamalari sizning qurilmangizga moslashtirildi!")

    @c_dp.message(F.text == "🤝 Sheriklar")
    async def c_partners(msg: types.Message):
        u = get_user(msg.from_user.id)
        r = u[1] if u else 0
        await msg.answer(f"🤝 **Sizning Sheriklaringiz:**\n\nSiz taklif qilgan jami do'stlar soni: **{r} ta**\nKo'proq do'st taklif qiling va bepul almazlarga ega bo'ling!")

    @c_dp.message(F.text == "👑 Mening darajam")
    async def c_level(msg: types.Message):
        u = get_user(msg.from_user.id)
        r = u[1] if u else 0
        if r < 5:
            lvl = "🥉 Boshlang'ich"
        elif r < 20:
            lvl = "🥈 Kumush O'yinchi"
        elif r < 50:
            lvl = "🥇 Oltin Chempion"
        else:
            lvl = "💎 Olmos Afsona"
        await msg.answer(f"👑 **Darajangiz:** {lvl}\n\nKeyingi darajaga o'tish uchun ko'proq do'stlaringizni taklif qiling!")

    @c_dp.message(F.text == "🏆 Reyting")
    async def c_top(msg: types.Message):
        top_users = get_top_users()
        text = "🏆 **TOP 10 ENG BOY O'YINCHILAR:**\n\n"
        for idx, user in enumerate(top_users, start=1):
            text += f"{idx}. {user[0]} — **{user[1]} almaz**\n"
        await msg.answer(text)

    @c_dp.message(F.text == "🤝 Sherik Topish")
    async def c_find_partner(msg: types.Message):
        await msg.answer("🎯 **O'yin uchun Sherik Topish:**\n\nBirga Free Fire yoki PUBG o'ynash uchun o'zingizga munosib jamoadosh qidiryapsizmi? Jamoadosh topish bo'limi tez orada yangilanadi!")

    @c_dp.message(F.text == "🛒 O'yin Do'koni")
    async def c_shop(msg: types.Message):
        b = InlineKeyboardBuilder()
        b.button(text="👨‍💻 Admin bilan bog'lanish", url=f"https://t.me/{admin_user}")
        await msg.answer("🛒 **O'yin Do'koni:**\n\n💎 100 Almaz — 15,000 so'm\n💎 310 Almaz — 42,000 so'm\n💎 520 Almaz — 70,000 so'm\n\nXarid qilish uchun admin bilan bog'laning:", reply_markup=b.as_markup())

    @c_dp.message(F.text == "🎬 Youtuber Xizmatlari")
    async def c_yt(msg: types.Message):
        await msg.answer("🎬 **Youtuberlar uchun Maxsus Xizmatlar:**\n\nKanalingizni rivojlantirish, obunachi yig'ish va video promo xizmatlari mavjud!")

    @c_dp.message(F.text == "🤖 Sun'iy Intellekt")
    async def c_ai(msg: types.Message):
        await msg.answer("🤖 **Sun'iy Intellekt (AI):**\n\nAI yordamchisi orqali o'yiningiz uchun taktika yoki istalgan savolingizga tezkor javob oling!")

    @c_dp.message(F.text == "🔑 Admin Panel")
    async def c_admin_panel(msg: types.Message):
        if msg.from_user.id != owner_id:
            return
        kb = ReplyKeyboardBuilder()
        kb.button(text="📊 Obunachilar Statistikasi")
        kb.button(text="➕ Almaz Qo'shish / Berish")
        kb.button(text="📢 Barchaga Xabar Yuborish")
        kb.button(text="🔙 Bosh menyu")
        kb.adjust(2, 1, 1)
        await msg.answer("🛠 **ADMIN PANEL:**\nKerakli bo'limni tanlang:", reply_markup=kb.as_markup(resize_keyboard=True))

    @c_dp.message(F.text == "📊 Obunachilar Statistikasi")
    async def c_admin_stats(msg: types.Message):
        if msg.from_user.id != owner_id:
            return
        users = get_all_users()
        await msg.answer(f"📊 **Bot Statistikasi:**\n\n👥 Umumiy obunachilar: **{len(users)} ta**")

    @c_dp.message(F.text == "📢 Barchaga Xabar Yuborish")
    async def c_admin_broadcast(msg: types.Message, state: FSMContext):
        if msg.from_user.id != owner_id:
            return
        await msg.answer("📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni kiriting:")
        await state.set_state(AdminBroadcastFSM.waiting_message)

    @c_dp.message(AdminBroadcastFSM.waiting_message)
    async def c_admin_send_broadcast(msg: types.Message, state: FSMContext, bot: Bot):
        users = get_all_users()
        count = 0
        for u_id in users:
            try:
                await bot.send_message(u_id, msg.text)
                count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
        await msg.answer(f"✅ Xabar **{count}** ta foydalanuvchiga muvaffaqiyatli yuborildi!")
        await state.clear()

    @c_dp.message(F.text == "➕ Almaz Qo'shish / Berish")
    async def c_admin_give_bonus(msg: types.Message, state: FSMContext):
        if msg.from_user.id != owner_id:
            return
        await msg.answer("👤 Almaz bermoqchi bo'lgan foydalanuvchining **Telegram ID**sini kiriting:")
        await state.set_state(AdminGiveBonusFSM.waiting_user_id)

    @c_dp.message(AdminGiveBonusFSM.waiting_user_id)
    async def c_admin_bonus_uid(msg: types.Message, state: FSMContext):
        if not msg.text.isdigit():
            await msg.answer("❌ Noto'g'ri ID. Raqam kiriting:")
            return
        await state.update_data(target_uid=int(msg.text))
        await msg.answer("💎 Qancha almaz qo'shmoqchisiz (Raqamda)?")
        await state.set_state(AdminGiveBonusFSM.waiting_amount)

    @c_dp.message(AdminGiveBonusFSM.waiting_amount)
    async def c_admin_bonus_amount(msg: types.Message, state: FSMContext, bot: Bot):
        if not msg.text.isdigit():
            await msg.answer("❌ Noto'g'ri miqdor. Raqam kiriting:")
            return
        data = await state.get_data()
        update_balance(data['target_uid'], int(msg.text))
        
        try:
            await bot.send_message(data['target_uid'], f"🎉 Admin tomonidan sizga **+{msg.text} almaz** berildi!")
        except Exception:
            pass
        
        await msg.answer(f"✅ ID `{data['target_uid']}` foydalanuvchiga **+{msg.text} almaz** berildi!")
        await state.clear()

    @c_dp.message(F.text == "🔙 Bosh menyu")
    async def c_back(msg: types.Message, state: FSMContext):
        await state.clear()
        await c_start(msg)

    return c_dp

async def register_and_start_client_bot(db_id, token, admin_user, owner_id):
    init_client_db(db_id)
    try:
        c_bot = Bot(token=token)
        c_dp = build_client_dispatcher(db_id, admin_user, owner_id)
        client_bots[db_id] = c_bot
        asyncio.create_task(c_dp.start_polling(c_bot))
        logging.info(f"Client bot #{db_id} muvaffaqiyatli ishga tushdi.")
    except Exception as e:
        logging.error(f"Client bot start error (ID: {db_id}): {e}")

async def start_all_user_bots():
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, bot_token, admin_username, template_id, owner_id FROM user_bots WHERE status = 'active'")
    bots = cursor.fetchall()
    conn.close()

    for b in bots:
        await register_and_start_client_bot(b[0], b[1], b[2], b[4])

# =====================================================================
# 7. MAKER BOT MENYULARI VA HANDLERLARI
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
        f"✨ Bu yerda siz **100 xildagi** professional Telegram botlarni atigi **39,990 so'm**ga yaratishingiz mumkin.\n"
        f"🔑 Har bir yaratilgan bot ichida to'liq **Admin Panel** bo'ladi!\n"
        f"⏱ Botlarning dastlabki ish muddati: **17 kun**.\n"
        f"🔁 Keyingi har 17 kun uchun to'lov: **11,990 so'm**.",
        reply_markup=main_maker_menu(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "📚 100 ta Botlar Katalogi")
async def show_catalog(msg: types.Message):
    text = "📚 **PRO MAX BOTLAR SHABLONLARI KATALOGI (TOP 10):**\n\n"
    for k in range(1, 11):
        text += f"🔹 **ID: {k}** — {BOT_TEMPLATES[k]['name']} (`{BOT_TEMPLATES[k]['cat']}`)\n"
    text += f"\n...va yana 90 ta maxsus bot shablonlari mavjud!\n\nBot yaratish uchun **'🤖 Bot Yaratish'** tugmasini bosing."
    await msg.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📂 Mening Botlarim")
async def my_bots(msg: types.Message):
    user_bots = get_user_bots_by_owner(msg.from_user.id)
    if not user_bots:
        await msg.answer("❌ Sizda hali yaratilgan botlar mavjud emas.")
        return
    text = "📂 **Sizning Botlaringiz:**\n\n"
    for b in user_bots:
        template_name = BOT_TEMPLATES.get(b[1], {}).get("name", f"Shablon #{b[1]}")
        text += f"🆔 **Bot ID:** `{b[0]}`\n🤖 **Tur:** {template_name}\n⏳ **Tugash sanasi:** {b[2]}\n📌 **Holat:** {b[3]}\n------------------------------\n"
    await msg.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📞 Qo'llab-quvvatlash")
async def support_info(msg: types.Message):
    await msg.answer("📞 Mutaxassis bilan bog'lanish va savollaringiz uchun admin: @AdminUsername")

@dp.message(F.text == "🤖 Bot Yaratish (39,990 so'm)")
async def start_bot_creation(msg: types.Message, state: FSMContext):
    await msg.answer("1️⃣ Yaratmoqchi bo'lgan botingiz **Shablon ID**sini kiriting (Masalan: `1` — Almaz bot):")
    await state.set_state(BotCreateFSM.waiting_template)

@dp.message(BotCreateFSM.waiting_template)
async def process_template_choice(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit() or int(msg.text) not in BOT_TEMPLATES:
        await msg.answer("❌ Noto'g'ri ID. 1 va 100 orasidagi raqam kiriting:")
        return
    await state.update_data(template_id=int(msg.text))
    await msg.answer("2️⃣ BotFather'dan olingan **Bot Token**ni yuboring:")
    await state.set_state(BotCreateFSM.waiting_token)

@dp.message(BotCreateFSM.waiting_token)
async def process_token_input(msg: types.Message, state: FSMContext):
    if ":" not in msg.text:
        await msg.answer("❌ Noto'g'ri Token formati. Qayta kiriting:")
        return
    await state.update_data(token=msg.text.strip())
    await msg.answer("3️⃣ O'zingizning Telegram **username**ingizni yuboring ('@' belgisiz):")
    await state.set_state(BotCreateFSM.waiting_admin_user)

@dp.message(BotCreateFSM.waiting_admin_user)
async def process_admin_user_input(msg: types.Message, state: FSMContext):
    clean_username = msg.text.strip().lstrip("@")
    await state.update_data(admin_user=clean_username)
    text = (
        f"💳 **TO'LOV QILISH BOSQICHI:**\n\n"
        f"💵 Narxi: **{CREATE_PRICE:,} so'm**\n"
        f"💳 Karta raqam: `{CARD_NUMBER}`\n"
        f"👤 Egasining ismi: **{CARD_HOLDER}**\n\n"
        f"📌 To'lovni amalga oshirgach, **TO'LOV CHEKI (Rasm/Skrinshot)**ini ushbu chatga yuboring:"
    )
    await msg.answer(text, parse_mode="Markdown")
    await state.set_state(BotCreateFSM.waiting_receipt)

@dp.message(BotCreateFSM.waiting_receipt, F.photo)
async def process_receipt_and_send_admin(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = msg.photo[-1].file_id
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash va Yaratish", callback_data=f"approve_create:{msg.from_user.id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject:{msg.from_user.id}")
    builder.adjust(1)
    
    caption = (
        f"📥 YANGI BOT YARATISH UCHUN TO'LOV CHEKI!\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name}\n"
        f"🆔 ID: {msg.from_user.id}\n"
        f"📌 Shablon ID: {data['template_id']}\n"
        f"🔑 Token: {data['token']}\n"
        f"👨‍💻 Admin Username: @{data['admin_user']}\n"
        f"💰 Summa: 39,990 so'm\n\n"
        f"To'lovni tasdiqlaysizmi?"
    )
    
    await maker_bot.send_photo(ADMIN_ID, photo_id, caption=caption, reply_markup=builder.as_markup())
    await msg.answer("⌛ **Chekingiz qabul qilindi!** Admin tekshirib tasdiqlagach, botingiz avtomatik ishga tushadi.", parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🔄 Obunani Uzaytirish (11,990 so'm)")
async def start_renew(msg: types.Message, state: FSMContext):
    await msg.answer("🔄 Obunani uzaytirmoqchi bo'lgan **Bot ID**ingizni kiriting (Mening Botlarim bo'limida ko'rishingiz mumkin):")
    await state.set_state(RenewFSM.waiting_bot_id)

@dp.message(RenewFSM.waiting_bot_id)
async def process_renew_bot_id(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit():
        await msg.answer("❌ Noto'g'ri ID. Faqat raqam kiriting:")
        return
    await state.update_data(renew_bot_id=int(msg.text))
    text = (
        f"💳 **OBUNANI UZAYTIRISH TO'LOVI:**\n\n"
        f"💵 Summa: **{RENEW_PRICE:,} so'm**\n"
        f"💳 Karta raqam: `{CARD_NUMBER}`\n"
        f"👤 Egasining ismi: **{CARD_HOLDER}**\n\n"
        f"📌 To'lovni amalga oshirgach, **TO'LOV CHEKI (Rasm/Skrinshot)**ini yuboring:"
    )
    await msg.answer(text, parse_mode="Markdown")
    await state.set_state(RenewFSM.waiting_receipt)

@dp.message(RenewFSM.waiting_receipt, F.photo)
async def process_renew_receipt(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = msg.photo[-1].file_id
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Obunani Uzaytirish", callback_data=f"approve_renew:{msg.from_user.id}:{data['renew_bot_id']}")
    builder.button(text="❌ Rad etish", callback_data=f"reject:{msg.from_user.id}")
    builder.adjust(1)
    
    caption = (
        f"🔄 OBUNANI UZAYTIRISH CHEKI!\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name}\n"
        f"🆔 User ID: {msg.from_user.id}\n"
        f"🤖 Bot ID: {data['renew_bot_id']}\n"
        f"💰 Summa: {RENEW_PRICE:,} so'm"
    )
    await maker_bot.send_photo(ADMIN_ID, photo_id, caption=caption, reply_markup=builder.as_markup())
    await msg.answer("⌛ **Chekingiz qabul qilindi!** Admin tasdiqlagach, bot muddati uzaytiriladi.", parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data.startswith("approve_create:"))
async def approve_bot_creation(call: types.CallbackQuery):
    owner_id = int(call.data.split(":")[1])
    caption = call.message.caption or ""
    
    try:
        template_match = re.search(r"Shablon ID:\s*(\d+)", caption)
        token_match = re.search(r"Token:\s*([^\s\n]+)", caption)
        admin_match = re.search(r"Admin Username:\s*@?([^\s\n]+)", caption)

        if not (template_match and token_match and admin_match):
            raise ValueError("Ma'lumotlar to'liq topilmadi")

        template_id = int(template_match.group(1))
        token = token_match.group(1).strip()
        admin_user = admin_match.group(1).strip().replace("@", "")

    except Exception as err:
        logging.error(f"Parsing error: {err}")
        await call.answer("❌ Chek matnini ajratishda xatolik yuz berdi!", show_alert=True)
        return

    bot_db_id, expire_date = add_user_bot(owner_id, token, admin_user, template_id)
    await register_and_start_client_bot(bot_db_id, token, admin_user, owner_id)
    
    template_name = BOT_TEMPLATES.get(template_id, {}).get('name', f"Shablon #{template_id}")
    await maker_bot.send_message(
        owner_id,
        f"🎉 **To'lovingiz tasdiqlandi va botingiz muvaffaqiyatli yaratildi!**\n\n"
        f"🤖 Bot shabloni: **{template_name}**\n"
        f"🔑 **Admin Panel:** Botingizga `/start` bosing va `🔑 Admin Panel` tugmasidan foydalaning!\n"
        f"⏱ Amal qilish muddati ({EXPIRE_DAYS} kun): **{expire_date}** gacha\n\n"
        f"Muddati tugashiga yaqin botni uzaytirish uchun **'🔄 Obunani Uzaytirish'** bo'limidan foydalaning.",
        parse_mode="Markdown"
    )
    await call.message.edit_caption(caption=caption + "\n\n✅ **ADMIN TARAFIDAN TASDIQLANDI VA BOT ISHGA TUSHDI!**")
    await call.answer("Tasdiqlandi va bot ishga tushirildi!", show_alert=True)

@dp.callback_query(F.data.startswith("approve_renew:"))
async def approve_bot_renew(call: types.CallbackQuery):
    parts = call.data.split(":")
    owner_id = int(parts[1])
    bot_id = int(parts[2])
    
    new_expire = extend_bot_subscription(bot_id)
    if new_expire:
        await maker_bot.send_message(
            owner_id,
            f"🎉 **Bot obunasi muvaffaqiyatli uzaytirildi!**\n\n"
            f"🤖 Bot ID: **{bot_id}**\n"
            f"⏱ Yangi tugash muddati: **{new_expire}**",
            parse_mode="Markdown"
        )
        await call.message.edit_caption(caption=(call.message.caption or "") + f"\n\n✅ **OBUNA {new_expire} GACHA UZAYTIRILDI!**")
        await call.answer("Uzaytirildi!", show_alert=True)
    else:
        await call.answer("❌ Bot topilmadi!", show_alert=True)

@dp.callback_query(F.data.startswith("reject:"))
async def reject_payment(call: types.CallbackQuery):
    owner_id = int(call.data.split(":")[1])
    await maker_bot.send_message(owner_id, "❌ **To'lovingiz rad etildi.** Chek xato yoki to'lov kelib tushmadi.", parse_mode="Markdown")
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n❌ **RAD ETILDI.**")
    await call.answer("Rad etildi!", show_alert=True)

# =====================================================================
# 8. DASTURNI ISHGA TUSHIRISH (MAIN)
# =====================================================================
async def main():
    init_db()
    await start_dummy_server()  # Render Web Service uchun port tayyorlash
    await start_all_user_bots()
    logging.info("PRO MAX Bot Constructor muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(maker_bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi!")
    except Exception as e:
        logging.error(f"Xatolik yuz berdi: {e}")
