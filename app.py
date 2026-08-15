"""
app.py — Render.com (yoki boshqa "Web Service" turidagi hosting) uchun
kichik ko'prik fayl.

NIMA UCHUN KERAK?
  Render "Web Service" bir narsani talab qiladi: dastur biror PORTni
  tinglashi (listen) kerak, aks holda Render uni "ishlamayapti" deb
  hisoblaydi va xato beradi (aynan sizda bo'lgani kabi).
  Lekin Telegram bot polling rejimida hech qanday portni ochmaydi.

  Shuning uchun bu fayl:
    1) Flask orqali juda kichik "men tirikman" server ochadi (Render shuni ko'radi)
    2) bot_core.py dagi butun botni ALOHIDA FON OQIMIDA (background thread)
       polling rejimida ishga tushiradi

Render'da "Start Command" shu bo'lishi kerak:
    gunicorn app:app
"""

import asyncio
import threading

from flask import Flask
import bot_core

app = Flask(name)

_bot_started = False
_bot_lock = threading.Lock()


@app.route("/")
def health():
    return "Empire Tap bot ishlab turibdi ✅"


def _run_bot_in_thread():
    """Botni alohida event loop bilan fon oqimida ishga tushiradi."""
    asyncio.set_event_loop(asyncio.new_event_loop())
    application = bot_core.build_application()
    application.run_polling(allowed_updates=bot_core.Update.ALL_TYPES, stop_signals=None)


def _ensure_bot_started():
    global _bot_started
    with _bot_lock:
        if not _bot_started:
            thread = threading.Thread(target=_run_bot_in_thread, daemon=True)
            thread.start()
            _bot_started = True


# Modul import qilinganda (gunicorn app:app ishga tushirganda) botni ham ishga tushiramiz
_ensure_bot_started()


if name == "main":
    # Mahalliy (local) sinov uchun: python app.py
    app.run(host="0.0.0.0", port=8080)
