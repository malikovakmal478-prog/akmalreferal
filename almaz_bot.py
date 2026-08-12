from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError

# Bot tokeningizni kiriting
TOKEN = "8631990028:AAHhHvbdC3L9DmSXwW0ujWD_WBFp41FHJf0"

# Majburiy obuna kanallari ro'yxati (@ belgisi bilan)
CHANNELS = [
    "@ffuzbkzorg",
    "@dima_almazlar",
    "@d1ma_sultanov"
]

# Asosiy menyu
MAIN_KEYBOARD = [
    ["🤖 Sun'iy Intellekt"],
    ["💎 Almaz ishlash", "🤝 Sheriklar"],
    ["🎰 Spin", "⚙️ Telefonga Nastroyka"],
    ["📊 Profilim", "🥇 Meningen darajam"],
    ["🏆 Reyting", "🤝 Sherik Topish"],
    ["🛒 O'yin Do'koni", "🎥 Youtuber Xizmatlari"]
]

# Foydalanuvchi barcha kanallarga obuna bo'lganini tekshiruvchi funksiya
async def check_subscriptions(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, list]:
    unsubscribed_channels = []
    for channel in CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']:
                unsubscribed_channels.append(channel)
        except TelegramError:
            # Bot kanalda admin bo'lmasa yoki kanal topilmasa
            unsubscribed_channels.append(channel)
            
    is_subscribed = len(unsubscribed_channels) == 0
    return is_subscribed, unsubscribed_channels

# Majburiy obuna tugmalarini yaratish
def get_subscription_keyboard(unsubscribed_channels: list) -> InlineKeyboardMarkup:
    keyboard = []
    for channel in unsubscribed_channels:
        # @ffuzbkzorg -> https://t.me/ffuzbkzorg
        url = f"https://t.me/{channel.replace('@', '')}"
        keyboard.append([InlineKeyboardButton(f"➕ Kanag'a a'zo bo'lish ({channel})", url=url)])
    
    # Tekshirish tugmasi
    keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(keyboard)

# /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_subscribed, unsubscribed = await check_subscriptions(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:",
            reply_markup=get_subscription_keyboard(unsubscribed),
            parse_mode="Markdown"
        )
        return

    first_name = update.effective_user.first_name or "Foydalanuvchi"
    text = (
        f"✨ Xush kelibsiz, {first_name}!\n\n"
        "Siz barcha tekshiruvlardan muvaffaqiyatli o'tdingiz — endi botning "
        "barcha imkoniyatlari ochildi. 🚀\n\n"
        "Quyidagi menyudan keragini tanlang\n👇"
    )
    await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True))

# Inline "✅ Tekshirish" tugmasi bosilganda ishlovchi handler
async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    is_subscribed, unsubscribed = await check_subscriptions(user_id, context)
    
    if is_subscribed:
        await query.message.delete()
        first_name = query.from_user.first_name or "Foydalanuvchi"
        text = (
            f"✨ Xush kelibsiz, {first_name}!\n\n"
            "Siz barcha tekshiruvlardan muvaffaqiyatli o'tdingiz — endi botning "
            "barcha imkoniyatlari ochildi. 🚀\n\n"
            "Quyidagi menyudan keragini tanlang\n👇"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
        )
    else:
        await query.edit_message_text(
            "❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!\nIltimos, qayta a'zo bo'lib, 'Tekshirish' tugmasini bosing:",
            reply_markup=get_subscription_keyboard(unsubscribed),
            parse_mode="Markdown"
        )
Telegram
FREE FIRE UZBEKISTAN
👑 Kanal egasi @ruzvix

⚡ Admin @ruzvix

📩 Shikoyatlar uchun: @ruzvix

📜 Qoidalar: @ak_olish_tartibii
VIEW CHANNEL

Акмал
Album
# Oddiy xabarlar yuborilganda ham obunani tekshirish
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_subscribed, unsubscribed = await check_subscriptions(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun avval barcha kanallarga a'zo bo'ling!",
            reply_markup=get_subscription_keyboard(unsubscribed),
            parse_mode="Markdown"
        )
        return

    text = update.message.text

    # 1. Sun'iy Intellekt
    if text == "🤖 Sun'iy Intellekt":
        reply_keyboard = [
            ["🤖 AI Suhbat"],
            ["🎭 Personaj Ovozida AI"],
            ["✨ Nickname Yaratish"],
            ["⬅️ Orqaga"]
        ]
        msg = (
            "🤖 sun'iy Intellekt markazi\n\n"
            "Bu yerda siz Free Fire bo'yicha eng professional AI xizmatlaridan foydalana olasiz.\n\n"
            "👇 Quyidagi bo'limlardan birini tanlang:\n"
            "• 🤖 AI Suhbat — Pro Coach bilan suhbat\n"
            "• 🎭 Personaj Ovozida AI — FF qahramonlari ohangida javob"
        )
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

    # 2. Sheriklar
    elif text == "🤝 Sheriklar":
        reply_keyboard = [
            ["🔍 Sherik Qidirish"],
            ["📢 E'lon Berish"],
            ["👤 Mening Pasportim"],
            ["ℹ️ Qo'llanma"],
            ["⬅️ Orqaga"]
        ]
        msg = "⚔️ Sherik topish (Beta)\n\nQuyidagilardan birini tanlang:"
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

    # 3. Spin
    elif text == "🎰 Spin":
        reply_keyboard = [
            ["🎰 Spin qilish"],
            ["📊 Mening spinlarim"],
            ["🎁 Bonus spin olish"],
            ["⬅️ Orqaga"]
        ]
        msg = (
            "🎰 Spin Tizimi\n\n"
            "Xush kelibsiz! Spin orqali almaz va itemlar yutib olishingiz mumkin!\n\n"
            "📊 Bugungi holat:\n"
            "🆓 Bepul spin: 1 ta\n"
            "💰 Pullik spin: 2 ta (har biri 5 💎)\n"
            "🎁 Bonus spin: 1 ta\n\n"
            "💎 Sizning balansingiz: 0\n\n"
            "⚠️ Bonus spin olish uchun avval 🎁 Bonus spin olish tugmasini bosing!"
        )
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

    # 4. Telefonga Nastroyka
    elif text == "⚙️ Telefonga Nastroyka":
        msg = (
            "⚙️ Telefonga mos Free Fire sozlamalari\n\n"
            "AI sizning qurilmangiz uchun ideal nastroykani yaratadi:\n"
            "• General / Red Dot / 2X / 4X / AWM\n"
            "• DPI tavsiyasi\n"
            "• Otish tugmasi o'lchami\n"
            "• Lagni kamaytirish bo'yicha maslahatlar\n"
            "• 350+ telefon modeli uchun PRO optimizatsiya 😎\n\n"
            "📱 Telefon modelini kiriting:\n"
            "Masalan: Redmi Note 9, Samsung A12, iPhone 11\n\n"
            "❗️ Telefon nomini to'g'ri yozing:\n"
            "Redmi note13pro ❌ — noto'g'ri\n"
            "Redmi note 13 pro ✅ — to'g'ri (bo'sh joyga e'tibor bering)\n\n"
            "🔥 Sizga PRO-level Free Fire nastroykani tayyorlab beraman!"
        )
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["⬅️ Orqaga"]], resize_keyboard=True))

    # 5. Profilim
    elif text == "📊 Profilim":
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Almazni yechish", callback_data="withdraw"), InlineKeyboardButton("🆔 FF ID sozlash", callback_data="set_id")],
            [InlineKeyboardButton("📈 Statistika", callback_data="stats")]
        ])
        user_name = update.effective_user.username

Акмал
Album
username_str = f"@{user_name}" if user_name else "Mavjud emas"
        
        msg = (
            "👤 Profilingiz\n\n"
            f"👤 Username: {username_str}\n"
            "🎮 Free Fire ID: Kiritilmagan\n"
            "🏅 Liga: 🥉 Bronze liga\n"
            "📊 Reyting ballari: 0\n"
            "💎 Almaz: 0\n"
            "🤝 Umumiy tasdiqlangan takliflar: 0\n\n"
            "Almazlaringizni istagan paytda yechib olishingiz mumkin 👇"
        )
        await update.message.reply_text(msg, reply_markup=inline_keyboard)

    # 6. Mening darajam
    elif text == "🥇 Meningen darajam":
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Darajani qanday oshiramiz ?", callback_data="how_to_rank")]
        ])
        msg = (
            "📌 Shaxsiy statistika:\n"
            "• Tasdiqlangan takliflar: 0\n"
            "• Umumiy takliflar: 0\n"
            "• Joriy Almaz balansi: 0\n\n"
            "🎯 Keyingi liga: Silver\n"
            "Unga yetish uchun yana 50 ball kerak.\n\n"
            "ℹ️ Eslatma: Ligalar hozircha faqat obro' sifatida ishlaydi.\n"
            "🔜 Yaqin vaqt ichida ligalar uchun alohida bonuslar qo'shiladi.\n"
            "Faol bo'ling — birinchilar qatorida bo'lasiz! 🚀"
        )
        await update.message.reply_text(msg, reply_markup=inline_keyboard)

    # 7. Reyting
    elif text == "🏆 Reyting":
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Isbotlar ↗️", url="https://t.me/telegram")]
        ])
        msg = (
            "⭐ Foydalanuvchi (ID: 5951770126) — 💎 42\n"
            "⭐ @abbaz678 — 💎 41\n"
            "⭐ Foydalanuvchi (ID: 8539440741) — 💎 40\n"
            "⭐ Foydalanuvchi (ID: 7479009047) — 💎 39\n"
            "⭐ @ELITE_PRICE_org — 💎 39\n"
            "⭐ Foydalanuvchi (ID: 8894816864) — 💎 39\n"
            "⭐ Foydalanuvchi (ID: 7480798039) — 💎 37\n"
            "⭐ @omirbayev_xvk — 💎 37\n"
            "⭐ @asad_bek03120 — 💎 36\n"
            "⭐ Foydalanuvchi (ID: 6950726271) — 💎 36"
        )
        await update.message.reply_text(msg, reply_markup=inline_keyboard)

    # 8. Orqaga
    elif text == "⬅️ Orqaga":
        await update.message.reply_text(
            "🏠 Bosh menyuga qaytdingiz",
            reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
        )

    else:
        await update.message.reply_text("Quyidagi menyudan kerakli bo'limni tanlang 👇")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot muvaffaqiyatli ishga tushdi...")
    app.run_polling()

if name == "main":
    main()
