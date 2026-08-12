import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3

# ================= SOZLAMALAR =================
BOT_TOKEN = '8631990028:AAHhHvbdC3L9DmSXwW0ujWD_WBFp41FHJf0'  # BotFather'dan olgan tokeningiz
ADMIN_ID = 7915255052  # O'zingizning Telegram ID raqamingizni yozing

# Siz so'ragan 3 ta majburiy kanal
CHANNELS = ['@ffuzbkzorg', '@DIMA_almazlar', '@d1ma_sultanov']
PAYMENTS_CHANNEL = '@tolovlar_kanalini_yozing'  # To'lovlar borib tushadigan kanal
MIN_WITHDRAW = 210  # Minimal almaz yechish
REF_BONUS = 5       # Har bir referal uchun almaz
SUPPORT_USERNAME = '@ruzvix'
# ==============================================

bot = telebot.TeleBot(BOT_TOKEN)

# Baza yaratish
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (user_id INTEGER PRIMARY KEY, balance INTEGER, referrals INTEGER)''')
conn.commit()

# Majburiy obunani tekshirish funksiyasi
def check_sub(user_id):
    for channel in CHANNELS:
        try:
            status = bot.get_chat_member(channel, user_id).status
            if status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

# Bosh menyu
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("💎 Balans va Referal"), KeyboardButton("📊 Statistika"))
    markup.add(KeyboardButton("💸 Almaz Yechish"), KeyboardButton("🆘 Yordam"))
    markup.add(KeyboardButton("🤖 AI Yordamchi"))
    return markup

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    
    # Bazaga qo'shish va referal tekshirish
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute("INSERT INTO users (user_id, balance, referrals) VALUES (?, ?, ?)", (user_id, 0, 0))
        conn.commit()
        
        # Referal orqali kirgan bo'lsa
        if len(message.text.split()) > 1:
            ref_id = message.text.split()[1]
            if ref_id.isdigit() and int(ref_id) != user_id:
                cursor.execute("UPDATE users SET balance = balance + ?, referrals = referrals + 1 WHERE user_id = ?", (REF_BONUS, int(ref_id)))
                conn.commit()
                bot.send_message(int(ref_id), f"🎉 Tabriklaymiz! Referal orqali do'stingiz kirdi va sizga {REF_BONUS} almaz berildi!")

    # Majburiy obunani tekshirish
    if not check_sub(user_id):
        markup = InlineKeyboardMarkup()
        for ch in CHANNELS:
            markup.add(InlineKeyboardButton(f" kanalga a'zo bo'lish ({ch})", url=f"https://t.me/{ch.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=markup)
        return

    bot.send_message(user_id, "Quyidagi menyudan kerakli bo'limni tanlang 👇", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def verify_sub(call):
    if check_sub(call.from_user.id):
        bot.answer_callback_query(call.id, "Obuna tasdiqlandi! ✅")
        bot.send_message(call.from_user.id, "Bosh menyuga qaytdingiz 👇", reply_markup=main_menu())
    else:
        bot.answer_callback_query(call.id, "Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    
    if not check_sub(user_id):
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun avval kanallarga a'zo bo'ling!")
        return

    text = message.text
    cursor.execute("SELECT balance, referrals FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    if text == "💎 Balans va Referal":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (f"💎 **Sizning balansingiz:** {user[0]} almaz\n"
               f"👥 **Taklif qilgan do'stlaringiz:** {user[1]} ta\n\n"
               f"🔗 **Sizning referal silkangiz:**\n{ref_link}\n\n"
               f"Har bir taklif uchun {REF_BONUS} almaz beriladi!")
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text == "📊 Statistika":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        bot.send_message(user_id, f"📊 **Bot statistikasi:**\n\nJami foydalanuvchilar: {total_users} ta")
        
    elif text == "🆘 Yordam":
        bot.send_message(user_id, f"Murojaat uchun: {SUPPORT_USERNAME}")
        
    elif text == "🤖 AI Yordamchi":
        bot.send_message(user_id, "Bu yerda siz Free Fire bo'yicha eng professional AI xizmatlaridan foydalana olasiz.")
        
    elif text == "💸 Almaz Yechish":
        if user[0] < MIN_WITHDRAW:
            bot.send_message(user_id, f"❌ Balansingiz yetarli emas. Minimal yechish {MIN_WITHDRAW} almaz.")
        else:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user_id}_{user[0]}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user_id}")
            )
            admin_msg = f"🔔 **Yangi zayavka!**\n\nFoydalanuvchi ID: {user_id}\nYechmoqchi bo'lgan summa: {user[0]} almaz."
            bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=markup)
            
            cursor.execute("UPDATE users SET balance = 0 WHERE user_id=?", (user_id,))
            conn.commit()
            
            bot.send_message(user_id, "⏳ Zayavka adminga yuborildi. Tasdiqlanishini kuting.")

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
        bot.send_message(target_user, f"🎉 Tabriklaymiz! Sizning {amount} almaz yechish so'rovingiz tasdiqlandi!")
        bot.send_message(PAYMENTS_CHANNEL, f"✅ **Yangi To'lov!**\n\nFoydalanuvchi ID: {target_user}\nMiqdor: {amount} almaz\n\nShuncha almaz tashlab berildi!", parse_mode="Markdown")
        
    elif action == "reject":
        bot.edit_message_text(f"❌ {target_user} ning so'rovi rad etildi.", ADMIN_ID, call.message.message_id)
        bot.send_message(target_user, "❌ Almaz yechish so'rovingiz admin tomonidan rad etildi.")

bot.infinity_polling()
