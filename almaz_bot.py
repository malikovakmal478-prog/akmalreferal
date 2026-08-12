"""
ALMAZ BOT - Telegram Referral Bot + Mini App
=============================================
Har bir referalga 5 olmos beriladi. Minimal yechish miqdori: 210 olmos.
Admin bilan bog'lanish: @ruzvix

ISHGA TUSHIRISH (Render.com'da):
1. Bu faylni GitHub repo'ga yuklang (yoki Render'da "Upload files")
2. requirements.txt yarating (pastda ko'rsatilgan)
3. Render.com'da "New Web Service" -> repo'ni ulang
4. Environment Variables qo'shing:
   - BOT_TOKEN = @BotFather'dan olingan token
   - BASE_URL  = Render sizga bergan URL, masalan https://almazbot.onrender.com
   - ADMIN_ID  = sizning Telegram user_id raqamingiz (ixtiyoriy, so'rovlar haqida xabar olish uchun)
     Agar ADMIN_ID bilmasangiz, @userinfobot ga yozib ID'ingizni bilib oling.
5. Start Command: python almaz_bot.py
6. Deploy tugmasini bosing. Bot avtomatik webhook o'rnatadi.

requirements.txt:
    python-telegram-bot==21.6
    Flask==3.0.3
"""

import os
import sqlite3
import hmac
import hashlib
import json
import asyncio
import threading
import logging
from datetime import datetime
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, Response
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import Application, CommandHandler, ContextTypes

# ----------------------------------------------------------------------
# SOZLAMALAR
# ----------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
ADMIN_ID = os.environ.get("ADMIN_ID", "")
ADMIN_USERNAME = "ruzvix"
PORT = int(os.environ.get("PORT", 10000))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "almaz.db")

REFERRAL_BONUS = 5
MIN_WITHDRAW = 210

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable topilmadi!")
if not BASE_URL:
    raise RuntimeError("BASE_URL environment variable topilmadi! Masalan: https://sizning-app.onrender.com")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("almazbot")

BOT_USERNAME_CACHE = {"value": None}

# ----------------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            referrer_id INTEGER,
            referral_count INTEGER DEFAULT 0,
            joined_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def get_or_create_user(user_id, username, first_name, referrer_id=None):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET username=?, first_name=? WHERE user_id=?",
            (username, first_name, user_id),
        )
        conn.commit()
        conn.close()
        return dict(row), False

    conn.execute(
        "INSERT INTO users (user_id, username, first_name, balance, total_earned, referrer_id, referral_count, joined_at) "
        "VALUES (?,?,?,0,0,?,0,?)",
        (user_id, username, first_name, referrer_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row), True


def credit_referrer(referrer_id):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET balance = balance + ?, total_earned = total_earned + ?, referral_count = referral_count + 1 "
        "WHERE user_id=?",
        (REFERRAL_BONUS, REFERRAL_BONUS, referrer_id),
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_withdraw_request(user_id, amount):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO requests (user_id, amount, status, created_at, updated_at) VALUES (?,?,'pending',?,?)",
        (user_id, amount, now, now),
    )
    conn.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    req_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return req_id


def get_user_requests(user_id, limit=20):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM requests WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_requests():
    conn = get_conn()
    rows = conn.execute(
        "SELECT r.*, u.username, u.first_name FROM requests r "
        "JOIN users u ON u.user_id = r.user_id "
        "WHERE r.status='pending' ORDER BY r.id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_request_status(req_id, status):
    conn = get_conn()
    row = conn.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute(
        "UPDATE requests SET status=?, updated_at=? WHERE id=?",
        (status, datetime.utcnow().isoformat(), req_id),
    )
    if status == "rejected":
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (row["amount"], row["user_id"]),
        )
    conn.commit()
    conn.close()
    return dict(row)


# ----------------------------------------------------------------------
# TELEGRAM WEBAPP initData TEKSHIRISH (xavfsizlik uchun)
# ----------------------------------------------------------------------
def verify_init_data(init_data: str) -> dict | None:
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return None
    user_json = parsed.get("user")
    if not user_json:
        return None
    try:
        user = json.loads(user_json)
    except json.JSONDecodeError:
        return None
    return user


# ----------------------------------------------------------------------
# ASYNCIO EVENT LOOP (background thread) - PTB async ishlarini bajarish uchun
# ----------------------------------------------------------------------
loop = asyncio.new_event_loop()


def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()


threading.Thread(target=start_loop, daemon=True).start()


def run_async(coro, timeout=30):
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ----------------------------------------------------------------------
# TELEGRAM BOT
# ----------------------------------------------------------------------
application = Application.builder().token(BOT_TOKEN).build()


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    args = context.args
    referrer_id = None

    if args and args[0].startswith("ref_"):
        try:
            candidate = int(args[0].replace("ref_", ""))
            if candidate != tg_user.id and get_user(candidate):
                referrer_id = candidate
        except ValueError:
            pass

    user, is_new = get_or_create_user(
        tg_user.id, tg_user.username or "", tg_user.first_name or "", referrer_id
    )

    if is_new and referrer_id:
        credit_referrer(referrer_id)
        try:
            await context.bot.send_message(
                referrer_id,
                f"🎉 Sizga yangi referal qo'shildi!\n+{REFERRAL_BONUS} 💎 hisobingizga qo'shildi.",
            )
        except Exception:
            pass

    webapp_url = f"{BASE_URL}/miniapp"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💎 Mini App'ni ochish", web_app=WebAppInfo(url=webapp_url))]]
    )
    await update.message.reply_text(
        "👋 Xush kelibsiz, Almaz Bot'ga!\n\n"
        f"💎 Har bir taklif qilgan do'stingiz uchun +{REFERRAL_BONUS} olmos olasiz\n"
        f"💰 Minimal yechish miqdori: {MIN_WITHDRAW} olmos\n\n"
        "Balansingizni ko'rish va olmos yechish uchun quyidagi tugmani bosing 👇",
        reply_markup=keyboard,
    )


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_ID or str(update.effective_user.id) != str(ADMIN_ID):
        return
    reqs = get_pending_requests()
    if not reqs:
        await update.message.reply_text("Kutilayotgan so'rovlar yo'q.")
        return
    lines = ["📋 Kutilayotgan so'rovlar:\n"]
    for r in reqs:
        uname = f"@{r['username']}" if r["username"] else r["first_name"]
        lines.append(f"#{r['id']} — {uname} (ID: {r['user_id']}) — {r['amount']} 💎")
    lines.append("\nTasdiqlash: /approve <id>\nRad etish: /reject <id>")
    await update.message.reply_text("\n".join(lines))


async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_ID or str(update.effective_user.id) != str(ADMIN_ID):
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /approve <so'rov_id>")
        return
    req_id = int(context.args[0])
    row = update_request_status(req_id, "approved")
    if not row:
        await update.message.reply_text("So'rov topilmadi.")
        return
    await update.message.reply_text(f"✅ #{req_id} so'rov tasdiqlandi.")
    try:
        await context.bot.send_message(
            row["user_id"], f"✅ Sizning {row['amount']} 💎 yechish so'rovingiz tasdiqlandi!"
        )
    except Exception:
        pass


async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_ID or str(update.effective_user.id) != str(ADMIN_ID):
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /reject <so'rov_id>")
        return
    req_id = int(context.args[0])
    row = update_request_status(req_id, "rejected")
    if not row:
        await update.message.reply_text("So'rov topilmadi.")
        return
    await update.message.reply_text(f"❌ #{req_id} so'rov rad etildi, mablag' qaytarildi.")
    try:
        await context.bot.send_message(
            row["user_id"],
            f"❌ Sizning {row['amount']} 💎 yechish so'rovingiz rad etildi. "
            f"Mablag' hisobingizga qaytarildi. Savollar uchun: @{ADMIN_USERNAME}",
        )
    except Exception:
        pass


application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("pending", pending_cmd))
application.add_handler(CommandHandler("approve", approve_cmd))
application.add_handler(CommandHandler("reject", reject_cmd))

run_async(application.initialize())
run_async(application.bot.set_webhook(url=f"{BASE_URL}/webhook/{BOT_TOKEN}"))
_me = run_async(application.bot.get_me())
BOT_USERNAME_CACHE["value"] = _me.username
log.info(f"Bot ishga tushdi: @{_me.username}")

# ----------------------------------------------------------------------
# FLASK APP
# ----------------------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def health():
    return "Almaz Bot ishlayapti ✅"


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    run_async(application.process_update(update))
    return "ok"


@app.route("/api/me", methods=["POST"])
def api_me():
    init_data = request.json.get("initData", "") if request.is_json else ""
    tg_user = verify_init_data(init_data)
    if not tg_user:
        return jsonify({"error": "invalid_init_data"}), 401

    user_id = tg_user["id"]
    user, _ = get_or_create_user(
        user_id, tg_user.get("username", ""), tg_user.get("first_name", "")
    )
    reqs = get_user_requests(user_id)
    bot_username = BOT_USERNAME_CACHE["value"]
    return jsonify(
        {
            "balance": user["balance"],
            "total_earned": user["total_earned"],
            "referral_count": user["referral_count"],
            "min_withdraw": MIN_WITHDRAW,
            "referral_link": f"https://t.me/{bot_username}?start=ref_{user_id}",
            "requests": [
                {"id": r["id"], "amount": r["amount"], "status": r["status"], "date": r["created_at"][:10]}
                for r in reqs
            ],
            "admin_username": ADMIN_USERNAME,
        }
    )


@app.route("/api/withdraw", methods=["POST"])
def api_withdraw():
    init_data = request.json.get("initData", "") if request.is_json else ""
    tg_user = verify_init_data(init_data)
    if not tg_user:
        return jsonify({"error": "invalid_init_data"}), 401

    user_id = tg_user["id"]
    user = get_user(user_id)
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    if user["balance"] < MIN_WITHDRAW:
        return jsonify({"error": "insufficient_balance", "min": MIN_WITHDRAW}), 400

    amount = user["balance"]
    req_id = create_withdraw_request(user_id, amount)

    if ADMIN_ID:
        uname = f"@{tg_user.get('username')}" if tg_user.get("username") else tg_user.get("first_name", "")
        try:
            run_async(
                application.bot.send_message(
                    ADMIN_ID,
                    f"💎 Yangi yechish so'rovi #{req_id}\n"
                    f"Foydalanuvchi: {uname} (ID: {user_id})\n"
                    f"Miqdor: {amount} 💎\n\n"
                    f"Tasdiqlash: /approve {req_id}\nRad etish: /reject {req_id}",
                )
            )
        except Exception:
            pass

    return jsonify({"ok": True, "request_id": req_id, "amount": amount})


MINIAPP_HTML = """
<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Almaz Bot</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  * { box-sizing: border-box; margin:0; padding:0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--tg-theme-bg-color, #0f0f1a);
    color: var(--tg-theme-text-color, #ffffff);
    padding: 16px;
    padding-bottom: 40px;
  }
  .header { text-align:center; margin: 16px 0 24px; }
  .diamond-icon { font-size: 56px; margin-bottom: 8px; }
  .header h1 { font-size: 22px; font-weight: 700; }
  .card {
    background: linear-gradient(135deg, #1e1e3f, #2a2a5a);
    border-radius: 20px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  }
  .balance-row { display:flex; justify-content:space-between; align-items:baseline; margin-bottom: 10px;}
  .balance-value { font-size: 32px; font-weight: 800; color: #7ee0ff; }
  .balance-label { font-size: 13px; opacity: 0.7; }
  .progress-wrap { background: rgba(255,255,255,0.1); border-radius: 999px; height: 12px; overflow: hidden; margin-top: 8px;}
  .progress-bar { height: 100%; background: linear-gradient(90deg, #4facfe, #00f2fe); border-radius: 999px; transition: width 0.4s ease; }
  .progress-text { font-size: 12px; opacity: 0.6; margin-top: 6px; text-align: right;}
  .stats-grid { display:flex; gap: 12px; }
  .stat-box { flex:1; background: rgba(255,255,255,0.06); border-radius: 14px; padding: 14px; text-align:center;}
  .stat-box .num { font-size: 22px; font-weight: 700; }
  .stat-box .lbl { font-size: 11px; opacity: 0.6; margin-top: 4px;}
  .ref-link-box {
    background: rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 12px;
    font-size: 12px;
    word-break: break-all;
    margin-bottom: 12px;
    opacity: 0.85;
  }
  .btn-row { display:flex; gap: 10px; }
  .btn {
    flex:1;
    padding: 13px;
    border: none;
    border-radius: 14px;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    color: white;
  }
  .btn-primary { background: linear-gradient(135deg, #4facfe, #00f2fe); color:#062; }
  .btn-secondary { background: rgba(255,255,255,0.1); color: white; }
  .btn-withdraw {
    width: 100%;
    margin-top: 14px;
    padding: 15px;
    border: none;
    border-radius: 14px;
    font-size: 15px;
    font-weight: 800;
    background: linear-gradient(135deg, #f7971e, #ffd200);
    color: #3a2400;
    cursor: pointer;
  }
  .btn-withdraw:disabled { opacity: 0.4; cursor: not-allowed; }
  .section-title { font-size: 14px; font-weight: 700; margin: 20px 0 10px; opacity: 0.8;}
  .history-item {
    display:flex; justify-content:space-between; align-items:center;
    background: rgba(255,255,255,0.05);
    padding: 12px 14px;
    border-radius: 12px;
    margin-bottom: 8px;
    font-size: 13px;
  }
  .status-pending { color: #ffd200; }
  .status-approved { color: #4ade80; }
  .status-rejected { color: #f87171; }
  .empty-text { text-align:center; opacity: 0.5; font-size: 13px; padding: 20px 0;}
  .contact-btn {
    width: 100%;
    margin-top: 20px;
    padding: 14px;
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.15);
    background: transparent;
    color: white;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
  .modal-overlay {
    position: fixed; inset:0; background: rgba(0,0,0,0.6);
    display:none; align-items:center; justify-content:center; z-index: 999; padding: 20px;
  }
  .modal-overlay.show { display:flex; }
  .modal-box {
    background: #1e1e3f; border-radius: 18px; padding: 24px; width: 100%; max-width: 340px; text-align:center;
  }
  .modal-box .modal-icon { font-size: 40px; margin-bottom: 10px;}
  .modal-box h3 { font-size: 17px; margin-bottom: 8px;}
  .modal-box p { font-size: 13px; opacity: 0.75; margin-bottom: 20px; line-height: 1.5;}
  .toast {
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: #222; padding: 12px 20px; border-radius: 12px; font-size: 13px;
    opacity:0; transition: opacity 0.3s; pointer-events:none; z-index: 1000;
  }
  .toast.show { opacity: 1; }
</style>
</head>
<body>

<div class="header">
  <div class="diamond-icon">💎</div>
  <h1>Almaz Bot</h1>
</div>

<div class="card">
  <div class="balance-row">
    <div>
      <div class="balance-value" id="balance">0</div>
      <div class="balance-label">joriy balans</div>
    </div>
  </div>
  <div class="progress-wrap"><div class="progress-bar" id="progressBar" style="width:0%"></div></div>
  <div class="progress-text" id="progressText">0 / 210</div>
</div>

<div class="stats-grid">
  <div class="stat-box">
    <div class="num" id="refCount">0</div>
    <div class="lbl">Referallar</div>
  </div>
  <div class="stat-box">
    <div class="num" id="totalEarned">0</div>
    <div class="lbl">Jami topilgan</div>
  </div>
</div>

<div class="section-title">🔗 Referal havolangiz</div>
<div class="ref-link-box" id="refLink">yuklanmoqda...</div>
<div class="btn-row">
  <button class="btn btn-secondary" onclick="copyLink()">📋 Nusxalash</button>
  <button class="btn btn-primary" onclick="shareLink()">📤 Ulashish</button>
</div>

<button class="btn-withdraw" id="withdrawBtn" onclick="openModal()" disabled>💰 Olmos yechish</button>

<div class="section-title">🕓 So'rovlar tarixi</div>
<div id="historyList"><div class="empty-text">Hozircha so'rovlar yo'q</div></div>

<button class="contact-btn" onclick="contactAdmin()">💬 Admin bilan bog'lanish</button>

<div class="modal-overlay" id="modalOverlay">
  <div class="modal-box">
    <div class="modal-icon">💎</div>
    <h3>Olmosni yechishni tasdiqlaysizmi?</h3>
    <p id="modalText">Butun balansingiz yechish uchun so'rov yuboriladi. Admin tasdiqlagach mablag' o'tkaziladi.</p>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="closeModal()">Bekor qilish</button>
      <button class="btn btn-primary" onclick="confirmWithdraw()">Tasdiqlash</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let state = { balance: 0, min_withdraw: 210, referral_link: "", admin_username: "ruzvix" };

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

async function loadData() {
  try {
    const res = await fetch('/api/me', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ initData: tg.initData })
    });
    const data = await res.json();
    if (data.error) { showToast('Xatolik: ' + data.error); return; }
    state = data;
    render(data);
  } catch(e) {
    showToast('Ma\\'lumot yuklanmadi');
  }
}

function render(data) {
  document.getElementById('balance').textContent = data.balance;
  document.getElementById('refCount').textContent = data.referral_count;
  document.getElementById('totalEarned').textContent = data.total_earned;
  document.getElementById('refLink').textContent = data.referral_link;

  const pct = Math.min(100, Math.round((data.balance / data.min_withdraw) * 100));
  document.getElementById('progressBar').style.width = pct + '%';
  document.getElementById('progressText').textContent = data.balance + ' / ' + data.min_withdraw;

  const btn = document.getElementById('withdrawBtn');
  btn.disabled = data.balance < data.min_withdraw;
  btn.textContent = data.balance < data.min_withdraw
    ? '💰 Yechish (kamida ' + data.min_withdraw + ' kerak)'
    : '💰 Olmos yechish (' + data.balance + ')';

  const list = document.getElementById('historyList');
  if (!data.requests || data.requests.length === 0) {
    list.innerHTML = '<div class="empty-text">Hozircha so\\'rovlar yo\\'q</div>';
  } else {
    list.innerHTML = data.requests.map(r => {
      const statusMap = {pending:'⏳ Kutilmoqda', approved:'✅ Tasdiqlangan', rejected:'❌ Rad etilgan'};
      const cls = 'status-' + r.status;
      return '<div class="history-item"><span>' + r.amount + ' 💎 — ' + r.date + '</span>' +
             '<span class="' + cls + '">' + (statusMap[r.status] || r.status) + '</span></div>';
    }).join('');
  }
}

function copyLink() {
  navigator.clipboard.writeText(state.referral_link).then(() => {
    showToast('Havola nusxalandi ✅');
    tg.HapticFeedback.notificationOccurred('success');
  }).catch(() => showToast('Nusxalab bo\\'lmadi'));
}

function shareLink() {
  const url = 'https://t.me/share/url?url=' + encodeURIComponent(state.referral_link) +
              '&text=' + encodeURIComponent('Almaz Bot orqali olmos yig\\'ib pul ishlang! 💎');
  tg.openTelegramLink(url);
}

function contactAdmin() {
  tg.openTelegramLink('https://t.me/' + state.admin_username);
}

function openModal() {
  if (state.balance < state.min_withdraw) return;
  document.getElementById('modalText').textContent =
    state.balance + ' 💎 yechish uchun so\\'rov yuboriladi. Admin tasdiqlagach mablag\\' o\\'tkaziladi.';
  document.getElementById('modalOverlay').classList.add('show');
}
function closeModal() {
  document.getElementById('modalOverlay').classList.remove('show');
}

async function confirmWithdraw() {
  closeModal();
  try {
    const res = await fetch('/api/withdraw', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ initData: tg.initData })
    });
    const data = await res.json();
    if (data.error) {
      showToast('Xatolik: ' + data.error);
      return;
    }
    tg.HapticFeedback.notificationOccurred('success');
    showToast('So\\'rov yuborildi ✅ #' + data.request_id);
    loadData();
  } catch(e) {
    showToast('Xatolik yuz berdi');
  }
}

loadData();
</script>
</body>
</html>
"""


@app.route("/miniapp")
def miniapp():
    return Response(MINIAPP_HTML, mimetype="text/html")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT)
else:
    init_db()