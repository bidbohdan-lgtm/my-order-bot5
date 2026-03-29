import os
import json
import sqlite3
from datetime import datetime, date
from calendar import monthrange
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ───────────────────────────────────────────
# НАЛАШТУВАННЯ — замінити на свої значення
# ───────────────────────────────────────────
BOT_TOKEN = "8369105545:AAFrFZuN5JruXACoErkjYEhKKPKDaXhGB7I"
ADMIN_ID   = 6197295841        # ваш Telegram user_id (дізнатись у @userinfobot)
API_SECRET = "my_secret_key"    # секрет для захисту API з сайту
# ───────────────────────────────────────────

DB_PATH = "orders.db"

# ═══════════════════════════════════════════
# БАЗА ДАНИХ
# ═══════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            client    TEXT NOT NULL,
            phone     TEXT,
            desc      TEXT NOT NULL,
            price     REAL DEFAULT 0,
            status    TEXT DEFAULT 'new',
            created   TEXT NOT NULL,
            updated   TEXT
        )
    """)
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect(DB_PATH)

def add_order(client, phone, desc, price):
    now = datetime.now().isoformat()
    with db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO orders (client,phone,desc,price,status,created) VALUES (?,?,?,?,?,?)",
            (client, phone, desc, price, "new", now)
        )
        conn.commit()
        return c.lastrowid

def update_status(order_id, status):
    with db() as conn:
        conn.execute(
            "UPDATE orders SET status=?, updated=? WHERE id=?",
            (status, datetime.now().isoformat(), order_id)
        )
        conn.commit()

def get_order(order_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    return row

def get_orders_by_period(start: date, end: date):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE date(created) BETWEEN ? AND ? ORDER BY created DESC",
            (start.isoformat(), end.isoformat())
        ).fetchall()
    return rows

# ═══════════════════════════════════════════
# ФОРМАТУВАННЯ
# ═══════════════════════════════════════════

STATUS_EMOJI = {"new": "🆕", "cooking": "🍳", "ready": "✅"}
STATUS_UA    = {"new": "Нове", "cooking": "Готується", "ready": "Готове"}

def fmt_order(row):
    oid, client, phone, desc, price, status, created, updated = row
    dt = datetime.fromisoformat(created).strftime("%d.%m %H:%M")
    ph = f"\n📞 {phone}" if phone else ""
    pr = f"\n💰 {price:.0f} ₴" if price else ""
    return (
        f"{STATUS_EMOJI.get(status,'❓')} <b>Замовлення #{oid}</b>\n"
        f"👤 {client}{ph}\n"
        f"📝 {desc}{pr}\n"
        f"📅 {dt} | {STATUS_UA.get(status, status)}"
    )

def order_keyboard(order_id, current_status):
    buttons = []
    if current_status != "cooking":
        buttons.append(InlineKeyboardButton("🍳 Готується", callback_data=f"status:{order_id}:cooking"))
    if current_status != "ready":
        buttons.append(InlineKeyboardButton("✅ Готове",    callback_data=f"status:{order_id}:ready"))
    if current_status != "new":
        buttons.append(InlineKeyboardButton("🆕 Нове",      callback_data=f"status:{order_id}:new"))
    return InlineKeyboardMarkup([buttons])

def checklist_text(rows, title):
    if not rows:
        return f"📋 <b>{title}</b>\n\nЗамовлень немає."
    total_sum = sum(r[4] for r in rows if r[4])
    total_cnt = len(rows)
    lines = [f"📋 <b>{title}</b>", f"Всього: {total_cnt} замовлень | 💰 {total_sum:.0f} ₴\n"]
    for r in rows:
        oid, client, phone, desc, price, status, created, _ = r
        dt = datetime.fromisoformat(created).strftime("%d.%m %H:%M")
        pr = f" — {price:.0f}₴" if price else ""
        lines.append(f"{STATUS_EMOJI.get(status,'❓')} #{oid} {client}{pr}\n   {desc[:40]}{'…' if len(desc)>40 else ''} | {dt}")
    return "\n".join(lines)

# ═══════════════════════════════════════════
# КОМАНДИ БОТА
# ═══════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "👋 Привіт! Я бот для замовлень.\n\n"
        "/today — замовлення за сьогодні\n"
        "/month — замовлення за цей місяць\n"
        "/lastmonth — попередній місяць\n"
        "/stats — загальна статистика",
        parse_mode="HTML"
    )

async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    today = date.today()
    rows = get_orders_by_period(today, today)
    await update.message.reply_text(checklist_text(rows, "Сьогодні"), parse_mode="HTML")

async def cmd_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    today = date.today()
    start = today.replace(day=1)
    end   = today.replace(day=monthrange(today.year, today.month)[1])
    rows  = get_orders_by_period(start, end)
    month_ua = today.strftime("%B %Y")
    await update.message.reply_text(checklist_text(rows, f"Цей місяць ({month_ua})"), parse_mode="HTML")

async def cmd_lastmonth(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    today = date.today()
    first_this = today.replace(day=1)
    last_prev  = (first_this.replace(day=1) - __import__('datetime').timedelta(days=1))
    start      = last_prev.replace(day=1)
    rows       = get_orders_by_period(start, last_prev)
    month_ua   = last_prev.strftime("%B %Y")
    await update.message.reply_text(checklist_text(rows, f"Попередній місяць ({month_ua})"), parse_mode="HTML")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    today = date.today()
    start_month = today.replace(day=1)
    all_rows    = get_orders_by_period(date(2000,1,1), today)
    month_rows  = get_orders_by_period(start_month, today)
    total_cnt   = len(all_rows)
    total_sum   = sum(r[4] for r in all_rows if r[4])
    month_cnt   = len(month_rows)
    month_sum   = sum(r[4] for r in month_rows if r[4])
    new_cnt     = sum(1 for r in all_rows if r[5] == "new")
    cooking_cnt = sum(1 for r in all_rows if r[5] == "cooking")
    ready_cnt   = sum(1 for r in all_rows if r[5] == "ready")
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"📅 <b>Цей місяць:</b> {month_cnt} замовлень | {month_sum:.0f} ₴\n"
        f"📦 <b>Всього:</b> {total_cnt} замовлень | {total_sum:.0f} ₴\n\n"
        f"🆕 Нові: {new_cnt}\n"
        f"🍳 Готуються: {cooking_cnt}\n"
        f"✅ Готові: {ready_cnt}"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def callback_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    _, order_id, new_status = query.data.split(":")
    order_id = int(order_id)
    update_status(order_id, new_status)
    row = get_order(order_id)
    await query.edit_message_text(
        fmt_order(row),
        parse_mode="HTML",
        reply_markup=order_keyboard(order_id, new_status)
    )

# ═══════════════════════════════════════════
# HTTP API ДЛЯ САЙТУ (приймає замовлення)
# ═══════════════════════════════════════════
# Запускається паралельно через aiohttp
# POST /new_order
# Headers: X-Secret: my_secret_key
# Body JSON: { "client":"Ім'я", "phone":"...", "desc":"...", "price": 250 }

from aiohttp import web

_bot_app = None

async def handle_new_order(request: web.Request):
    if request.headers.get("X-Secret") != API_SECRET:
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    client = data.get("client", "Невідомий")
    phone  = data.get("phone", "")
    desc   = data.get("desc", "")
    price  = float(data.get("price", 0))

    if not desc:
        return web.json_response({"error": "desc required"}, status=400)

    order_id = add_order(client, phone, desc, price)
    row      = get_order(order_id)

    # Надіслати адміну в Telegram
    await _bot_app.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 <b>Нове замовлення!</b>\n\n{fmt_order(row)}",
        parse_mode="HTML",
        reply_markup=order_keyboard(order_id, "new")
    )
    return web.json_response({"ok": True, "order_id": order_id})

async def run_web():
    app = web.Application()
    app.router.add_post("/new_order", handle_new_order)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("✅ HTTP API запущено на порту 8080")

# ═══════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════

async def post_init(application):
    global _bot_app
    _bot_app = application
    await run_web()

def main():
    init_db()
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start",     cmd_start))
    application.add_handler(CommandHandler("today",     cmd_today))
    application.add_handler(CommandHandler("month",     cmd_month))
    application.add_handler(CommandHandler("lastmonth", cmd_lastmonth))
    application.add_handler(CommandHandler("stats",     cmd_stats))
    application.add_handler(CallbackQueryHandler(callback_status, pattern=r"^status:"))
    print("🤖 Бот запущено!")
    application.run_polling()

if __name__ == "__main__":
    main()
