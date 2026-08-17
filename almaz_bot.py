import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

# ⚙️ SOZLAMALAR
BOT_TOKEN = "8846688801:AAHLab-JBdYuNkq2shGUYACD7hW_TkByvf4"  # BotFather'dan olingan token
ADMIN_ID = 7849637859  # O'zingizning Telegram ID raqamingizni kiriting

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Database Sozlamalari ---
conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    diamonds INTEGER DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    referrer_id INTEGER DEFAULT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    channel_link TEXT
)
""")
conn.commit()

# --- FSM Holatlari ---
class WithdrawState(StatesGroup):
    waiting_for_id = State()
    waiting_for_amount = State()

class PartnerState(StatesGroup):
    waiting_for_info = State()

class AIState(StatesGroup):
    waiting_for_question = State()

class AdminState(StatesGroup):
    add_channel_id = State()
    add_channel_link = State()
    del_channel_id = State()
    broadcast_msg = State()
    add_diamonds_user = State()
    add_diamonds_amount = State()

# --- Klaviatura Menular ---
def main_menu():
    kb = [
        [KeyboardButton(text="🤖 Sun'iy Intellekt")],
        [KeyboardButton(text="💎 Almaz ishlash"), KeyboardButton(text="🤝 Sheriklar")],
        [KeyboardButton(text="⚙️ Telefonga Nastroyka")],
        [KeyboardButton(text="📊 Profilim"), KeyboardButton(text="🎖 Mening darajam")],
        [KeyboardButton(text="🏆 Reyting"), KeyboardButton(text="🤝 Sherik Topish")],
        [KeyboardButton(text="🛒 O'yin Do'koni"), KeyboardButton(text="🎥 Youtuber Xizmatlari")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
        resize_keyboard=True
    )

def admin_menu():
    kb = [
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Majburiy Obuna")],
        [KeyboardButton(text="📨 Reklama Yuborish"), KeyboardButton(text="💎 Almaz Boshqarish")],
        [KeyboardButton(text="⬅️ Bosh Menyuga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Majburiy Obuna Tekshiruvi ---
async def check_subscription(user_id: int):
    cursor.execute("SELECT channel_id, channel_link FROM channels")
    channels = cursor.fetchall()
    unsubscribed_channels = []

    for ch_id, ch_link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubscribed_channels.append((ch_id, ch_link))
        except Exception:
            # Bot kanalda admin bo'lmasa yoki kanal xato bo'lsa
            pass

    return unsubscribed_channels

def subscription_keyboard(channels):
    buttons = []
    for idx, (_, link) in enumerate(channels, start=1):
        buttons.append([InlineKeyboardButton(text=f"📢 {idx}-Kanalga a'zo bo'lish", url=link)])
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- /start buyrug'i ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = None

    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        if referrer_id and referrer_id != user_id:
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
            if cursor.fetchone():
                cursor.execute("UPDATE users SET diamonds = diamonds + 5, referrals = referrals + 1 WHERE user_id = ?", (referrer_id,))
                try:
                    await bot.send_message(referrer_id, "🎉 Taklif havolangiz orqali yangi foydalanuvchi qo'shildi! Sizga +5 almaz berildi.")
                except Exception:
                    pass

        cursor.execute("INSERT INTO users (user_id, diamonds, referrals, level, referrer_id) VALUES (?, 0, 0, 1, ?)", (user_id, referrer_id))
        conn.commit()

    # Majburiy obunani tekshirish
    unsubbed = await check_subscription(user_id)
    if unsubbed:
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=subscription_keyboard(unsubbed))
        return

    await message.answer("👋 Xush kelibsiz! Asosiy menyudan kerakli bo'limni tanlang:", reply_markup=main_menu())

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    unsubbed = await check_subscription(callback.from_user.id)
    if unsubbed:
        await callback.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
    else:
        await callback.message.delete()
        await callback.message.answer("✅ Rahmat! Endi botdan to'liq foydalanishingiz mumkin.", reply_markup=main_menu())

# --- Admin Panel Buyrug'i ---
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin Panelga xush kelibsiz!", reply_markup=admin_menu())

@dp.message(F.text == "⬅️ Bosh Menyuga")
async def back_to_user_menu(message: types.Message):
    await message.answer("🏠 Asosiy menyu", reply_markup=main_menu())

# --- Admin: Statistika ---
@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(diamonds) FROM users")
    total_diamonds = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM channels")
    total_channels = cursor.fetchone()[0]

    text = (
        f"📊 **Bot Statistikasi:**\n\n"
        f"👥 Barcha foydalanuvchilar: **{total_users}** ta\n"
        f"💎 Aylanishdagi almazlar: **{total_diamonds}** ta\n"
        f"📢 Majburiy kanallar: **{total_channels}** ta"
    )
    await message.answer(text, parse_mode="Markdown")

# --- Admin: Majburiy Obuna Boshqaruvi ---
@dp.message(F.text == "📢 Majburiy Obuna")
async def admin_channels(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT channel_id, channel_link FROM channels")
    channels = cursor.fetchall()

    text = "📢 **Hozirgi Majburiy Kanallar:**\n\n"
    for c_id, c_link in channels:
        text += f"• `{c_id}` — [Kanal havolasi]({c_link})\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_ch")],
        [InlineKeyboardButton(text="➖ Kanal o'chirish", callback_data="del_ch")]
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)

@dp.callback_query(F.data == "add_ch")
async def add_channel_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Kanalning ID raqamini yoki foydalanuvchi nomini kiriting (Masalan: `@kanal_username` yoki `-100123456789`):\n\n*Eslatma: Bot kanalda admin bo'lishi kerak!*", parse_mode="Markdown", reply_markup=back_menu())
    await state.set_state(AdminState.add_channel_id)
    await callback.answer()

@dp.message(AdminState.add_channel_id)
async def add_channel_id(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("🛠 Admin Panel", reply_markup=admin_menu())
        return

    await state.update_data(ch_id=message.text)
    await message.answer("🔗 Endi kanalning taklif havolasini (Linkini) kiriting (Masalan: `https://t.me/kanal_username`):", parse_mode="Markdown")
    await state.set_state(AdminState.add_channel_link)

@dp.message(AdminState.add_channel_link)
async def add_channel_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ch_id = data.get("ch_id")
    ch_link = message.text

    cursor.execute("INSERT OR REPLACE INTO channels (channel_id, channel_link) VALUES (?, ?)", (ch_id, ch_link))
    conn.commit()

    await message.answer("✅ Kanal majburiy obunaga muvaffaqiyatli qo'shildi!", reply_markup=admin_menu())
    await state.clear()

@dp.callback_query(F.data == "del_ch")
async def del_channel_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🗑 O'chirmoqchi bo'lgan kanalingizning ID sini kiriting (Masalan: `@kanal_username`):", reply_markup=back_menu())
    await state.set_state(AdminState.del_channel_id)
    await callback.answer()

@dp.message(AdminState.del_channel_id)
async def del_channel_process(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("🛠 Admin Panel", reply_markup=admin_menu())
        return

    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (message.text,))
    conn.commit()

    await message.answer("✅ Kanal majburiy obunadan o'chirildi!", reply_markup=admin_menu())
    await state.clear()

# --- Admin: Reklama Yuborish ---
@dp.message(F.text == "📨 Reklama Yuborish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📝 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni/reklamangizni yuboring:", reply_markup=back_menu())
    await state.set_state(AdminState.broadcast_msg)

@dp.message(AdminState.broadcast_msg)
async def broadcast_process(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("🛠 Admin Panel", reply_markup=admin_menu())
        return

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    count = 0
    await message.answer("🚀 Reklama yuborish boshlandi...")
    
    for (u_id,) in users:
        try:
            await message.copy_to(chat_id=u_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Reklama **{count}** ta foydalanuvchiga muvaffaqiyatli yuborildi!", reply_markup=admin_menu())
    await state.clear()

# --- Admin: Almaz Boshqarish ---
@dp.message(F.text == "💎 Almaz Boshqarish")
async def add_diamonds_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👤 Foydalanuvchining **Telegram ID** raqamini kiriting:", reply_markup=back_menu())
    await state.set_state(AdminState.add_diamonds_user)

@dp.message(AdminState.add_diamonds_user)
async def add_diamonds_user(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("🛠 Admin Panel", reply_markup=admin_menu())
        return

    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqam bo'lishi kerak!")
        return

    await state.update_data(target_user=int(message.text))
    await message.answer("💎 Nechta almaz qo'shmoqchisiz? (Olib tashlash uchun manfiy son kiriting, masalan: -50):")
    await state.set_state(AdminState.add_diamonds_amount)

@dp.message(AdminState.add_diamonds_amount)
async def add_diamonds_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Miqdor son bo'lishi kerak!")
        return

    data = await state.get_data()
    target_user = data.get("target_user")

    cursor.execute("UPDATE users SET diamonds = diamonds + ? WHERE user_id = ?", (amount, target_user))
    conn.commit()

    try:
        await bot.send_message(target_user, f"💎 Admin tomonidan balansingizga **{amount}** almaz qo'shildi!")
    except Exception:
        pass

    await message.answer(f"✅ Foydalanuvchi `{target_user}` balansiga {amount} almaz o'zgartirildi!", reply_markup=admin_menu())
    await state.clear()

# --- Orqaga Tugmasi Logikasi ---
@dp.message(F.text == "⬅️ Orqaga")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Bosh menyuga qaytdingiz", reply_markup=main_menu())

# --- QOLGAN BO'LIMLAR (Foydalanuvchilar uchun) ---

@dp.message(F.text == "🤖 Sun'iy Intellekt")
async def ai_start(message: types.Message, state: FSMContext):
    await message.answer("🤖 AI Rejimi yoqildi! Savolingizni yuboring:", reply_markup=back_menu())
    await state.set_state(AIState.waiting_for_question)

@dp.message(AIState.waiting_for_question)
async def ai_response(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("🏠 Bosh menyuga qaytdingiz", reply_markup=main_menu())
        return

    query = message.text.lower()
    if "nastroyka" in query or "sozlama" in query:
        ans = "💡 O'yinda headshot urish uchun umumiy sezgirlikni (Obshiy) 95-100 oralig'ida tuting va Red Dot'ni 90 ga qo'ying!"
    elif "almaz" in query:
        ans = "💎 Almaz olish uchun referal havolangizni do'stlaringizga yuboring yoki O'yin Do'koni bo'limidan xarid qiling."
    else:
        ans = f"🤖 Savolingiz qabul qilindi: '{message.text}'. Tez orada javob beriladi!"
    
    await message.answer(ans)

@dp.message(F.text == "💎 Almaz ishlash")
@dp.message(F.text == "🤝 Sheriklar")
async def earn_diamonds(message: types.Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    text = (
        f"🚀 **Almaz ishlash bo'limi**\n\n"
        f"Do'stlaringizni taklif qiling va har bir do'stingiz uchun **5 almas** ega bo'ling!\n\n"
        f"🔗 Sizning taklif havolangiz:\n`{ref_link}`"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "⚙️ Telefonga Nastroyka")
async def settings_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Redmi / Xiaomi", callback_data="set_redmi")],
        [InlineKeyboardButton(text="📱 Samsung", callback_data="set_samsung")],
        [InlineKeyboardButton(text="📱 iPhone / iOS", callback_data="set_iphone")],
        [InlineKeyboardButton(text="📱 Poco / RealMi / Boshqalar", callback_data="set_other")]
    ])
    await message.answer("⚙️ Telefon modelingizni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("set_"))
async def show_settings(callback: types.CallbackQuery):
    phone_type = callback.data.split("_")[1]
    if phone_type == "redmi":
        text = "📱 **Redmi Sozlamalari:**\n• Obshiy: 98\n• Red Dot: 92\n• 2x Scope: 95\n• 4x Scope: 90\n• Knopka razmeri: 48%"
    elif phone_type == "samsung":
        text = "📱 **Samsung Sozlamalari:**\n• Obshiy: 100\n• Red Dot: 88\n• 2x Scope: 90\n• 4x Scope: 85\n• Knopka razmeri: 45%"
    elif phone_type == "iphone":
        text = "📱 **iPhone Sozlamalari:**\n• Obshiy: 90\n• Red Dot: 85\n• 2x Scope: 88\n• 4x Scope: 80\n• Knopka razmeri: 52%"
    else:
        text = "📱 **Umumiy Sozlamalar:**\n• Obshiy: 95\n• Red Dot: 90\n• 2x Scope: 92\n• 4x Scope: 88\n• Knopka razmeri: 50%"

    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text == "📊 Profilim")
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT diamonds, referrals, level FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    diamonds = row[0] if row else 0
    referrals = row[1] if row else 0
    level = row[2] if row else 1

    text = (
        f"👤 **Sizning Profilingiz:**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"🎖 Darajangiz: **{level}-daraja**\n"
        f"💎 Almazlaringiz: **{diamonds}** ta\n"
        f"👥 Taklif qilgan do'stlaringiz: **{referrals}** ta\n\n"
        f"💸 Minimal yechib olish: **450 almas**"
    )
    
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Almaz yechib olish", callback_data="withdraw")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=inline_kb)

@dp.callback_query(F.data == "withdraw")
async def start_withdraw(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cursor.execute("SELECT diamonds FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    diamonds = row[0] if row else 0

    if diamonds < 450:
        await callback.answer("❌ Minimal yechib olish miqdori 450 almas!", show_alert=True)
        return

    await callback.message.answer("📝 O'yindagi **ID raqamingizni** kiriting:", reply_markup=back_menu())
    await state.set_state(WithdrawState.waiting_for_id)
    await callback.answer()

@dp.message(WithdrawState.waiting_for_id)
async def process_withdraw_id(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("🏠 Bosh menyuga qaytdingiz", reply_markup=main_menu())
        return

    await state.update_data(game_id=message.text)
    await message.answer("💎 Nechta almaz yechib olmoqchisiz? (Minimal 450):")
    await state.set_state(WithdrawState.waiting_for_amount)

@dp.message(WithdrawState.waiting_for_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("🏠 Bosh menyuga qaytdingiz", reply_markup=main_menu())
        return

    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting!")
        return

    amount = int(message.text)
    user_id = message.from_user.id
    
    cursor.execute("SELECT diamonds FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    diamonds = row[0] if row else 0

    if amount < 450:
        await message.answer("❌ Minimal yechib olish miqdori 450 almas!")
        return
    
    if amount > diamonds:
        await message.answer("❌ Balansingizda yetarli almaz yo'q!")
        return

    data = await state.get_data()
    game_id = data.get("game_id")

    cursor.execute("UPDATE users SET diamonds = diamonds - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

    admin_text = f"📥 **Yangi yechib olish so'rovi!**\n\n👤 User ID: `{user_id}`\n🎮 Game ID: `{game_id}`\n💎 Almaz: {amount}"
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_{user_id}_{amount}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{user_id}_{amount}")]
    ])
    
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_kb)
    except Exception:
        pass

    await message.answer("✅ Arizangiz adminga yuborildi. Tez orada tekshirib beriladi!", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data.startswith("app_"))
async def approve_withdraw(callback: types.CallbackQuery):
    _, uid, amount = callback.data.split("_")
    await bot.send_message(int(uid), f"🎉 Tabriklaymiz! {amount} almaz o'yin ID ingizga tushirib berildi!")
    await callback.messag
