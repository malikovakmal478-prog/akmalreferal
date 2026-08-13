import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

API_TOKEN = '8805365427:AAFqqCpa8NWXRZ9lo1pJlmH_ozqZm1rQCf4'
ADMIN_ID = 7915255052  # O'zingizning Telegram ID'ingizni kiriting

# Majburiy obuna kanallari
CHANNELS = ["@d1ma_sultanov", "@dima_almazlar", "@ffuzbkzorg"]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- DATABASE (MA'LUMOTLAR BAZASI) ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            almaz INTEGER DEFAULT 0,
            ff_id TEXT DEFAULT 'Kiritilmagan',
            ref_by INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- STATES (FSM) ---
class Form(StatesGroup):
    waiting_ff_id = State()
    waiting_broadcast = State()

# --- OBUNANI TEKSHIRISH FUNKSIYASI ---
async def check_sub(user_id: int) -> bool:
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            # Agar bot kanalda admin bo'lmasa yoki xatolik bo'lsa
            pass
    return True

# --- KLAVIATURALAR ---
def get_sub_keyboard():
    keyboard = []
    for channel in CHANNELS:
        channel_name = channel.replace("@", "")
        keyboard.append([InlineKeyboardButton(text=f"➕ {channel}", url=f"https://t.me/{channel_name}")])
    keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🤖 Sun'iy Intellekt")],
        [KeyboardButton(text="💎 Almaz ishlash"), KeyboardButton(text="🤝 Sheriklar")],
        [KeyboardButton(text="⚙️ Telefonga Nastroyka"), KeyboardButton(text="📊 Profilim")],
        [KeyboardButton(text="🏅 Mening darajam"), KeyboardButton(text="🏆 Reyting")],
        [KeyboardButton(text="🤝 Sherik Topish"), KeyboardButton(text="🛒 O'yin Do'koni")]
    ],
    resize_keyboard=True
)

ai_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🤖 AI Suhbat")],
        [KeyboardButton(text="🎭 Personaj Ovozida AI")],
        [KeyboardButton(text="✨ Nickname Yaratish")],
        [KeyboardButton(text="⬅️ Orqaga")]
    ],
    resize_keyboard=True
)

shop_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💎 To'g'ridan-to'g'ri yechish")],
        [KeyboardButton(text="🎁 Naborlar"), KeyboardButton(text="🏃 Emotsiyalar")],
        [KeyboardButton(text="🛡️ Stenkalar & Skinlar")],
        [KeyboardButton(text="🧾 Mening Buyurtmalarim")],
        [KeyboardButton(text="⬅️ Orqaga")]
    ],
    resize_keyboard=True
)

admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📢 Xabar yuborish (Broadcast)")],
        [KeyboardButton(text="⬅️ Orqaga")]
    ],
    resize_keyboard=True
)

# --- HANDLERLAR ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    # Majburiy obunani tekshirish
    if not await check_sub(user_id):
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling va Tekshirish tugmasini bosing:",
            reply_markup=get_sub_keyboard()
        )
        return

    await register_and_welcome(message)
async def register_and_welcome(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Mavjud emas"
    
    args = message.text.split() if message.text else []
    ref_by = 0
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_by = int(args[1].replace("ref_", ""))
        except ValueError:
            ref_by = 0

    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute('INSERT INTO users (user_id, username, ref_by) VALUES (?, ?, ?)', (user_id, username, ref_by))
        if ref_by and ref_by != user_id:
            cursor.execute('UPDATE users SET almaz = almaz + 1 WHERE user_id = ?', (ref_by,))
            try:
                await bot.send_message(ref_by, "🎉 Siz yangi do'st taklif qildingiz va +1 Almaz berildi!")
            except Exception:
                pass
        conn.commit()
    conn.close()

    text = f"✨ Xush kelibsiz, {message.from_user.first_name}!\n\nSiz barcha tekshiruvlardan muvaffaqiyatli o'tdingiz — endi botning barcha imkoniyatlari ochildi. 🚀\n\nQuyidagi menyudan keragini tanlang 👇"
    await message.answer(text, reply_markup=main_menu)

@dp.callback_query(F.data == "check_subscription")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ Rahmat! Barcha kanallarga obuna bo'ldingiz.")
        await register_and_welcome(callback.message)
    else:
        await callback.answer("❌ Siz hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)

# Admin panelga kirish
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_menu)

@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        conn.close()

        await message.answer(f"📈 Bot Statistikasi:\n\n👤 Jami a'zolar soni: {total_users} ta")

@dp.message(F.text == "📢 Xabar yuborish (Broadcast)")
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing:")
        await state.set_state(Form.waiting_broadcast)

@dp.message(Form.waiting_broadcast)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        conn.close()

        count = 0
        for user in users:
            try:
                await bot.send_message(user[0], message.text)
                count += 1
            except Exception:
                pass
        await message.answer(f"✅ Xabar {count} ta foydalanuvchiga muvaffaqiyatli yuborildi.")
        await state.clear()

# Menyu bosilganda
@dp.message(F.text == "⬅️ Orqaga")
async def back_to_main(message: types.Message):
    await message.answer("🏠 Bosh menyuga qaytdingiz", reply_markup=main_menu)

@dp.message(F.text == "🤖 Sun'iy Intellekt")
async def ai_section(message: types.Message):
    text = "🤖 Sun'iy Intellekt markazi\n\nBu yerda siz Free Fire bo'yicha eng professional AI xizmatlaridan foydalana olasiz.\n\n👇 Quyidagi bo'limlardan birini tanlang:"
    await message.answer(text, reply_markup=ai_menu)
@dp.message(F.text == "📊 Profilim")
async def profile_section(message: types.Message):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT almaz, ff_id FROM users WHERE user_id = ?', (message.from_user.id,))
    user = cursor.fetchone()
    conn.close()

    almaz = user[0] if user else 0
    ff_id = user[1] if user else "Kiritilmagan"
    username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"

    text = (
        f"👤 Profilingiz\n\n"
        f"👤 Username: {username}\n"
        f"🎮 Free Fire ID: {ff_id}\n"
        f"🥇 Liga: 🥉 Bronze liga\n"
        f"📊 Reyting ballari: 0\n"
        f"💎 Almaz: {almaz}\n\n"
        f"Almazlaringizni istagan paytda yechib olishingiz mumkin 👇"
    )

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Almazni yechish", callback_data="withdraw"), InlineKeyboardButton(text="🆔 FF ID sozlash", callback_data="set_ff_id")]
    ])

    await message.answer(text, reply_markup=inline_kb)

@dp.callback_query(F.data == "set_ff_id")
async def ask_ff_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎮 Free Fire ID raqamingizni kiriting:")
    await state.set_state(Form.waiting_ff_id)
    await callback.answer()

@dp.message(Form.waiting_ff_id)
async def save_ff_id(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET ff_id = ? WHERE user_id = ?', (message.text, message.from_user.id))
    conn.commit()
    conn.close()

    await message.answer(f"✅ FF ID muvaffaqiyatli saqlandi: {message.text}", reply_markup=main_menu)
    await state.clear()

@dp.message(F.text == "💎 Almaz ishlash")
async def ref_link(message: types.Message):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    text = (
        f"👇 Sizning shaxsiy taklif havolangiz:\n{link}\n\n"
        f"🔥 Qancha ko'p do'st — shuncha ko'p Almaz!\n"
        f"Bugunoq boshlang — natija darhol ko'rina boshlaydi! 💎😎"
    )
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📫 Do'stlarga ulashish", switch_inline_query=link)]
    ])
    await message.answer(text, reply_markup=inline_kb)

@dp.message(F.text == "⚙️ Telefonga Nastroyka")
async def nastroyka(message: types.Message):
    text = (
        "⚙️ Telefonga mos Free Fire sozlamalari\n\n"
        "📱 Telefon modelini kiriting:\n"
        "Masalan: Redmi Note 9, Samsung A12, iPhone 11\n\n"
        "❗ Telefon nomini to'g'ri yozing!"
    )
    await message.answer(text)

@dp.message(F.text == "🛒 O'yin Do'koni")
async def shop(message: types.Message):
    await message.answer("🛒 FF Market & Exchange\n\nKategoriyani tanlang:", reply_markup=shop_menu)

# Botni ishga tushirish
async def main():
    await dp.start_polling(bot)

if name == 'main':
    asyncio.run(main())
