import json
import logging
import sqlite3
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import traceback

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота (будет браться из переменной окружения)
TOKEN = os.environ.get('BOT_TOKEN', '8685226609:AAEA8vHoWELRP7_KwXfV9Qbpq1usLUfdJ6o')

# ID администратора
ADMIN_ID = 860845946

# URL для личного кабинета
PERSONAL_ACCOUNT_URL = "https://partners-app.yandex.ru/team_ref/8647844ed8ee4d0eb3d60155113dafb1?locale=ru"

# URL для калькулятора дохода
CALCULATOR_URL = "https://eda.yandex.ru/partner/perf/samara/?utm_medium=cpc&utm_source=yandex-hr&utm_campaign=%5BEDA%5DMX_Courier_RU-ALL-1M_Brand_search_NU%7C73792274&utm_term=49415175552%7C---autotargeting&utm_content=k50id%7C0100000049415175552_49415175552%7Ccid%7C73792274%7Cgid%7C5378729251%7Caid%7C15662855932%7Cadp%7Cno%7Cpos%7Cpremium1%7Csrc%7Csearch_none%7Cdvc%7Cdesktop%7Cmain&etext=2202.H1-umiWOxa1IhaqocPaUS69zT9wHAZdkgZEGqorPY5rJ_ebzkat1FDn2yZO3bEqDYssRPcp0IyJXzD9sTJXJ7293dG14ZXB1Z2VrdW1hemM.0d27564e0c3a01c61971ab0f3d5b481a3ae88ee1&yclid=14506292526793097215"

# Инициализация базы данных
def init_database():
    conn = sqlite3.connect('/tmp/users.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  registration_date TEXT,
                  balance REAL DEFAULT 0,
                  test_passed INTEGER DEFAULT 0,
                  withdrawal_info TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount REAL,
                  payment_method TEXT,
                  payment_details TEXT,
                  status TEXT DEFAULT 'pending',
                  request_date TEXT,
                  FOREIGN KEY (user_id) REFERENCES users (user_id))''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_db():
    return sqlite3.connect('/tmp/users.db', check_same_thread=False)

def is_registered(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def register_user(user_id, username, first_name, last_name):
    conn = get_db()
    c = conn.cursor()
    registration_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registration_date) VALUES (?, ?, ?, ?, ?)",
              (user_id, username, first_name, last_name, registration_date))
    conn.commit()
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_registered(user.id):
        register_user(user.id, user.username, user.first_name, user.last_name)
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            "Вы успешно зарегистрированы в системе."
        )
    
    keyboard = [
        [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
        [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
        [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
        [InlineKeyboardButton("👤 Личный кабинет", url=PERSONAL_ACCOUNT_URL)],
        [InlineKeyboardButton("🆘 Обратиться в поддержку", callback_data='support')]
    ]
    
    await update.message.reply_text(
        "🏠 *Главное меню*\n\n"
        "Выберите нужный раздел:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# Обработчик callback-запросов (пока упрощённый, чтобы не грузить)
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    await query.edit_message_text(f"Вы выбрали: {data}")

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Используйте /start")

# Заглушки для админских команд
async def admin_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Админ-панель")

async def admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Подтверждение")

# === ЭТО НОВАЯ ЧАСТЬ ДЛЯ KOYEB ===
# Функция для запуска бота
async def run_bot():
    """Создаёт приложение и запускает polling."""
    logger.info("Запуск бота...")
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_requests))
    application.add_handler(CommandHandler("confirm", admin_confirm))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await application.initialize()
    await application.start()
    logger.info("Бот запущен и работает.")
    # Запускаем polling (это бесконечный процесс)
    await application.updater.start_polling()
    
    # Держим бота запущенным
    while True:
        await asyncio.sleep(3600)

# Основная функция для Koyeb (точка входа)
def main():
    init_database()
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")

if __name__ == "__main__":
    main()
