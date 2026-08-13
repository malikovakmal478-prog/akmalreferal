import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import os
from flask import Flask
import threading

# ================= SOZLAMALAR =================
BOT_TOKEN = '8844914761:AAF5d8lG00n6NlPMqEHIB53fRfIEz7LcGTw'
ADMIN_ID = 7915255052  # O'zingizning Telegram ID raqamingizni yozing

# Siz ko'rsatgan 3 ta majburiy kanal
CHANNELS = ['@ffuzbkzorg', '@DIMA_almazlar', '@d1ma_sultanov']
PAYMENTS_CHANNEL = '@tolovlar_kanalini_yozing'  # To'lovlar borib tushadigan kanal
MIN_WITHDRAW = 210  # Minimal almaz yechish
REF_BONUS = 5       # Har bir referal uchun almaz
SUPPORT_USERNAME = '@ruzvix'
# ==============================================

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot ishlayapti!"

# Baza yaratish
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (user_id INTEGER PRIMARY KEY, balance INTEGER, referrals INTEGER, ff_id TEXT, points INTEGER)''')
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

# Rasmdagidek to'liq asosiy menyu
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("💎 Almaz ishlash"), KeyboardButton("🤝 Sheriklar"),
        KeyboardButton("🎰 Spin"), KeyboardButton("⚙️ Telefonga Nastroyka"),
        KeyboardButton("📊 Profilim"), KeyboardButton("👑 Mening darajam"),
        KeyboardButton("🏆 Reyting"), KeyboardButton("🤝 Sherik Topish"),
        KeyboardButton("🛒 O'yin Do'koni"), KeyboardButton("🎬 Youtuber Xizmatlari"),
        KeyboardButton("🤖 Sun'iy Intellekt")
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
            markup.add(InlineKeyboardButton(f"Kanag'a a'zo bo'lish ({ch})", url=f"https://t.me/{ch.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=markup)
        return

    bot.send_message(user_id, "🏡 Bosh menyuga qaytdingiz 👇", reply_markup=main_menu())

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
    
    if text == "💎 Almaz ishlash" or text == "🤝 Sheriklar":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (f"💎 **Almaz ishlash & Referal**\n\n"
               f"👥 Taklif qilgan do'stlaringiz: {user[1]} ta\n"
               f"💎 Balansingiz: {user[0]} almaz\n\n"
               f"🔗 **Sizning referal havolangiz:**\n{ref_link}\n\n"
               f"Har bir do'st uchun {REF_BONUS} almaz beriladi!")
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text == "📊 Profilim":
        league = "Bronze liga"
        if user[3] >= 50: league = "Silver liga"
        msg = (f"👤 **Profilingiz**\n\n"
               f"👤 Username: @{message.from_user.username or 'Mavjud emas'}\n"
               f"🎮 Free Fire ID: {user[2]}\n"
               f"🏆 Liga: 🥉 {league}\n"
               f"📊 Reyting ballari: {user[3]}\n"
               f"💎 Almaz: {user[0]}\n"
               f"🤝 Tasdiqlangan takliflar: {user[1]}\n\n"
               f"Almazlaringizni istagan paytda yechib olishingiz mumkin 👇")
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 Almazni yechish", callback_data="withdraw"),
                   InlineKeyboardButton("🆔 FF ID sozlash", callback_data="set_ffid"))
        bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=markup)
        
    elif text == "🏆 Reyting":
        cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        top_users = cursor.fetchall()
        msg = "🏆 **Eng faol foydalanuvchilar reytingi:**\n\n"
        for idx, row in enumerate(top_users, 1):
            msg += f"{idx}. ID: {row[0]} — 💎 {row[1]} almaz\n"
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text == "👑 Mening darajam":
        points = user[3]
        next_ball = 50 - (points % 50)
        msg = (f"📊 **Shaxsiy statistika:**\n"
               f"• Tasdiqlangan takliflar: {user[1]}\n"
               f"• Joriy Almaz balansi: {user[0]}\n\n"
               f"🎯 **Keyingi liga: Silver**\n"
               f"Unga yetish uchun yana {next_ball} ball kerak.")
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text == "⚙️ Telefonga Nastroyka":
        msg = ("⚙️ **Telefonga mos Free Fire sozlamalari**\n\n"
               "AI sizning qurilmangiz uchun ideal nastroykani yaratadi:\n"
               "• General / Red Dot / 2X / 4X / AWM\n"
               "• DPI tavsiyasi\n"
               "• Otish tugmasi o'lchami\n\n"
               "📱 Telefon modelini kiriting (Masalan: Redmi note 13 pro):")
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text == "🎰 Spin":
        bot.send_message(user_id, "🎰 Spin ishlash uchun do'stlaringizni taklif qiling!")
        
    elif text == "🤖 Sun'iy Intellekt":
        msg = ("🤖 **Sun'iy Intellekt / Pro Coach**\n\n"
               "Bu yerda siz Free Fire bo'yicha eng professional AI xizmatlaridan foydalana olasiz.\n\n"
               "Quyidagi bo'limlardan birini tanlang:\n"
               "• AI Suhbat — Pro Coach bilan suhbat\n"
               "• Personaj Ovozida AI — FF qahramonlari ohangida javob")
        bot.send_message(user_id, msg, parse_mode="Markdown")
        
    elif text in ["🆘 Yordam", "Sherik Topish", "O'yin Do'koni", "Youtuber Xizmatlari"]:
        bot.send_message(user_id, f"Murojaat va xizmatlar uchun admin: {SUPPORT_USERNAME}")

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def withdraw_callback(call):
    user_id = call.from_user.id
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = cursor.fetchone()[0]
    
    if bal < MIN_WITHDRAW:
        bot.answer_callback_query(call.id, f"❌ Balansingiz yetarli emas! Minimal yechish {MIN_WITHDRAW} almaz.", show_alert=True)
    else:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user_id}_{bal}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user_id}")
        )
        admin_msg = f"🔔 **Yangi yechish zayavkasi!**\n\nFoydalanuvchi ID: {user_id}\nMiqdor: {bal} almaz."
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=markup)
        
        cursor.execute("UPDATE users SET balance = 0 WHERE user_id=?", (user_id,))
        conn.commit()
        bot.edit_message_text("⏳ Zayavkangiz adminga yuborildi. Kuting!", call.message.chat.id, call.message.message_id)

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
        bot.send_message(PAYMENTS_CHANNEL, f"✅ **Yangi To'lov!**\n\nFoydalanuvchi ID: {target_user}\nMiqdor: {amount} almaz\nShuncha almaz tashlab berildi!", parse_mode="Markdown")
        
    elif action == "reject":
        bot.edit_message_text(f"❌ {target_user} ning so'rovi rad etildi.", ADMIN_ID, call.message.message_id)
        bot.send_message(target_user, "❌ Almaz yechish so'rovingiz admin tomonidan rad etildi.")

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Bot ishga tushdi...")
    bot.infinity_polling()
