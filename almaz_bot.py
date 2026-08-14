import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3

# ================= SOZLAMALAR =================
BOT_TOKEN = '8956850306:AAGYo7rMuNOu2SKWnkmZXyK6OaBQAGlhPKA'
ADMIN_ID = 7849637859  # O'zingizning Telegram ID raqamingiz
CHANNELS = ['@arzon_almazbor', '@arzon_almazbor', '@arzon_almazbor']
PAYMENTS_CHANNEL = '@tolovlar_kanalini_yozing'
MIN_WITHDRAW = 210
REF_BONUS = 5
SUPPORT_USERNAME = '@ruzvix'
# ==============================================

bot = telebot.TeleBot(BOT_TOKEN)

# Baza yaratish
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (user_id INTEGER PRIMARY KEY, balance INTEGER, referrals INTEGER, ff_id TEXT, points INTEGER)''')
conn.commit()

# Foydalanuvchilarning anketalari vaqtinchalik xotirasi
user_states = {}

# Majburiy obunani tekshirish
def check_sub(user_id):
    for channel in CHANNELS:
        try:
            status = bot.get_chat_member(channel, user_id).status
            if status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

# Asosiy menyu
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("💎 Almaz ishlash"), KeyboardButton("🤝 Sherik Topish"),
        KeyboardButton("🛒 O'yin Do'koni"), KeyboardButton("📊 Profilim"),
        KeyboardButton("💸 Almaz Yechish"), KeyboardButton("🆘 Yordam")
    )
    return markup

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute("INSERT INTO users (user_id, balance, referrals, ff_id, points) VALUES (?, ?, ?, ?, ?)", (user_id, 0, 0, "Kiritilmagan", 0))
        conn.commit()
        
        if len(message.text.split()) > 1:
            ref_id = message.text.split()[1]
            if ref_id.isdigit() and int(ref_id) != user_id:
                cursor.execute("UPDATE users SET balance = balance + ?, referrals = referrals + 1, points = points + 10 WHERE user_id = ?", (REF_BONUS, int(ref_id)))
                conn.commit()
                bot.send_message(int(ref_id), f"🎉 Tabriklaymiz! Referal orqali do'stingiz kirdi va sizga {REF_BONUS} almaz berildi!")

    if not check_sub(user_id):
        markup = InlineKeyboardMarkup()
        for ch in CHANNELS:
            markup.add(InlineKeyboardButton(f"Kanalga a'zo bo'lish ({ch})", url=f"https://t.me/{ch.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'lishingiz shart!", reply_markup=markup)
        return

    bot.send_message(user_id, "🏡 Bosh menyuga xush kelibsiz!", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def verify_sub(call):
    if check_sub(call.from_user.id):
        bot.answer_callback_query(call.id, "Obuna tasdiqlandi! ✅")
        bot.send_message(call.from_user.id, "Quyidagi menyudan kerakli bo'limni tanlang 👇", reply_markup=main_menu())
    else:
        bot.answer_callback_query(call.id, "Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    
    if not check_sub(user_id):
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun avval kanallarga a'zo bo'ling!")
        return

    text = message.text
    cursor.execute("SELECT balance, referrals, ff_id, points FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    # Sherik topish anketa jarayoni
    if user_id in user_states:
        state = user_states[user_id]
        if state == 'waiting_age':
            user_states[user_id] = {'age': text, 'step': 'waiting_level'}
            bot.send_message(user_id, "🎮 Free Fire darajangiz (LEVEL) nechchi?")
            return
        elif state.get('step') == 'waiting_level':
            user_states[user_id]['level'] = text
            user_states[user_id]['step'] = 'waiting_gender'
            bot.send_message(user_id, "👤 O'g'il bolamisiz yoki qiz?")
            return
        elif state.get('step') == 'waiting_gender':
            gender = text
            data = user_states.pop(user_id)
            msg = (f"🔍 **Sizga mos do'st topildi!**\n\n"
                   f"🎂 Yoshi: {data['age']}\n"
                   f"🎮 FF Level: {data['level']}\n"
                   f"👤 Jinsi: {gender}\n"
                   f"🔗 Murojaat uchun: @{message.from_user.username or 'Mavjud emas'}")
            bot.send_message(user_id, msg, parse_mode="Markdown")
            bot.send_message(user_id, "Bosh menyudasiz 👇", reply_markup=main_menu())
            return

    if text == "💎 Almaz ishlash":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (f"💎 **Almaz ishlash bo'limi**\n\n"
               f"👥 Taklif qilgan do'stlaringiz: {user[1]} ta\n"
               f"💎 Balansingiz: {user[0]} almaz\n\n"
               f"🔗 **Sizning referal havolangiz:**\n{ref_link}\n\n"
               f"Har bir taklif qilgan odamingiz uchun 5 almaz qo'shiladi!")
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text == "🤝 Sherik Topish":
        user_states[user_id] = {'step': 'waiting_age'}
        bot.send_message(user_id, "Necha yoshsiz?")
        
    elif text == "🛒 O'yin Do'koni":
        shop_text = (
            "🛒 **O'yin Do'koni - Almaz Narxlari**\n\n"
            "110 💎 | 11 999 SO`M🇺🇿 | 78💸🇷🇺\nBONUS 🎁 BILAN | 180 💎\n\n"
            "220 💎 | 23 999 SO`M🇺🇿 | 155💸🇷🇺\nBONUS 🎁 BILAN | 290 💎\n\n"
            "341 💎 | 35 999 SO`M🇺🇿 | 235💸🇷🇺\nBONUS 🎁 BILAN | 559 💎\n\n"
            "451 💎 | 47 999 SO`M🇺🇿 | 310💸🇷🇺\nBONUS 🎁 BILAN | 664 💎\n\n"
            "572 💎 | 59 999 SO`M🇺🇿 | 390💸🇷🇺\nBONUS 🎁 BILAN | 936 💎\n\n"
            "1 166 💎 | 111 999 SO`M🇺🇿 | 780 🇷🇺\nBONUS 🎁 BILAN | 1908 💎\n\n"
            "2 398 💎 | 222 222 SO`M🇺🇿 | 1560💸🇷🇺\nBONUS 🎁 BILAN | 4 247 💎\n\n"
            "6 160 💎 | 555 555 SO`M🇺🇿 | 3510💸🇷🇺\nBONUS 🎁 BILAN | 10 360 💎\n\n"
            "12 320 💎 | 1 111 111 UZ_SO`M | 6870💸🇷🇺\nBONUS 🫴 BILAN | 15 960 💎\n\n"
            "💙 **LVL UP PASS** — 70 000 SO`M💎\n\n"
            "💎 **VAUCHER Almaz**\n"
            "💳 OYLIK VAUCHER — 99 999 SO`M\n"
            "💳 Haftalik Vaucher — 20 000 SO`M\n"
            "💳 LITE VAUCHER — 7 777 SO`M\n\n"
            f"SOTIB OLISH UCHUN MUROJAT ETASIZ: {SUPPORT_USERNAME} 💎"
        )
        bot.send_message(user_id, shop_text, parse_mode="Markdown")
        
    elif text == "📊 Profilim":
        msg = (f"👤 **Profilingiz**\n\n"
               f"💎 Almaz balansi: {user[0]}\n"
               f"🤝 Takliflar soni: {user[1]} ta\n\n"
               f"Almazlaringizni yechish uchun '💸 Almaz Yechish' tugmasini bosing.")
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text == "💸 Almaz Yechish":
        if user[0] < MIN_WITHDRAW:
            bot.send_message(user_id, f"❌ Kechirasiz, minimal almaz yechish {MIN_WITHDRAW} almaz. Sizda {user[0]} almaz mavjud.")
        else:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user_id}_{user[0]}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user_id}")
            )
            admin_msg = f"🔔 **Yangi zayavka!**\n\nFoydalanuvchi ID: {user_id}\nYechmoqchi bo'lgan miqdor: {user[0]} almaz."
            bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=markup)
            
            cursor.execute("UPDATE users SET balance = 0 WHERE user_id=?", (user_id,))
            conn.commit()
            bot.send_message(user_id, "⏳ Almaz yechish so'rovingiz adminga yuborildi. Tasdiqlanishini kuting!")
            
    elif text == "🆘 Yordam":
        bot.send_message(user_id, f"Murojaat uchun: {SUPPORT_USERNAME}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("reject_"))
def admin_approval(call):
    if call.from_user.id != ADMIN_ID:
        return
        
    data = call.data.split('_')
    action = data[0]
    target_user = int(data[1])
    
    if action == "approve":
        amount = data[2]
        bot.edit_message_text(f"✅ {target_user} ning so'rovi tasdiqlandi.", ADMIN_ID, call.message.message_id)
        bot.send_message(target_user, "🎉 Almaz yechish so'rovingiz tasdiqlandi!")
        bot.send_message(PAYMENTS_CHANNEL, f"✅ **Yangi To'lov!**\n\nFoydalanuvchi ID: {target_user}\nMiqdor: {amount} almaz\nShuncha almaz tashlab berildi!", parse_mode="Markdown")
        
    elif action == "reject":
        bot.edit_message_text(f"❌ {target_user} ning so'rovi rad etildi.", ADMIN_ID, call.message.message_id)
        bot.send_message(target_user, "❌ Almaz yechish so'rovingiz admin tomonidan rad etildi.")

bot.infinity_polling()
