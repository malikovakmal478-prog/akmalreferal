import asyncio
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# !!! SOZLAMALAR !!!
API_TOKEN = "8635436262:AAHdexSxyGVWNXHcAZ_EaNEvzt4zzqFFh70"
ADMIN_CARD = "5440810319904917"
ADMIN_USERNAME = "Akmaljon1100"  # '@' belgisiz yozing

main_bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
active_bot_tasks = {}

# --- 1. MA'LUMOTLAR BAZASI ---
def init_db():
    conn = sqlite3.connect("constructor.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bot_token TEXT UNIQUE,
            bot_type TEXT,
            created_at TEXT,
            expires_at TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            bot_token TEXT,
            movie_code TEXT,
            file_id TEXT,
            caption TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ref_users (
            bot_token TEXT,
            user_id INTEGER,
            balance INTEGER DEFAULT 0,
            referred_by INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            bot_token TEXT PRIMARY KEY,
            sub_channel TEXT,
            ref_bonus INTEGER DEFAULT 5,
            min_withdraw INTEGER DEFAULT 210
        )
    """)
    conn.commit()
    conn.close()

class BotCreation(StatesGroup):
    entering_token = State()

class MovieState(StatesGroup):
    waiting_code = State()
    waiting_file = State()

class SettingsState(StatesGroup):
    waiting_channel = State()
    waiting_min_withdraw = State()

# --- MAJBURIY OBUNA TEKSHIRUVI ---
async def check_subscription(bot: Bot, user_id: int, channel: str) -> bool:
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception:
        pass
    return False

# --- 2. FOYDALANUVCHI BOTLARINI ISHGA TUSHIRISH ---
async def start_user_bot(token: str, bot_type: str, owner_id: int):
    try:
        sub_bot = Bot(token=token)
        sub_dp = Dispatcher()
        router = Router()

        def get_settings():
            conn = sqlite3.connect("constructor.db")
            cursor = conn.cursor()
            cursor.execute("SELECT sub_channel, ref_bonus, min_withdraw FROM bot_settings WHERE bot_token = ?", (token,))
            res = cursor.fetchone()
            if not res:
                cursor.execute("INSERT INTO bot_settings (bot_token, sub_channel, ref_bonus, min_withdraw) VALUES (?, '', 5, 210)", (token,))
                conn.commit()
                res = ("", 5, 210)
            conn.close()
            return res

        # KINO BOT MANTIQLARI
        if bot_type == "Kodli Kino Bot":
            def kino_menu():
                kb = ReplyKeyboardBuilder()
                kb.button(text="🔍 Kino qidirish")
                kb.button(text="⚙️ Admin Panel")
                kb.adjust(1, 1)
                return kb.as_markup(resize_keyboard=True)

            @router.message(CommandStart())
            async def kino_start(message: types.Message):
                settings = get_settings()
                channel = settings[0]
                if channel and not await check_subscription(sub_bot, message.from_user.id, channel):
                    kb = InlineKeyboardBuilder()
                    kb.button(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{channel.replace('@','')}")
                    kb.button(text="✅ Obunani tekshirish", callback_data="check_kino_sub")
                    await message.answer(f"⚠️ Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:\n{channel}", reply_markup=kb.as_markup())
                    return
                await message.answer("🎬 **Kino Botga xush kelibsiz!**\nKino kodini yuboring (Masalan: `30224030`):", reply_markup=kino_menu(), parse_mode="Markdown")

            @router.callback_query(F.data == "check_kino_sub")
            async def check_kino_sub_cb(call: types.CallbackQuery):
                settings = get_settings()
                if await check_subscription(sub_bot, call.from_user.id, settings[0]):
                    await call.message.edit_text("✅ Obuna tasdiqlandi! Kino kodini yuboring:")
                else:
                    await call.answer("❌ Hali kanalga a'zo bo'lmadingiz!", show_alert=True)

            @router.message(F.text == "⚙️ Admin Panel")
            @router.message(Command("admin"))
            async def kino_admin(message: types.Message):
                if message.from_user.id != owner_id:
                    return
                kb = InlineKeyboardBuilder()
                kb.button(text="➕ Kino qo'shish", callback_data="add_movie")
                kb.button(text="📢 Majburiy obuna sozlash", callback_data="set_sub")
                kb.adjust(1)
                await message.answer("🛠️ **Kino Bot Admin Paneli:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

            @router.callback_query(F.data == "add_movie")
            async def add_movie_start(call: types.CallbackQuery, state: FSMContext):
                await state.set_state(MovieState.waiting_code)
                await call.message.answer("Kino uchun kod kiriting (masalan: 30224030):")

            @router.message(MovieState.waiting_code)
            async def set_code(message: types.Message, state: FSMContext):
                await state.update_data(m_code=message.text)
                await state.set_state(MovieState.waiting_file)
                await message.answer("Endi kinoning video faylini yuboring:")

            @router.message(MovieState.waiting_file, F.video)
            async def set_file(message: types.Message, state: FSMContext):
                data = await state.get_data()
                conn = sqlite3.connect("constructor.db")
                cursor = conn.cursor()
                cursor.execute("INSERT INTO movies VALUES (?, ?, ?, ?)", (token, data['m_code'], message.video.file_id, message.caption or ""))
                conn.commit()
                conn.close()
                await message.answer(f"✅ Kino saqlandi! Kodi: `{data['m_code']}`", parse_mode="Markdown")
                await state.clear()

            @router.callback_query(F.data == "set_sub")
            async def set_sub_channel(call: types.CallbackQuery, state: FSMContext):
                await state.set_state(SettingsState.waiting_channel)
                await call.message.answer("Majburiy obuna kanali usernamesini kiriting (masalan: @kanal_nomi):")

            @router.message(SettingsState.waiting_channel)
            async def save_sub_channel(message: types.Message, state: FSMContext):
                conn = sqlite3.connect("constructor.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE bot_settings SET sub_channel = ? WHERE bot_token = ?", (message.text.strip(), token))
                conn.commit()
                conn.close()
                await message.answer("✅ Majburiy obuna kanali yangilandi!")
                await state.clear()

            @router.message(F.text.isdigit())
            async def get_movie(message: types.Message):
                conn = sqlite3.connect("constructor.db")
                cursor = conn.cursor()
                cursor.execute("SELECT file_id, caption FROM movies WHERE bot_token = ? AND movie_code = ?", (token, message.text))
                movie = cursor.fetchone()
                conn.close()
                if movie:
                    await sub_bot.send_video(message.chat.id, video=movie[0], caption=movie[1])
                else:
                    await message.answer("❌ Bu kod bo'yicha kino topilmadi.")

        # REFERRAL BOT MANTIQLARI
        elif bot_type == "Referral Bot":
            def ref_menu():
                kb = ReplyKeyboardBuilder()
                kb.button(text="🔗 Taklif havolam")
                kb.button(text="💎 Balans / Almoslar")
                kb.button(text="📤 Pulni yechib olish")
                kb.button(text="⚙️ Admin Panel")
                kb.adjust(2, 2)
                return kb.as_markup(resize_keyboard=True)

            @router.message(CommandStart())
            async def ref_start(message: types.Message):
                settings = get_settings()
                channel = settings[0]
                if channel and not await check_subscription(sub_bot, message.from_user.id, channel):
                    kb = InlineKeyboardBuilder()
                    kb.button(text="📢 Kanalga a'zo bo'lish", url=f"https://t.me/{channel.replace('@','')}")
                    kb.button(text="✅ Obunani tekshirish", callback_data="check_ref_sub")
                    await message.answer(f"⚠️ Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:\n{channel}", reply_markup=kb.as_markup())
                    return

                args = message.text.split()
                user_id = message.from_user.id
                conn = sqlite3.connect("constructor.db")
                cursor = conn.cursor()
                cursor.execute("SELECT balance FROM ref_users WHERE bot_token = ? AND user_id = ?", (token, user_id))
                res = cursor.fetchone()
                
                if not res:
                    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
                    cursor.execute("INSERT INTO ref_users VALUES (?, ?, 0, ?)", (token, user_id, ref_id))
                    if ref_id and ref_id != user_id:
                        bonus = settings[1]
                        cursor.execute("UPDATE ref_users SET balance = balance + ? WHERE bot_token = ? AND user_id = ?", (bonus, token, ref_id))
                        try:
                            await sub_bot.send_message(ref_id, f"🎉 Do'stingiz qo'shildi! Sizga **{bonus} almos** berildi.", parse_mode="Markdown")
                        except Exception:
                            pass
                    conn.commit()
                conn.close()
                await message.answer("💎 **Referral Botga xush kelibsiz!**", reply_markup=ref_menu(), parse_mode="Markdown")

            @router.callback_query(F.data == "check_ref_sub")
            async def check_ref_sub_cb(call: types.CallbackQuery):
                settings = get_settings()
                if await check_subscription(sub_bot, call.from_user.id, settings[0]):
                    await call.message.edit_text("✅ Obuna tasdiqlandi! Qaytadan /start bosing.")
                else:
                    await call.answer("❌ Hali kanalga a'zo bo'lmadingiz!", show_alert=True)

            @router.message(F.text == "⚙️ Admin Panel")
            @router.message(Command("admin"))
            async def ref_admin(message: types.Message):
                if message.from_user.id != owner_id:
                    return
                settings = get_settings()
                kb = InlineKeyboardBuilder()
                kb.button(text="✏️ Min. yechishni o'zgartirish", callback_data="set_min_w")
                kb.button(text="📢 Majburiy obuna sozlash", callback_data="set_ref_sub")
                kb.adjust(1)
                await message.answer(f"🛠️ **Referral Admin Paneli:**\n\n- Har bir taklif: {settings[1]} almos\n- Min. yechish: {settings[2]} almos", reply_markup=kb.as_markup(), parse_mode="Markdown")

            @router.callback_query(F.data == "set_min_w")
            async def set_min_w_start(call: types.CallbackQuery, state: FSMContext):
                await state.set_state(SettingsState.waiting_min_withdraw)
                await call.message.answer("Yangi minimal yechish miqdorini kiriting (masalan: 210):")

            @router.message(SettingsState.waiting_min_withdraw)
            async def save_min_w(message: types.Message, state: FSMContext):
                if message.text.isdigit():
                    conn = sqlite3.connect("constructor.db")
                    cursor = conn.cursor()
                    cursor.execute("UPDATE bot_settings SET min_withdraw = ? WHERE bot_token = ?", (int(message.text), token))
                    conn.commit()
                    conn.close()
                    await message.answer("✅ Minimal yechish miqdori yangilandi!")
                    await state.clear()
                else:
                    await message.answer("Faqat raqam kiriting!")

            @router.callback_query(F.data == "set_ref_sub")
            async def set_ref_sub(call: types.CallbackQuery, state: FSMContext):
                await state.set_state(SettingsState.waiting_channel)
                await call.message.answer("Kanal usernamesini kiriting (masalan: @kanal_nomi):")

            @router.message(SettingsState.waiting_channel)
            async def save_ref_sub(message: types.Message, state: FSMContext):
                conn = sqlite3.connect("constructor.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE bot_settings SET sub_channel = ? WHERE bot_token = ?", (message.text.strip(), token))
                conn.commit()
                conn.close()
                await message.answer("✅ Majburiy obuna kanali saqlandi!")
                await state.clear()

            @router.message(F.text == "🔗 Taklif havolam")
            async def get_ref_link(message: types.Message):
                me = await sub_bot.get_me()
                settings = get_settings()
                link = f"https://t.me/{me.username}?start={message.from_user.id}"
                await message.answer(f"🔗 Havolangiz:\n`{link}`\n\nHar bir taklif: **{settings[1]} almos**", parse_mode="Markdown")

            @router.message(F.text == "💎 Balans / Almoslar")
            async def show_bal(message: types.Message):
                settings = get_settings()
                conn = sqlite3.connect("constructor.db")
                cursor = conn.cursor()
                cursor.execute("SELECT balance FROM ref_users WHERE bot_token = ? AND user_id = ?", (token, message.from_user.id))
                row = cursor.fetchone()
                bal = row[0] if row else 0
                conn.close()
                await message.answer(f"👤 Balansingiz: **{bal} almos**\nMin. yechish: **{settings[2]} almos**", parse_mode="Markdown")

            @router.message(F.text == "📤 Pulni yechib olish")
            async def withdraw(message: types.Message):
                settings = get_settings()
                conn = sqlite3.connect("constructor.db")
                cursor = conn.cursor()
                cursor.execute("SELECT balance FROM ref_users WHERE bot_token = ? AND user_id = ?", (token, message.from_user.id))
                row = cursor.fetchone()
                bal = row[0] if row else 0
                conn.close()

                if bal >= settings[2]:
                    await message.answer("✅ Yechib olish so'rovingiz adminga yuborildi.")
                    await sub_bot.send_message(owner_id, f"📥 **Yechish so'rovi:**\nUser ID: {message.from_user.id}\nBalans: {bal} almos", parse_mode="Markdown")
                else:
                    await message.answer(f"❌ Kamida **{settings[2]} almos** kerak! (Sizda: {bal} almos)", parse_mode="Markdown")

        sub_dp.include_router(router)
        await sub_dp.start_polling(sub_bot)
    except Exception as e:
        print(f"Sub-botda ({token}) xatolik: {e}")

# --- 3. ASOSIY KONSTRUKTOR BOT ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Yangi bot yaratish")
    builder.button(text="📁 Mening botlarim")
    builder.button(text="💳 Obuna to'lovi")
    builder.button(text="📞 Admin bilan bog'lanish")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("👋 **Bot Konstruktoriga xush kelibsiz!**\nKerakli menyuni tanlang:", reply_markup=main_menu(), parse_mode="Markdown")

@dp.message(F.text == "➕ Yangi bot yaratish")
async def start_creation(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Kodli Kino Bot", callback_data="tpl_Kodli Kino Bot")
    builder.button(text="💎 Referral Bot", callback_data="tpl_Referral Bot")
    builder.adjust(1)
    await message.answer("✨ **Yaratmoqchi bo'lgan bot turini tanlang:**", reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("tpl_"))
async def process_template(call: types.CallbackQuery, state: FSMContext):
    template_name = call.data.split("_", 1)[1]
    await state.update_data(bot_type=template_name)
    await state.set_state(BotCreation.entering_token)
    await call.message.edit_text(f"🤖 **{template_name}** uchun @BotFather'dan olingan tokenini yuboring:", parse_mode="Markdown")

@dp.message(BotCreation.entering_token)
async def save_and_run_bot(message: types.Message, state: FSMContext):
    token = message.text.strip()
    data = await state.get_data()
    bot_type = data.get('bot_type', 'Kodli Kino Bot')
    user_id = message.from_user.id
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    free_until = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = sqlite3.connect("constructor.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_bots (user_id, bot_token, bot_type, created_at, expires_at, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (user_id, token, bot_type, now, free_until)
        )
        conn.commit()
        conn.close()

        task = asyncio.create_task(start_user_bot(token, bot_type, user_id))
        active_bot_tasks[token] = task

        await message.answer(f"✅ **{bot_type}** ishga tushdi!\n\n🔑 Botga o'tib `/admin` deb yozing.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")
    await state.clear()

@dp.message(F.text == "📁 Mening botlarim")
async def my_bots(message: types.Message):
    conn = sqlite3.connect("constructor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT bot_type, expires_at, is_active FROM user_bots WHERE user_id = ?", (message.from_user.id,))
    bots = cursor.fetchall()
    conn.close()
    if not bots:
        await message.answer("Sizda hali botlar yo'q.")
        return
    text = "📱 **Sizning botlaringiz:**\n\n"
    for i, b in enumerate(bots, 1):
        text += f"{i}. **{b[0]}** — {'🟢 Faol' if b[2] else '🔴 To\'xtatilgan'}\n⏳ Sinov muddati: `{b[1][:16]}`\n\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💳 Obuna to'lovi")
async def payment_menu(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🧾 Chekni adminga yuborish", url=f"https://t.me/{ADMIN_USERNAME}")
    await message.answer(f"💳 Oylik obuna: **30,000 so'm**\nKarta: `{ADMIN_CARD}`", reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def admin_contact(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍💻 Admin", url=f"https://t.me/{ADMIN_USERNAME}")
    await message.answer("Bog'lanish uchun tugmani bosing:", reply_markup=builder.as_markup())

async def load_existing_bots():
    conn = sqlite3.connect("constructor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT bot_token, bot_type, user_id FROM user_bots WHERE is_active = 1")
    bots = cursor.fetchall()
    conn.close()
    for token, b_type, owner_id in bots:
        if token not in active_bot_tasks:
            active_bot_tasks[token] = asyncio.create_task(start_user_bot(token, b_type, owner_id))

async def main():
    print("Bot ishga tushmoqda...")
    init_db()
    await load_existing_bots()
    await dp.start_polling(main_bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Xatolik: {e}")
