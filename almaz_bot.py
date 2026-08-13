import telebot
from flask import Flask
import threading
import os

# ================= SOZLAMALAR =================
API_TOKEN = '8844914761:AAF5d8lG00n6NlPMqEHIB53fRfIEz7LcGTw'
ADMIN_ID = 7915255052  # O'zingizning Telegram ID raqamingizni yozing
# ==============================================

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot ishlayapti!"

# Bot komandasi
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Assalomu alaykum! Almaz Botimizga xush kelibsiz. Botimiz hozirda mukammal ishlamoqda! 🚀")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"Xabaringiz qabul qilindi: {message.text}")

# Flask serverini ishga tushirish (Render port talab qilgani uchun)
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Flask serverini alohida oqimda (thread) ishga tushiramiz
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Bot ishga tushdi...")
    # Telegram botni polling rejimida ishga tushiramiz
    bot.infinity_polling()
