import logging
import sqlite3
import asyncio
from datetime import datetime, date, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================= SOZLAMALAR =================
BOT_TOKEN = "8886195421:AAEv4pGZ0C0NUEx4XTUGljF2rhnDRheqnHY"
ADMIN_IDS = [7849637859]
DB_PATH = "shop.db"
CURRENCY = "so'm"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= DATABASE =================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS customers(
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        joined_at TEXT, banned INTEGER DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price INTEGER,
        description TEXT, active INTEGER DEFAULT 1)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER,
        product_name TEXT, price INTEGER, note TEXT, status TEXT DEFAULT 'kutilmoqda',
        created_at TEXT)""")
    conn.commit()
    conn.close()

def upsert_customer(user):
    conn = db()
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute("SELECT user_id FROM customers WHERE user_id=?", (user.id,)).fetchone()
    if row:
        conn.execute("UPDATE customers SET username=?, first_name=? WHERE user_id=?",
                     (user.username, user.first_name, user.id))
    else:
        conn.execute("INSERT INTO customers(user_id, username, first_name, joined_at, banned) VALUES(?,?,?,?,0)",
                     (user.id, user.username, user.first_name, now))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = db()
    row = conn.execute("SELECT banned FROM customers WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row["banned"])

def add_product(name, price, description):
    conn = db()
    conn.execute("INSERT INTO products(name, price, description, active) VALUES(?,?,?,1)", (name, price, description))
    conn.commit()
    conn.close()

def list_products(active_only=True):
    conn = db()
    if active_only:
        rows = conn.execute("SELECT * FROM products WHERE active=1 ORDER BY id").fetchall()
    else:
        rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    conn.close()
    return rows

def get_product(pid):
    conn = db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    return row

def delete_product(pid):
    conn = db()
    conn.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    conn.commit()
    conn.close()

def create_order(user_id, product, note=""):
    conn = db()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO orders(user_id, product_id, product_name, price, note, status, created_at) VALUES(?,?,?,?,?,?,?)",
        (user_id, product["id"], product["name"], product["price"], note, "kutilmoqda", now))
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id

def get_order(order_id):
    conn = db()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return row

def set_order_status(order_id, status):
    conn = db()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()

def list_orders(status=None, limit=8, offset=0):
    conn = db()
    if status:
        rows = conn.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT ? OFFSET ?",
                           (status, limit, offset)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    conn.close()
    return rows

def get_stats():
    conn = db()
    total_customers = conn.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"]
    today = date.today().isoformat()
    new_today = conn.execute("SELECT COUNT(*) c FROM customers WHERE joined_at LIKE ?", (today+"%",)).fetchone()["c"]
    total_orders = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    paid_orders = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(price),0) s FROM orders WHERE status='tolandi'").fetchone()
    pending = conn.execute("SELECT COUNT(*) c FROM orders WHERE status='kutilmoqda'").fetchone()["c"]
    conn.close()
    return total_customers, new_today, total_orders, paid_orders["c"], paid_orders["s"], pending

def all_customer_ids():
    conn = db()
    rows = conn.execute("SELECT user_id FROM customers WHERE banned=0").fetchall()
    conn.close()
    return [r["user_id"] for r in rows]

def list_customers(limit=8, offset=0):
    conn = db()
    rows = conn.execute("SELECT * FROM customers ORDER BY joined_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    conn.close()
    return rows

# ================= YORDAMCHI =================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def fmt_price(p):
    return f"{p:,}".replace(",", " ") + f" {CURRENCY}"

def back_kb(cb="menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data=cb)]])

# Conversation holatlari
(PROD_NAME, PROD_PRICE, PROD_DESC, ORDER_NOTE,
 BROADCAST_WAIT, CUST_SEARCH) = range(6)

# ================= MIJOZ TOMONI =================
def catalog_kb():
    rows = list_products()
    kb = [[InlineKeyboardButton(f"{r['name']} — {fmt_price(r['price'])}", callback_data=f"p_view_{r['id']}")] for r in rows]
    if not kb:
        kb = [[InlineKeyboardButton("Hozircha mahsulot yo'q", callback_data="noop")]]
    return InlineKeyboardMarkup(kb)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("🚫 Siz botdan foydalanishdan bloklangansiz.")
        return
    upsert_customer(user)
    await update.message.reply_text(
        "🛒 *Bot do'koni*ga xush kelibsiz!\n\n"
        "Bu yerda tayyor botlar sotiladi — kerakli mahsulotni tanlang, "
        "narxi va tavsifi bilan tanishing, so'ng buyurtma bering.",
        parse_mode="Markdown", reply_markup=catalog_kb())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("/start — katalogni ko'rish\n/admin — admin panel (faqat adminlar)")

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data

    if data == "menu":
        await query.answer()
        await query.edit_message_text("🛒 *Bot do'koni* — mahsulotni tanlang:", parse_mode="Markdown", reply_markup=catalog_kb())
        return ConversationHandler.END

    if data == "noop":
        await query.answer("Hozircha mahsulot yo'q.", show_alert=True)
        return ConversationHandler.END

    if data.startswith("p_view_"):
        await query.answer()
        pid = int(data.split("_")[-1])
        p = get_product(pid)
        if not p:
            await query.edit_message_text("Mahsulot topilmadi.", reply_markup=back_kb())
            return ConversationHandler.END
        text = f"🤖 *{p['name']}*\n\n{p['description']}\n\n💰 Narxi: *{fmt_price(p['price'])}*"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sotib olish", callback_data=f"p_buy_{p['id']}")],
            [InlineKeyboardButton("⬅️ Katalogga qaytish", callback_data="menu")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        return ConversationHandler.END

    if data.startswith("p_buy_"):
        await query.answer()
        pid = int(data.split("_")[-1])
        p = get_product(pid)
        if not p:
            await query.edit_message_text("Mahsulot topilmadi.", reply_markup=back_kb())
            return ConversationHandler.END
        context.user_data["buy_product_id"] = pid
        await query.edit_message_text(
            f"🧾 *{p['name']}* — {fmt_price(p['price'])}\n\n"
            "Buyurtmangizga izoh yozing (masalan aloqa uchun telefon/username, "
            "yoki botga qanday o'zgartirish kerakligi). Agar kerak bo'lmasa \"-\" deb yozing.\n\n"
            "Bekor qilish: /cancel",
            parse_mode="Markdown")
        return ORDER_NOTE

    return ConversationHandler.END

async def order_note_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note = update.message.text.strip()
    pid = context.user_data.get("buy_product_id")
    p = get_product(pid)
    if not p:
        await update.message.reply_text("Xatolik: mahsulot topilmadi.", reply_markup=back_kb())
        return ConversationHandler.END
    user = update.effective_user
    order_id = create_order(user.id, p, note if note != "-" else "")
    await update.message.reply_text(
        f"✅ Buyurtmangiz qabul qilindi!\n\n"
        f"🧾 Buyurtma #{order_id}\n🤖 {p['name']}\n💰 {fmt_price(p['price'])}\n\n"
        "Tez orada admin siz bilan bog'lanadi va to'lov bo'yicha yo'riqnoma beradi.",
        reply_markup=back_kb())

    uname = ("@"+user.username) if user.username else user.first_name
    admin_text = (f"🆕 *Yangi buyurtma!* #{order_id}\n\n"
                  f"👤 Mijoz: {uname} (`{user.id}`)\n"
                  f"🤖 Mahsulot: {p['name']}\n💰 Narx: {fmt_price(p['price'])}\n"
                  f"📝 Izoh: {note if note != '-' else '—'}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ To'landi deb belgilash", callback_data=f"o_paid_{order_id}"),
         InlineKeyboardButton("❌ Bekor qilish", callback_data=f"o_cancel_{order_id}")],
    ])
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, admin_text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Bekor qilindi.", reply_markup=back_kb())
    return ConversationHandler.END

# ================= ADMIN — BUYURTMALARNI BOSHQARISH =================
async def order_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yo'q.", show_alert=True)
        return
    data = query.data
    order_id = int(data.split("_")[-1])
    order = get_order(order_id)
    if not order:
        await query.answer("Buyurtma topilmadi.", show_alert=True)
        return

    if data.startswith("o_paid_"):
        set_order_status(order_id, "tolandi")
        await query.answer("To'landi deb belgilandi ✅")
        await query.edit_message_text(query.message.text + "\n\n✅ *TO'LANDI*", parse_mode="Markdown")
        try:
            await context.bot.send_message(order["user_id"],
                f"✅ Buyurtmangiz #{order_id} to'lovi tasdiqlandi. Rahmat!\nBot tez orada siz bilan bog'lanib yetkazib beriladi.")
        except Exception:
            pass

    elif data.startswith("o_cancel_"):
        set_order_status(order_id, "bekor")
        await query.answer("Bekor qilindi ❌")
        await query.edit_message_text(query.message.text + "\n\n❌ *BEKOR QILINDI*", parse_mode="Markdown")
        try:
            await context.bot.send_message(order["user_id"], f"❌ Buyurtmangiz #{order_id} bekor qilindi.")
        except Exception:
            pass

# ================= ADMIN PANEL — ASOSIY MENYU =================
def admin_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Yangi mahsulot", callback_data="a_prod_add"),
         InlineKeyboardButton("📋 Mahsulotlar", callback_data="a_prod_list")],
        [InlineKeyboardButton("🧾 Buyurtmalar", callback_data="a_orders_0"),
         InlineKeyboardButton("📊 Statistika", callback_data="a_stats")],
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data="a_broadcast"),
         InlineKeyboardButton("👥 Mijozlar", callback_data="a_customers_0")],
    ])

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ Bu buyruq faqat adminlar uchun.")
        return
    await update.message.reply_text("🛠 *Admin panel — Bot do'koni*\n\nBo'limni tanlang:",
                                    parse_mode="Markdown", reply_markup=admin_menu_kb())

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ Ruxsat yo'q.")
        return ConversationHandler.END
    data = query.data

    if data == "a_menu":
        await query.edit_message_text("🛠 *Admin panel — Bot do'koni*\n\nBo'limni tanlang:",
                                      parse_mode="Markdown", reply_markup=admin_menu_kb())
        return ConversationHandler.END

    if data == "a_stats":
        total_c, new_today, total_o, paid_c, paid_sum, pending = get_stats()
        text = (f"📊 *Statistika*\n\n👥 Mijozlar: *{total_c}* (bugun +{new_today})\n"
                f"🧾 Buyurtmalar: *{total_o}* (kutilmoqda: {pending})\n"
                f"✅ To'langan: *{paid_c}* ta\n💰 Jami tushum: *{fmt_price(paid_sum)}*")
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb("a_menu"))
        return ConversationHandler.END

    if data == "a_prod_add":
        await query.edit_message_text("➕ Yangi mahsulot nomini yozing (masalan: \"Tap-to-earn o'yin boti\").\nBekor qilish: /cancel")
        return PROD_NAME

    if data == "a_prod_list":
        rows = list_products(active_only=False)
        if not rows:
            await query.edit_message_text("Hozircha mahsulot yo'q.", reply_markup=back_kb("a_menu"))
            return ConversationHandler.END
        kb = []
        for r in rows:
            status = "🟢" if r["active"] else "🔴"
            kb.append([InlineKeyboardButton(f"{status} {r['name']} — {fmt_price(r['price'])}", callback_data=f"a_prod_view_{r['id']}")])
        kb.append([InlineKeyboardButton("⬅️ Menyu", callback_data="a_menu")])
        await query.edit_message_text("📋 *Mahsulotlar ro'yxati:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if data.startswith("a_prod_view_"):
        pid = int(data.split("_")[-1])
        p = get_product(pid)
        if not p:
            await query.edit_message_text("Topilmadi.", reply_markup=back_kb("a_menu"))
            return ConversationHandler.END
        text = f"🤖 *{p['name']}*\n\n{p['description']}\n\n💰 {fmt_price(p['price'])}\nHolat: {'🟢 Faol' if p['active'] else '🔴 O‘chirilgan'}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 O'chirish", callback_data=f"a_prod_del_{pid}")],
            [InlineKeyboardButton("⬅️ Ro'yxatga qaytish", callback_data="a_prod_list")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        return ConversationHandler.END

    if data.startswith("a_prod_del_"):
        pid = int(data.split("_")[-1])
        delete_product(pid)
        await query.edit_message_text("🗑 Mahsulot o'chirildi (katalogdan yashirildi).", reply_markup=back_kb("a_menu"))
        return ConversationHandler.END

    if data.startswith("a_orders_"):
        offset = int(data.split("_")[-1])
        rows = list_orders(limit=6, offset=offset)
        if not rows:
            await query.edit_message_text("Buyurtma yo'q.", reply_markup=back_kb("a_menu"))
            return ConversationHandler.END
        lines = ["🧾 *Buyurtmalar*\n"]
        icons = {"kutilmoqda": "⏳", "tolandi": "✅", "bekor": "❌"}
        for o in rows:
            lines.append(f"{icons.get(o['status'],'•')} #{o['id']} — {o['product_name']} — {fmt_price(o['price'])} — `{o['user_id']}`")
        nav = []
        if offset >= 6:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"a_orders_{offset-6}"))
        nav.append(InlineKeyboardButton("➡️", callback_data=f"a_orders_{offset+6}"))
        kb = InlineKeyboardMarkup([nav, [InlineKeyboardButton("⬅️ Menyu", callback_data="a_menu")]])
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
        return ConversationHandler.END

    if data.startswith("a_customers_"):
        offset = int(data.split("_")[-1])
        rows = list_customers(limit=8, offset=offset)
        if not rows:
            await query.edit_message_text("Boshqa mijoz yo'q.", reply_markup=back_kb("a_menu"))
            return ConversationHandler.END
        lines = ["👥 *Mijozlar*\n"]
        for r in rows:
            uname = ("@"+r["username"]) if r["username"] else r["first_name"] or "—"
            status = "🚫" if r["banned"] else "✅"
            lines.append(f"{status} `{r['user_id']}` — {uname}")
        nav = []
        if offset >= 8:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"a_customers_{offset-8}"))
        nav.append(InlineKeyboardButton("➡️", callback_data=f"a_customers_{offset+8}"))
        kb = InlineKeyboardMarkup([nav, [InlineKeyboardButton("⬅️ Menyu", callback_data="a_menu")]])
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
        return ConversationHandler.END

    if data == "a_broadcast":
        await query.edit_message_text("📢 Barcha mijozlarga yuboriladigan xabarni yozing.\nBekor qilish: /cancel")
        return BROADCAST_WAIT

    return ConversationHandler.END

# ---------- Mahsulot qo'shish oqimi ----------
async def prod_name_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_prod_name"] = update.message.text.strip()
    await update.message.reply_text(f"Narxini kiriting (faqat son, {CURRENCY} da). Masalan: 500000")
    return PROD_PRICE

async def prod_price_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = int(update.message.text.strip())
        context.user_data["new_prod_price"] = price
        await update.message.reply_text("Tavsifini kiriting (mahsulot haqida ma'lumot):")
        return PROD_DESC
    except ValueError:
        await update.message.reply_text("Iltimos, narxni faqat butun son ko'rinishida kiriting!")
        return PROD_PRICE

async def prod_desc_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = context.user_data.get("new_prod_name")
    price = context.user_data.get("new_prod_price")
    desc = update.message.text.strip()
    
    add_product(name, price, desc)
    await update.message.reply_text("✅ Mahsulot muvaffaqiyatli qo'shildi!", reply_markup=back_kb("a_menu"))
    return ConversationHandler.END

async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message.text
    ids = all_customer_ids()
    count = 0
    for cid in ids:
        try:
            await context.bot.send_message(cid, msg)
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"📢 Xabar {count} ta mijozga yuborildi.", reply_markup=back_kb("a_menu"))
    return ConversationHandler.END

# ================= ASOSIY DASTUR =================
async def run():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("admin", admin_panel),
            CallbackQueryHandler(shop_callback, pattern="^(menu|noop|p_view_|p_buy_)"),
            CallbackQueryHandler(admin_callback, pattern="^a_"),
        ],
        states={
            PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_name_receive)],
            PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_price_receive)],
            PROD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_desc_receive)],
            BROADCAST_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
            ORDER_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_note_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(order_admin_callback, pattern="^(o_paid_|o_cancel_)"))
    app.add_handler(CommandHandler("help", help_command))

    init_db()
    print("Bot ishga tushdi...")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    stop_signal = asyncio.Future()
    try:
        await stop_signal
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

def main():
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()
