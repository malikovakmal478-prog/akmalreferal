import asyncio
import logging
import sqlite3
import sys
import subprocess
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# =====================================================================
# 1. SOZLAMALAR
# =====================================================================
MAKER_TOKEN = "8635436262:AAHdexSxyGVWNXHcAZ_EaNEvzt4zzqFFh70"
ADMIN_ID = 7849637859  # Admin Telegram ID
CARD_NUMBER = "5440 8103 1990 4917"
CARD_HOLDER = "G/N"

CREATE_PRICE = 39990
RENEW_PRICE = 9990
EXPIRE_DAYS = 17

maker_bot = Bot(token=MAKER_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# =====================================================================
# 2. FSM HOLATLARI
# =====================================================================
class BotCreateFSM(StatesGroup):
    waiting_template = State()
    waiting_token = State()
    waiting_admin_user = State()
    waiting_receipt = State()

class RenewFSM(StatesGroup):
    waiting_bot_id = State()
    waiting_receipt = State()

# =====================================================================
# 3. MA'LUMOTLAR BAZASI
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
        current_expire = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        start_date = max(current_expire, datetime.now())
        new_expire = (start_date + timedelta(days=EXPIRE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE user_bots SET expire_date = ?, status = 'active' WHERE id = ?", (new_expire, bot_id))
        conn.commit()
        conn.close()
        return new_expire
    conn.close()
    return None

# =====================================================================
# 4. 100 TA PRO MAX BOT SHABLONLARI TIZIMI
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

def build_client_bot_code(token, admin_user, template_id, db_id):
    return f'''# -*- coding: utf-8 -*-
import asyncio, sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

API_TOKEN = "{token}"
ADMIN_USERNAME = "{admin_user}"
REF_BONUS = 5

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect("client_data_{db_id}.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, full_name TEXT, balance INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0, level TEXT DEFAULT '🥉 Boshlang''ich', referred_by INTEGER
        )
    """)
    conn.commit()
    conn.close()

def get_user(u_id):
    conn = sqlite3.connect("client_data_{db_id}.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, referrals, level FROM users WHERE user_id = ?", (u_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def add_user(u_id, fname, ref_id):
    conn = sqlite3.connect("client_data_{db_id}.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (u_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, full_name, balance, referrals, referred_by) VALUES (?, ?, 0, 0, ?)", (u_id, fname, ref_id))
        if ref_id and ref_id != u_id:
            cursor.execute("UPDATE users SET balance = balance + ?, referrals = referrals + 1 WHERE user_id = ?", (REF_BONUS, ref_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

@dp.message(CommandStart())
async def start(msg: types.Message):
    args = msg.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    add_user(msg.from_user.id, msg.from_user.full_name, ref_id)
    
    kb = ReplyKeyboardBuilder()
    kb.button(text="💎 Almaz ishlash"); kb.button(text="🤝 Sheriklar")
    kb.button(text="⚙️ Telefonga Nastroyka"); kb.button(text="📊 Profilim")
    kb.button(text="👑 Mening darajam"); kb.button(text="🏆 Reyting")
    kb.button(text="🤝 Sherik Topish"); kb.button(text="🛒 O'yin Do'koni")
    kb.button(text="🎬 Youtuber Xizmatlari"); kb.button(text="🤖 Sun'iy Intellekt")
    kb.adjust(2, 1, 2, 2, 2, 1)
    
    await msg.answer(f"👋 Salom {{msg.from_user.full_name}}!\\n💎 **Almaz Bot Pro Max** xush kelibsiz!", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text == "💎 Almaz ishlash")
async def almaz(msg: types.Message):
    me = await bot.get_me()
    await msg.answer(f"💎 **Almaz ishlash**\\n\\nSizning havolangiz:\\n`https://t.me/{{me.username}}?start={{msg.from_user.id}}`\\n\\nTaklif uchun: **{{REF_BONUS}} almaz**", parse_mode="Markdown")

@dp.message(F.text == "📊 Profilim")
async def prof(msg: types.Message):
    u = get_user(msg.from_user.id)
    b, r, l = (u[0], u[1], u[2]) if u else (0, 0, "Boshlang'ich")
    await msg.answer(f"📊 **Profil:**\\n💎 Balans: {{b}}\\n👥 Referallar: {{r}}\\n👑 Daraja: {{l}}")

@dp.message(F.text == "🛒 O'yin Do'koni")
async def shop(msg: types.Message):
    b = InlineKeyboardBuilder()
    b.button(text="👨‍💻 Admin bilan bog'lanish", url="https://t.me/{admin_user}")
    await msg.answer("🛒 **Do'kon:**\\n100 Almaz - 15,000 so'm", reply_markup=b.as_markup())

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
'''

# =====================================================================
# 5. MENYULAR VA TUGMALAR
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

# =====================================================================
# 6. HANDLERLAR VA TO'LOV MANTIQLARI
# =====================================================================
@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    await msg.answer(
        f"🚀 **PRO MAX BOT CONSTRUCTOR**ga xush kelibsiz!\n\n"
        f"✨ Bu yerda siz **100 xildagi** eng professional Telegram botlarni atigi **39,990 so'm**ga yaratishingiz mumkin.\n"
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
        await msg.answer("❌ Noto'g'ri Token format. Qayta kiriting:")
        return
    await state.update_data(token=msg.text.strip())
    await msg.answer("3️⃣ O'zingizning Telegram **username**ingizni yuboring ('@' belgisiz):")
    await state.set_state(BotCreateFSM.waiting_admin_user)

@dp.message(BotCreateFSM.waiting_admin_user)
async def process_admin_user_input(msg: types.Message, state: FSMContext):
    await state.update_data(admin_user=msg.text.strip().replace("@", ""))
    
    text = (
        f"💳 **TO'LOV QILISH BASQICHI:**\n\n"
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
        f"📥 **YANGI BOT YARATISH UCHUN TO'LOV CHEKI!**\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name} (@{msg.from_user.username})\n"
        f"🪪 ID: `{msg.from_user.id}`\n"
        f"🤖 Shablon ID: **{data['template_id']}** ({BOT_TEMPLATES[data['template_id']]['name']})\n"
        f"🔑 Token: `{data['token']}`\n"
        f"👨‍💻 Admin Username: @{data['admin_user']}\n"
        f"💰 Summa: **39,990 so'm**\n\n"
        f"Shuncha to'ladi. To'lovni tasdiqlaysizmi?"
    )
    
    await maker_bot.send_photo(ADMIN_ID, photo_id, caption=caption, parse_mode="Markdown", reply_markup=builder.as_markup())
    await msg.answer("⌛ **Chekingiz qabul qilindi!** Admin tekshirib tasdiqlagach, botingiz avtomatik ishga tushadi.")
    await state.clear()

# =====================================================================
# 7. ADMIN TASDIQLASH CALLBACKI (TUZATILGAN QISM)
# =====================================================================
@dp.callback_query(F.data.startswith("approve_create:"))
async def approve_bot_creation(call: types.CallbackQuery):
    owner_id = int(call.data.split(":")[1])
    caption = call.message.caption or ""
    
    # Text parse jarayonini xatosiz va xavfsiz amalga oshirish
    try:
        template_id = int(caption.split("Shablon ID: **")[1].split("**")[0])
        token = caption.split("Token: `")[1].split("`")[0]
        admin_user = caption.split("Admin Username: @")[1].split("\n")[0]
    except Exception as err:
        await call.answer("❌ Chek matnini ajratishda xatolik yuz berdi!", show_alert=True)
        return

    # Bazaga saqlash
    bot_db_id, expire_date = add_user_bot(owner_id, token, admin_user, template_id)
    
    # Bot kodi faylini yaratish va fonda ishga tushirish
    file_name = f"user_bot_{bot_db_id}.py"
    code = build_client_bot_code(token, admin_user, template_id, bot_db_id)
    
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(code)
        
    subprocess.Popen([sys.executable, file_name])
    
    # Foydalanuvchiga xabar yuborish
    await maker_bot.send_message(
        owner_id,
        f"🎉 **To'lovingiz tasdiqlandi va botingiz muvaffaqiyatli yaratildi!**\n\n"
        f"🤖 Bot shabloni: **{BOT_TEMPLATES[template_id]['name']}**\n"
        f"⏱ Amal qilish muddati (17 kun): **{expire_date}** gacha\n\n"
        f"Muddati tugashiga yaqin botni uzaytirish uchun **'🔄 Obunani Uzaytirish'** bo'limidan foydalaning.",
        parse_mode="Markdown"
    )
    await call.message.edit_caption(caption=caption + "\n\n✅ **ADMIN TARAFIDAN TASDIQLANDI VA BOT ISHGA TUSHDI!**")
    await call.answer("Tasdiqlandi va bot ishga tushirildi!")

@dp.callback_query(F.data.startswith("reject:"))
async def reject_payment(call: types.CallbackQuery):
    owner_id = int(call.data.split(":")[1])
    await maker_bot.send_message(owner_id, "❌ **To'lovingiz rad etildi.** Chek xato yoki to'lov kelib tushmadi.")
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n❌ **RAD ETILDI.**")
    await call.answer("Rad etildi!")

# =====================================================================
# 8. OBUNANI UZAYTIRISH (17 KUN / 11,990 SO'M)
# =====================================================================
@dp.message(F.text == "🔄 Obunani Uzaytirish (11,990 so'm)")
async def renew_start(msg: types.Message, state: FSMContext):
    conn = sqlite3.connect("constructor_promax.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, template_id, expire_date FROM user_bots WHERE owner_id = ?", (msg.from_user.id,))
    bots = cursor.fetchall()
    conn.close()

    if not bots:
        await msg.answer("❌ Sizda hali yaratilgan botlar mavjud emas.")
        return

    text = "📂 **Sizning botlaringiz:**\n\n"
    for b in bots:
        text += f"🆔 **Bot ID: {b[0]}** | Shablon: {BOT_TEMPLATES[b[1]]['name']}\n⏱ Muddat: `{b[2]}`\n\n"
    text += "Qaysi Bot ID'si uchun obunani uzaytirmoqchisiz? Bot ID'sini kiriting:"
    
    await msg.answer(text, parse_mode="Markdown")
    await state.set_state(RenewFSM.waiting_bot_id)

@dp.message(RenewFSM.waiting_bot_id)
async def renew_bot_id(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit():
        await msg.answer("❌ Bot ID raqam bo'lishi kerak. Qayta kiriting:")
        return
    await state.update_data(renew_bot_id=int(msg.text))
    
    text = (
        f"💳 **17 KUNLIK OBUNANI UZAYTIRISH TO'LOVI:**\n\n"
        f"💵 Narxi: **{RENEW_PRICE:,} so'm**\n"
        f"💳 Karta raqam: `{CARD_NUMBER}`\n"
        f"👤 Egasining ismi: **{CARD_HOLDER}**\n\n"
        f"📌 To'lovni amalga oshirib, **TO'LOV CHEKI (Rasm)**ni ushbu chatga yuboring:"
    )
    await msg.answer(text, parse_mode="Markdown")
    await state.set_state(RenewFSM.waiting_receipt)

@dp.message(RenewFSM.waiting_receipt, F.photo)
async def process_renew_receipt(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = msg.photo[-1].file_id
    bot_id = data['renew_bot_id']

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Obunani 17 kunga uzaytirish", callback_data=f"approve_renew:{bot_id}:{msg.from_user.id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject:{msg.from_user.id}")
    builder.adjust(1)

    caption = (
        f"🔄 **BOT OBUNASINI UZAYTIRISH CHEKI!**\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name}\n"
        f"🆔 Bot ID: **{bot_id}**\n"
        f"💰 Summa: **11,990 so'm**\n\n"
        f"Tasdiqlaysizmi?"
    )
    await maker_bot.send_photo(ADMIN_ID, photo_id, caption=caption, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await msg.answer("⌛ **Chekingiz adminga yuborildi.** Tasdiqlangach obunangiz uzaytiriladi.")
    await state.clear()

@dp.callback_query(F.data.startswith("approve_renew:"))
async def approve_renew_callback(call: types.CallbackQuery):
    _, bot_id, owner_id = call.data.split(":")
    new_expire = extend_bot_subscription(int(bot_id))

    await maker_bot.send_message(
        int(owner_id),
        f"🎉 **Botingiz obunasi muvaffaqiyatli 17 kunga uzaytirildi!**\n\n"
        f"🆔 Bot ID: {bot_id}\n"
        f"🗓 Yangi tugash muddati: **{new_expire}**",
        parse_mode="Markdown"
    )
    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n✅ **OBUNA UZAYTIRILDI!**")
    await call.answer("Obuna uzaytirildi!")

# =====================================================================
# 9. DASTURNI ISHGA TUSHIRISH
# =====================================================================
async def main():
    init_db()
    print("PRO MAX Bot Constructor muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(maker_bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Xatolik: {e}")
