import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import os
from flask import Flask
import threading

# ================= SOZLAMALAR =================
BOT_TOKEN = '8956850306:AAGYo7rMuNOu2SKWnkmZXyK6OaBQAGlhPKA'
ADMIN_ID = 7849637859  # Sizning Telegram ID raqamingiz

# Majburiy obuna kanallari
CHANNELS = ['@arzon_almazbor', '@arzon_almazbor', '@arzon_almazbor', '@arzon_almazbor']
PAYMENTS_CHANNEL = '@ffuzbkzorg'
MIN_WITHDRAW = 210
REF_BONUS = 5
SUPPORT_USERNAME = '@ruzvix'
YT_CHANNEL = '@dima_sultanov'
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

user_states = {}

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

# Asosiy menyu
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("💎 Almaz ishlash"), KeyboardButton("🤝 Sheriklar"),
        KeyboardButton("🎰 Spin"), KeyboardButton("⚙️ Telefonga Nastroyka"),
        KeyboardButton("📊 Profilim"), KeyboardButton("👑 Mening darajam"),
        KeyboardButton("🏆 Reyting"), KeyboardButton("🤝 Sherik Topish"),
        KeyboardButton("🛒 O'yin Do'koni"), KeyboardButton("🎬 Youtuber Xizmatlari"),
        KeyboardButton("🤖 Sun'iy Intellekt")
    )
    if user_id == ADMIN_ID:
        markup.add(KeyboardButton("🛠 Admin Panel"))
    return markup

# Admin panel menyusi
def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("📊 Statistika"), KeyboardButton("📢 Xabar yuborish"),
        KeyboardButton("💎 Almaz berish/ayirish"), KeyboardButton("🔙 Bosh menyu")
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
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun quyidagi barcha kanallarga a'zo bo'lishingiz shart!", reply_markup=markup)
        return

    bot.send_message(user_id, "🏡 Bosh menyuga xush kelibsiz 👇", reply_markup=main_menu(user_id))

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def verify_sub(call):
    if check_sub(call.from_user.id):
        bot.answer_callback_query(call.id, "Obuna tasdiqlandi! ✅")
        bot.send_message(call.from_user.id, "Quyidagi menyudan kerakli bo'limni tanlang 👇", reply_markup=main_menu(call.from_user.id))
    else:
        bot.answer_callback_query(call.id, "Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    
    if not check_sub(user_id):
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun avval barcha kanallarga a'zo bo'ling!")
        return

    text = message.text
    
    # Holatlarni boshqarish
    if user_id in user_states:
        state = user_states[user_id]
        if state == 'waiting_ffid':
            user_states.pop(user_id)
            cursor.execute("UPDATE users SET ff_id = ? WHERE user_id = ?", (text, user_id))
            conn.commit()
            bot.send_message(user_id, f"✅ Free Fire ID muvaffaqiyatli saqlandi: **{text}**", parse_mode="Markdown", reply_markup=main_menu(user_id))
            return
        elif state == 'waiting_broadcast':
            user_states.pop(user_id)
            cursor.execute("SELECT user_id FROM users")
            all_users = cursor.fetchall()
            success = 0
            for u in all_users:
                try:
                    bot.send_message(u[0], text)
                    success += 1
                except:
                    pass
            bot.send_message(user_id, f"✅ Xabar {success} ta foydalanuvchiga yuborildi!", reply_markup=admin_menu())
            return
        elif state == 'waiting_user_balance':
            user_states.pop(user_id)
            try:
                parts = text.split()
                target_uid = int(parts[0])
                amount = int(parts[1])
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_uid))
                conn.commit()
                bot.send_message(user_id, f"✅ Foydalanuvchi ({target_uid}) balansiga {amount} almaz qo'shildi/ayirildi!", reply_markup=admin_menu())
                bot.send_message(target_uid, f"💎 Admin tomonidan balansingizga {amount} almaz o'zgartirildi!")
            except:
                bot.send_message(user_id, "❌ Xato format! Qaytadan urinib ko'ring (Masalan: 123456789 50)", reply_markup=admin_menu())
            return
        elif isinstance(state, dict):
            if state['step'] == 'waiting_age':
                user_states[user_id] = {'age': text, 'step': 'waiting_level'}
                bot.send_message(user_id, "🎮 Free Fire urvningiz (LEVEL) nechi?")
                return
            elif state['step'] == 'waiting_level':
                user_states[user_id]['level'] = text
                user_states[user_id] = {**user_states[user_id], 'step': 'waiting_gender'}
                bot.send_message(user_id, "👤 O'g'il bolamisiz yoki qiz?")
                return
            elif state['step'] == 'waiting_gender':
                gender = text
                data = user_states.pop(user_id)
                msg = (f"🔍 **Sizga mos do'st topildi!**\n\n"
                       f"🎂 Yoshi: {data['age']}\n"
                       f"🎮 FF Level: {data['level']}\n"
                       f"👤 Jinsi: {gender}\n"
                       f"🔗 Murojaat uchun: @{message.from_user.username or 'Mavjud emas'}")
                bot.send_message(user_id, msg, parse_mode="Markdown")
                bot.send_message(user_id, "Bosh menyudasiz 👇", reply_markup=main_menu(user_id))
                return

    cursor.execute("SELECT balance, referrals, ff_id, points FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    # Admin panel tugmalari
    if user_id == ADMIN_ID:
        if text == "🛠 Admin Panel":
            bot.send_message(user_id, "🛠 Admin paneliga xush kelibsiz:", reply_markup=admin_menu())
            return
        elif text == "🔙 Bosh menyu":
            bot.send_message(user_id, "🏡 Bosh menyu:", reply_markup=main_menu(user_id))
            return
        elif text == "📊 Statistika":
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            bot.send_message(user_id, f"📊 Bot statistikasi:\n\n👥 Jami foydalanuvchilar: {total_users} ta", reply_markup=admin_menu())
            return
        elif text == "📢 Xabar yuborish":
            user_states[user_id] = 'waiting_broadcast'
            bot.send_message(user_id, "📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni kiriting:", reply_markup=admin_menu())
            return
        elif text == "💎 Almaz berish/ayirish":
            user_states[user_id] = 'waiting_user_balance'
            bot.send_message(user_id, "🆔 Foydalanuvchi ID raqami va almaz miqdorini bo'sh joy qoldirib yozing (Masalan: 7915255052 50 yoki -20):", reply_markup=admin_menu())
            return

    if text == "💎 Almaz ishlash" or text == "🤝 Sheriklar":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (f"💎 **Almaz ishlash & Referal**\n\n"
               f"👥 Taklif qilgan do'stlaringiz: {user[1]} ta\n"
               f"💎 Balansingiz: {user[0]} almaz\n\n"
               f"🔗 **Sizning referal havolangiz:**\n{ref_link}\n\n"
               f"Har bir taklif qilingan do'st uchun {REF_BONUS} almaz qo'shiladi!")
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
            f"SOTIB OLISH UCHUN MUROJAT ETASIZ: {SUPPORT_USERNAME} 💎\n\n"
            "ALMAZ 💎 SOTIB OLASIZ\n\n"
            f"{SUPPORT_USERNAME}"
        )
        bot.send_message(user_id, shop_text, parse_mode="Markdown")
        
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
        bot.send_message(user_id, "🤖 Bu yerda siz Free Fire bo'yicha AI xizmatlaridan foydalanishingiz mumkin. Savolingizni yozing!")
        
    elif text == "🎬 Youtuber Xizmatlari":
        bot.send_message(user_id, f"🎬 Youtuber xizmatlari uchun murojaat qilishingiz mumkin bo'lgan kanal/admin: {YT_CHANNEL}")
        
    elif text == "🆘 Yordam":
        bot.send_message(user_id, f"Murojaat va xizmatlar uchun admin: {SUPPORT_USERNAME}")

@bot.callback_query_handler(func=lambda call: call.data == "set_ffid")
def set_ffid_callback(call):
    user_id = call.from_user.id
    user_states[user_id] = 'waiting_ffid'
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "🆔 Free Fire ID raqamingizni kiriting:")

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
