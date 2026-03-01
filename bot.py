import json
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import traceback
import random
import uuid
import os
import threading
import atexit
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = '8685226609:AAEA8vHoWELRP7_KwXfV9Qbpq1usLUfdJ6o'

# ID администратора
ADMIN_ID = 860845946

# URL для личного кабинета
PERSONAL_ACCOUNT_URL = "https://partners-app.yandex.ru/team_ref/8647844ed8ee4d0eb3d60155113dafb1?locale=ru"

# URL для калькулятора дохода
CALCULATOR_URL = "https://eda.yandex.ru/partner/perf/samara/?utm_medium=cpc&utm_source=yandex-hr&utm_campaign=%5BEDA%5DMX_Courier_RU-ALL-1M_Brand_search_NU%7C73792274&utm_term=49415175552%7C---autotargeting&utm_content=k50id%7C0100000049415175552_49415175552%7Ccid%7C73792274%7Cgid%7C5378729251%7Caid%7C15662855932%7Cadp%7Cno%7Cpos%7Cpremium1%7Csrc%7Csearch_none%7Cdvc%7Cdesktop%7Cmain&etext=2202.H1-umiWOxa1IhaqocPaUS69zT9wHAZdkgZEGqorPY5rJ_ebzkat1FDn2yZO3bEqDYssRPcp0IyJXzD9sTJXJ7293dG14ZXB1Z2VrdW1hemM.0d27564e0c3a01c61971ab0f3d5b481a3ae88ee1&yclid=14506292526793097215"

# ========== ПОСТОЯННОЕ ХРАНЕНИЕ ДАННЫХ ==========
DB_CONN = None

def init_database():
    """Инициализирует БД в памяти и загружает данные из файла"""
    global DB_CONN
    DB_CONN = sqlite3.connect(':memory:', check_same_thread=False)
    c = DB_CONN.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  registration_date TEXT,
                  balance REAL DEFAULT 0,
                  test_passed INTEGER DEFAULT 0,
                  test_attempts INTEGER DEFAULT 0,
                  last_test_attempt TEXT)''')
    
    # Таблица заявок на вывод
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount REAL,
                  payment_method TEXT,
                  payment_details TEXT,
                  status TEXT DEFAULT 'pending',
                  request_date TEXT)''')
    
    # Таблица тикетов поддержки
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets
                 (ticket_id TEXT PRIMARY KEY,
                  user_id INTEGER,
                  username TEXT,
                  first_name TEXT,
                  message TEXT,
                  status TEXT DEFAULT 'open',
                  created_at TEXT,
                  answered_at TEXT,
                  admin_reply TEXT)''')
    
    # Таблица курьеров
    c.execute('''CREATE TABLE IF NOT EXISTS couriers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  recruiter_id INTEGER,
                  full_name TEXT,
                  city TEXT,
                  registered_at TEXT)''')
    
    # Загружаем сохраненные данные
    if os.path.exists('backup.json'):
        try:
            with open('backup.json', 'r') as f:
                backup = json.load(f)
            
            # Восстанавливаем users
            for row in backup.get('users', []):
                c.execute('''INSERT OR REPLACE INTO users 
                             VALUES (?,?,?,?,?,?,?,?,?)''', row)
            
            # Восстанавливаем withdrawals
            for row in backup.get('withdrawals', []):
                c.execute('''INSERT INTO withdrawals 
                             VALUES (?,?,?,?,?,?,?)''', row)
            
            # Восстанавливаем tickets
            for row in backup.get('tickets', []):
                c.execute('''INSERT INTO support_tickets 
                             VALUES (?,?,?,?,?,?,?,?,?)''', row)
            
            # Восстанавливаем couriers
            for row in backup.get('couriers', []):
                c.execute('''INSERT INTO couriers 
                             VALUES (?,?,?,?,?)''', row)
            
            DB_CONN.commit()
            logger.info(f"✅ Загружены данные из backup.json")
        except Exception as e:
            logger.error(f"Ошибка загрузки backup: {e}")
    
    # Запускаем автосохранение
    start_auto_backup()

def get_db():
    global DB_CONN
    if DB_CONN is None:
        init_database()
    return DB_CONN

def backup_database():
    """Сохраняет все данные в JSON"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        backup = {
            'users': c.execute("SELECT * FROM users").fetchall(),
            'withdrawals': c.execute("SELECT * FROM withdrawals").fetchall(),
            'tickets': c.execute("SELECT * FROM support_tickets").fetchall(),
            'couriers': c.execute("SELECT * FROM couriers").fetchall(),
            'timestamp': datetime.now().isoformat()
        }
        
        with open('backup.json', 'w') as f:
            json.dump(backup, f, default=str)
        
        logger.info("💾 Данные сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

def start_auto_backup():
    """Запускает автосохранение в фоне"""
    def auto_backup_worker():
        while True:
            import time
            time.sleep(300)  # 5 минут
            backup_database()
    
    thread = threading.Thread(target=auto_backup_worker, daemon=True)
    thread.start()

# Сохраняем при выходе
atexit.register(backup_database)

# ========== GOOGLE SHEETS ИНТЕГРАЦИЯ ==========
def get_google_sheet():
    """Подключается к Google Sheets и возвращает рабочий лист"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 
                 'https://www.googleapis.com/auth/drive']
        
        creds_json = os.environ.get('GOOGLE_CREDS_JSON')
        
        if creds_json:
            creds_dict = json.loads(creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        
        client = gspread.authorize(creds)
        
        sheet_id = os.environ.get('GOOGLE_SHEET_ID', '')
        if not sheet_id:
            logger.error("GOOGLE_SHEET_ID не задан")
            return None
            
        sheet = client.open_by_key(sheet_id).sheet1
        logger.info("✅ Подключение к Google Sheets установлено")
        return sheet
    except Exception as e:
        logger.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

def add_courier_to_google_sheet(recruiter_name, recruiter_username, full_name, city):
    """Добавляет запись о курьере в Google Sheets"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            return False
        
        row = [
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            recruiter_name,
            f"@{recruiter_username}" if recruiter_username else "-",
            full_name,
            city
        ]
        sheet.append_row(row)
        logger.info(f"✅ Курьер {full_name} добавлен в Google Sheets")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления в Google Sheets: {e}")
        return False

# ========== ФУНКЦИИ ПРОВЕРКИ ПОЛЬЗОВАТЕЛЕЙ ==========
def is_registered(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    return result is not None

def register_user(user_id, username, first_name, last_name):
    conn = get_db()
    c = conn.cursor()
    registration_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registration_date, balance) VALUES (?, ?, ?, ?, ?, 0)",
              (user_id, username, first_name, last_name, registration_date))
    conn.commit()

def update_test_status(user_id, passed):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET test_passed = ?, last_test_attempt = ? WHERE user_id = ?",
              (1 if passed else 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()

def can_take_test(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed, last_test_attempt FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if not result:
        return True, 0
    
    test_passed, last_attempt_str = result
    
    if test_passed == 1:
        return True, 0
    
    if last_attempt_str:
        last_attempt = datetime.strptime(last_attempt_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        time_diff = now - last_attempt
        
        if time_diff < timedelta(minutes=30):
            remaining = 30 - int(time_diff.total_seconds() / 60)
            return False, remaining
    
    return True, 0

# ========== ТЕСТОВЫЕ ВОПРОСЫ ==========
TEST_QUESTIONS = [
    {
        'question': 'Что произойдет с профилем рекрутера, если его курьер нарушает правила сервиса?',
        'options': [
            'Ничего, отвечает только курьер',
            'Профиль рекрутера может быть заблокирован',
            'Рекрутер получит штраф 1000 рублей',
            'Курьер получит предупреждение'
        ],
        'correct': 1
    },
    {
        'question': 'Как правильно писать текст вакансии, чтобы не нарушить правила?',
        'options': [
            '"Яндекс Еда ищет курьеров"',
            '"Партнер Яндекс Еды ищет курьеров"',
            '"Срочно требуются курьеры в Яндекс"',
            '"Работа в Яндекс Еде"'
        ],
        'correct': 1
    },
    {
        'question': 'Где категорически нельзя размещать вакансии?',
        'options': [
            'В тематических Telegram-каналах о работе',
            'В комментариях под постами других рекрутеров',
            'На Авито в разделе "Работа"',
            'В группах ВКонтакте о доставке'
        ],
        'correct': 1
    },
    {
        'question': 'Какие документы нужны гражданину РФ для оформления курьером (16+)?',
        'options': [
            'Только паспорт',
            'Паспорт с регистрацией, ИНН, медкнижка (если есть), согласие родителей',
            'Паспорт и СНИЛС',
            'Только ИНН'
        ],
        'correct': 1
    },
    {
        'question': 'Какие документы нужны гражданину Беларуси для оформления курьером?',
        'options': [
            'Только паспорт',
            'Паспорт, ИНН, СНИЛС, трудовой договор',
            'Только миграционная карта',
            'Паспорт и регистрация'
        ],
        'correct': 1
    },
    {
        'question': 'Что такое целевое действие (ЦД)?',
        'options': [
            'Количество заказов, которое нужно выполнить курьеру после оформления',
            'Первая доставка курьера',
            'Регистрация в приложении',
            'Выход на первый слот'
        ],
        'correct': 0
    },
    {
        'question': 'Какой максимальный норматив целевого действия (ЦД)?',
        'options': [
            '50 заказов',
            '100 заказов',
            '130 заказов',
            '200 заказов'
        ],
        'correct': 2
    },
    {
        'question': 'Сколько заказов минимально должен сделать кандидат, чтобы рекрутер мог чувствовать себя в безопасности?',
        'options': [
            'Достаточно 5 заказов',
            'Хотя бы 15 заказов',
            'Минимум 25 заказов',
            'Нужно 30 заказов'
        ],
        'correct': 2
    },
    {
        'question': 'Что получает курьер дополнительно за заказ весом от 10 до 15 кг?',
        'options': [
            'Ничего, это обычный заказ',
            'Дополнительную выплату',
            'Повышенный коэффициент',
            'Бесплатный обед в ресторане'
        ],
        'correct': 1
    },
    {
        'question': 'Что происходит, если курьер ждёт заказ в ресторане более 20 минут?',
        'options': [
            'Время ожидания не оплачивается',
            'Время ожидания оплачивается',
            'Курьер может уйти без заказа',
            'Ресторан платит штраф курьеру'
        ],
        'correct': 1
    }
]

# ========== ФУНКЦИИ ДЛЯ УДАЛЕНИЯ СООБЩЕНИЙ ==========
async def delete_previous_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет предыдущее сообщение бота"""
    try:
        if 'last_bot_message_id' in context.user_data and 'last_chat_id' in context.user_data:
            await context.bot.delete_message(
                chat_id=context.user_data['last_chat_id'],
                message_id=context.user_data['last_bot_message_id']
            )
    except Exception:
        pass

async def send_and_track(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    """Отправляет сообщение и сохраняет его ID"""
    await delete_previous_message(update, context)
    
    if update.callback_query:
        message = await update.callback_query.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    else:
        message = await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    
    context.user_data['last_bot_message_id'] = message.message_id
    context.user_data['last_chat_id'] = message.chat_id
    return message

async def edit_and_track(query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    """Редактирует сообщение и сохраняет ID"""
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    context.user_data['last_bot_message_id'] = query.message.message_id
    context.user_data['last_chat_id'] = query.message.chat_id

# ========== ФУНКЦИИ ПОДДЕРЖКИ ==========
def create_support_ticket(user_id, username, first_name, message):
    """Создает новый тикет поддержки"""
    conn = get_db()
    c = conn.cursor()
    ticket_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('''INSERT INTO support_tickets 
                 (ticket_id, user_id, username, first_name, message, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (ticket_id, user_id, username, first_name, message, created_at))
    
    conn.commit()
    return ticket_id

def get_open_tickets():
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT ticket_id, user_id, username, first_name, message, created_at 
                 FROM support_tickets 
                 WHERE status = 'open' 
                 ORDER BY created_at ASC''')
    return c.fetchall()

def get_ticket(ticket_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT * FROM support_tickets WHERE ticket_id = ?''', (ticket_id,))
    return c.fetchone()

def close_ticket(ticket_id, admin_reply):
    conn = get_db()
    c = conn.cursor()
    answered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''UPDATE support_tickets 
                 SET status = 'closed', answered_at = ?, admin_reply = ? 
                 WHERE ticket_id = ?''',
              (answered_at, admin_reply, ticket_id))
    conn.commit()

# ========== ФУНКЦИИ ДЛЯ ВЫВОДА ==========
def get_user_balance(user_id):
    """Получает баланс пользователя"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    return result[0] if result else 0

def create_withdrawal_request(user_id, amount, method, details):
    """Создает заявку на вывод"""
    conn = get_db()
    c = conn.cursor()
    request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO withdrawals 
                 (user_id, amount, payment_method, payment_details, request_date, status) 
                 VALUES (?, ?, ?, ?, ?, 'pending')''',
              (user_id, amount, method, details, request_date))
    request_id = c.lastrowid
    conn.commit()
    return request_id

def get_pending_withdrawals():
    """Получает все ожидающие заявки на вывод"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT w.id, w.user_id, u.first_name, u.username, 
                        w.amount, w.payment_method, w.payment_details, w.request_date
                 FROM withdrawals w
                 JOIN users u ON w.user_id = u.user_id
                 WHERE w.status = 'pending'
                 ORDER BY w.request_date ASC''')
    return c.fetchall()

def confirm_withdrawal(request_id):
    """Подтверждает заявку на вывод"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE withdrawals SET status = 'completed' WHERE id = ?", (request_id,))
    conn.commit()

# ========== ФУНКЦИИ ДЛЯ КУРЬЕРОВ ==========
def add_courier(recruiter_id, full_name, city):
    """Добавляет курьера в базу и Google Sheets"""
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем, нет ли уже такого курьера у этого рекрутера
    c.execute('''SELECT id FROM couriers 
                 WHERE recruiter_id = ? AND full_name = ? AND city = ?''',
              (recruiter_id, full_name, city))
    exists = c.fetchone()
    
    if exists:
        conn.close()
        return False, "Курьер с такими данными уже записан"
    
    registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO couriers (recruiter_id, full_name, city, registered_at)
                 VALUES (?, ?, ?, ?)''',
              (recruiter_id, full_name, city, registered_at))
    conn.commit()
    
    # Получаем данные рекрутера для Google Sheets
    c.execute("SELECT first_name, username FROM users WHERE user_id = ?", (recruiter_id,))
    recruiter = c.fetchone()
    recruiter_name = recruiter[0] if recruiter else "Неизвестно"
    recruiter_username = recruiter[1] if recruiter else ""
    
    conn.close()
    
    # Отправляем в Google Sheets (в отдельном потоке, чтобы не тормозить бота)
    try:
        threading.Thread(
            target=add_courier_to_google_sheet,
            args=(recruiter_name, recruiter_username, full_name, city),
            daemon=True
        ).start()
        logger.info(f"Запущена отправка в Google Sheets для курьера {full_name}")
    except Exception as e:
        logger.error(f"Ошибка запуска потока для Google Sheets: {e}")
    
    return True, "Курьер успешно записан"

def get_recruiter_couriers(recruiter_id):
    """Получает всех курьеров рекрутера"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT full_name, city, registered_at 
                 FROM couriers 
                 WHERE recruiter_id = ? 
                 ORDER BY registered_at DESC''', (recruiter_id,))
    return c.fetchall()

# ========== ФУНКЦИИ ДЛЯ УДАЛЕНИЯ СООБЩЕНИЙ ==========
async def delete_previous_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет предыдущее сообщение бота"""
    try:
        if 'last_bot_message_id' in context.user_data and 'last_chat_id' in context.user_data:
            await context.bot.delete_message(
                chat_id=context.user_data['last_chat_id'],
                message_id=context.user_data['last_bot_message_id']
            )
    except Exception:
        pass

async def send_and_track(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    """Отправляет сообщение и сохраняет его ID"""
    await delete_previous_message(update, context)
    
    if update.callback_query:
        message = await update.callback_query.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    else:
        message = await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    
    context.user_data['last_bot_message_id'] = message.message_id
    context.user_data['last_chat_id'] = message.chat_id
    return message

async def edit_and_track(query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    """Редактирует сообщение и сохраняет ID"""
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    context.user_data['last_bot_message_id'] = query.message.message_id
    context.user_data['last_chat_id'] = query.message.chat_id

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_previous_message(update, context)
    
    user = update.effective_user
    user_id = user.id
    
    if not is_registered(user_id):
        register_user(user_id, user.username, user.first_name, user.last_name)
        await send_and_track(
            update, context,
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            "Вы успешно зарегистрированы в системе."
        )
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    test_passed = result[0] if result else 0
    
    if test_passed == 1:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
            [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
            [InlineKeyboardButton("👤 Личный кабинет", callback_data='personal_account')],
            [InlineKeyboardButton("🆘 Обратиться в поддержку", callback_data='support')]
        ]
        menu_text = "🏠 *Главное меню*\n\nВыберите нужный раздел:"
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')]
        ]
        menu_text = "📚 *Для доступа к полному функционалу необходимо пройти тест*\n\nВыберите действие:"
    
    await send_and_track(
        update, context,
        menu_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Обработка админских кнопок
    if data.startswith('admin_reply_'):
        await admin_reply_callback(update, context)
        return
    elif data.startswith('admin_close_'):
        await admin_close_callback(update, context)
        return
    elif data.startswith('withdrawal_confirm_'):
        await admin_withdrawal_confirm(update, context)
        return
    elif data == 'next_question':
        await next_question_callback(update, context)
        return
    
    # Проверка доступа для обычных пользователей
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    test_passed = result[0] if result else 0
    
    protected_sections = ['withdrawal', 'personal_account', 'my_couriers', 'add_courier']
    if test_passed == 0 and data in protected_sections:
        keyboard = [[InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')]]
        await edit_and_track(
            query, context,
            "❌ *Доступ запрещен!*\n\nДля доступа к этому разделу необходимо пройти тест.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # Обработка остальных callback'ов
    if data == 'all_info':
        await show_all_info_menu(query, context)
    elif data == 'take_test':
        await start_test(query, user_id, context)
    elif data == 'withdrawal':
        await withdrawal_menu(query, user_id, context)
    elif data == 'personal_account':
        await personal_account_menu(query, user_id, context)
    elif data == 'my_couriers':
        await show_my_couriers(query, user_id, context)
    elif data == 'add_courier':
        await add_courier_start(query, user_id, context)
    elif data == 'support':
        await support_start(query, user_id, context)
    elif data.startswith('info_'):
        await show_info_section(query, context)
    elif data == 'back_to_main':
        await back_to_main(query, user_id, context)
    elif data == 'back_to_info':
        await show_all_info_menu(query, context)
    elif data.startswith('answer_'):
        await handle_test_answer(query, user_id, context)
    elif data in ['withdrawal_card', 'withdrawal_yoomoney', 'withdrawal_other']:
        await process_withdrawal_option(query, user_id, context)

# ========== ВЫВОД СРЕДСТВ ==========
async def withdrawal_menu(query, user_id, context):
    balance = get_user_balance(user_id)
    
    text = (
        f"💰 *Вывод средств*\n\n"
        f"💳 *Ваш баланс:* {balance} руб.\n"
        f"⏱ *Обновляется:* каждые 24 часа\n\n"
        f"Выберите способ вывода:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Карта", callback_data='withdrawal_card')],
        [InlineKeyboardButton("📱 ЮMoney", callback_data='withdrawal_yoomoney')],
        [InlineKeyboardButton("🔄 Другой способ", callback_data='withdrawal_other')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    
    await edit_and_track(
        query, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def process_withdrawal_option(query, user_id, context):
    method = query.data.replace('withdrawal_', '')
    context.user_data['withdrawal_method'] = method
    
    keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data='withdrawal')]]
    await edit_and_track(
        query, context,
        f"Выбран способ: *{method}*\n\n"
        f"Введите сумму и реквизиты в формате:\n"
        f"Сумма|Реквизиты\n\n"
        f"Пример: 500|1234567890123456",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_withdrawal_details'] = True

async def handle_withdrawal_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    
    try:
        amount, details = text.split('|')
        amount = float(amount.strip())
        details = details.strip()
        method = context.user_data.get('withdrawal_method', 'unknown')
        balance = get_user_balance(user.id)
        
        if amount < 100:
            await send_and_track(
                update, context,
                "❌ Минимальная сумма вывода: 100 руб."
            )
            return
        
        if amount > balance:
            await send_and_track(
                update, context,
                f"❌ Недостаточно средств. Ваш баланс: {balance} руб."
            )
            return
        
        request_id = create_withdrawal_request(user.id, amount, method, details)
        
        await send_and_track(
            update, context,
            f"✅ *Заявка на вывод создана!*\n\n"
            f"🆔 Номер заявки: `{request_id}`\n"
            f"💰 Сумма: {amount} руб.\n"
            f"💳 Способ: {method}\n\n"
            f"Ожидайте подтверждения администратором.",
            parse_mode='Markdown'
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f'withdrawal_confirm_{request_id}')]
        ]
        
        admin_message = (
            f"💰 *НОВАЯ ЗАЯВКА НА ВЫВОД*\n\n"
            f"🆔 *Заявка:* `{request_id}`\n"
            f"👤 *Пользователь:* {user.first_name} (@{user.username})\n"
            f"🆔 *User ID:* `{user.id}`\n"
            f"💰 *Сумма:* {amount} руб.\n"
            f"💳 *Способ:* {method}\n"
            f"📝 *Реквизиты:* {details}"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except ValueError:
        await send_and_track(
            update, context,
            "❌ Неверный формат. Используйте: Сумма|Реквизиты\n"
            "Пример: 500|1234567890123456"
        )
    except Exception as e:
        await send_and_track(
            update, context,
            f"❌ Ошибка: {str(e)}"
        )
    
    context.user_data['awaiting_withdrawal_details'] = False

async def admin_withdrawal_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    request_id = int(query.data.replace('withdrawal_confirm_', ''))
    confirm_withdrawal(request_id)
    
    await query.edit_message_text(
        f"✅ Заявка {request_id} подтверждена"
    )

# ========== ПОДДЕРЖКА ==========
async def support_start(query, user_id, context):
    text = (
        "🆘 *Поддержка*\n\n"
        "Опишите вашу проблему или вопрос. Я передам сообщение администратору.\n\n"
        "⏱ *Время ответа:* от 15 минут до 1 часа\n\n"
        "Напишите ваш вопрос одним сообщением:"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data='back_to_main')]]
    await edit_and_track(
        query, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_support_message'] = True

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text
    
    ticket_id = create_support_ticket(
        user.id,
        user.username,
        user.first_name,
        message_text
    )
    
    await delete_previous_message(update, context)
    await send_and_track(
        update, context,
        f"✅ *Ваше обращение принято!*\n\n"
        f"🆔 Номер обращения: `{ticket_id}`\n"
        f"⏱ Ожидаемое время ответа: от 15 минут до 1 часа\n\n"
        f"Как только администратор ответит, вы получите уведомление.",
        parse_mode='Markdown'
    )
    
    keyboard = [
        [InlineKeyboardButton("📨 Ответить", callback_data=f'admin_reply_{ticket_id}')],
        [InlineKeyboardButton("✅ Закрыть", callback_data=f'admin_close_{ticket_id}')]
    ]
    
    admin_message = (
        f"🆘 *НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ*\n\n"
        f"🆔 *Тикет:* `{ticket_id}`\n"
        f"👤 *Пользователь:* {user.first_name} (@{user.username})\n"
        f"🆔 *User ID:* `{user.id}`\n"
        f"📅 *Время:* {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"📝 *Сообщение:*\n{message_text}"
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_support_message'] = False

async def admin_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    ticket_id = query.data.replace('admin_reply_', '')
    context.user_data['replying_to_ticket'] = ticket_id
    
    await query.edit_message_text(
        f"📝 Введите ответ для тикета `{ticket_id}`:",
        parse_mode='Markdown'
    )

async def admin_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    ticket_id = query.data.replace('admin_close_', '')
    ticket = get_ticket(ticket_id)
    
    if ticket:
        close_ticket(ticket_id, "Тикет закрыт администратором")
        
        await context.bot.send_message(
            chat_id=ticket[1],
            text=f"🆘 *Обращение #{ticket_id} закрыто*\n\nВаш тикет был закрыт администратором.",
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(f"✅ Тикет {ticket_id} закрыт")
    else:
        await query.edit_message_text("❌ Тикет не найден")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    ticket_id = context.user_data.get('replying_to_ticket')
    if not ticket_id:
        return
    
    reply_text = update.message.text
    ticket = get_ticket(ticket_id)
    
    if ticket:
        close_ticket(ticket_id, reply_text)
        
        user_message = (
            f"🆘 *Ответ на обращение #{ticket_id}*\n\n"
            f"📝 *Ваш вопрос:*\n{ticket[4]}\n\n"
            f"💬 *Ответ администратора:*\n{reply_text}\n\n"
            f"⏱ Время ответа: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await context.bot.send_message(
            chat_id=ticket[1],
            text=user_message,
            parse_mode='Markdown'
        )
        
        await update.message.reply_text(f"✅ Ответ на тикет {ticket_id} отправлен пользователю")
    else:
        await update.message.reply_text("❌ Тикет не найден")
    
    context.user_data['replying_to_ticket'] = None

# ========== ЛИЧНЫЙ КАБИНЕТ ==========
async def personal_account_menu(query, user_id, context):
    keyboard = [
        [InlineKeyboardButton("🔑 Войти в кабинет", url=PERSONAL_ACCOUNT_URL)],
        [InlineKeyboardButton("👥 Список моих курьеров", callback_data='my_couriers')],
        [InlineKeyboardButton("📝 Записать курьера", callback_data='add_courier')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    
    await edit_and_track(
        query, context,
        "👤 *Личный кабинет*\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_my_couriers(query, user_id, context):
    couriers = get_recruiter_couriers(user_id)
    
    if not couriers:
        text = "📭 *У вас пока нет записанных курьеров*"
    else:
        text = "👥 *Ваши курьеры:*\n\n"
        for i, (name, city, date) in enumerate(couriers, 1):
            date_obj = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
            date_str = date_obj.strftime("%d.%m.%Y")
            text += f"{i}. *{name}* — {city}\n"
            text += f"   📅 {date_str}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("📝 Записать курьера", callback_data='add_courier')],
        [InlineKeyboardButton("🔙 Назад", callback_data='personal_account')]
    ]
    
    await edit_and_track(
        query, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def add_courier_start(query, user_id, context):
    text = (
        "📝 *Запись курьера*\n\n"
        "Введите данные курьера в формате:\n"
        "`Фамилия Имя, Город`\n\n"
        "Например:\n"
        "`Иванов Иван, Москва`"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data='personal_account')]]
    await edit_and_track(
        query, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_courier_data'] = True

async def handle_courier_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    try:
        if ',' not in text:
            await send_and_track(
                update, context,
                "❌ Неверный формат. Используйте: Фамилия Имя, Город\n"
                "Пример: Иванов Иван, Москва"
            )
            return
        
        full_name, city = text.split(',', 1)
        full_name = full_name.strip()
        city = city.strip()
        
        if not full_name or not city:
            await send_and_track(
                update, context,
                "❌ Имя и город не могут быть пустыми"
            )
            return
        
        success, message = add_courier(user_id, full_name, city)
        
        if success:
            await send_and_track(
                update, context,
                f"✅ *Курьер успешно записан!*\n\n"
                f"👤 *Имя:* {full_name}\n"
                f"🏙 *Город:* {city}",
                parse_mode='Markdown'
            )
        else:
            await send_and_track(
                update, context,
                f"❌ {message}"
            )
        
    except Exception as e:
        await send_and_track(
            update, context,
            f"❌ Ошибка: {str(e)}"
        )
    
    context.user_data['awaiting_courier_data'] = False
    
    keyboard = [
        [InlineKeyboardButton("👥 Список курьеров", callback_data='my_couriers')],
        [InlineKeyboardButton("📝 Записать ещё", callback_data='add_courier')],
        [InlineKeyboardButton("🔙 В личный кабинет", callback_data='personal_account')]
    ]
    await send_and_track(
        update, context,
        "👤 *Личный кабинет*\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== ТЕСТИРОВАНИЕ ==========
async def start_test(query, user_id, context):
    can_take, minutes_left = can_take_test(user_id)
    
    if not can_take:
        await edit_and_track(
            query, context,
            f"⏳ *Тест временно недоступен*\n\n"
            f"Вы уже проходили тест недавно. Следующая попытка будет доступна через *{minutes_left} минут*.",
            parse_mode='Markdown'
        )
        return
    
    context.user_data['test_answers'] = []
    context.user_data['test_current'] = 0
    context.user_data['test_questions'] = random.sample(TEST_QUESTIONS, len(TEST_QUESTIONS))
    
    await show_test_question(query, context)

async def show_test_question(query, context):
    current = context.user_data.get('test_current', 0)
    questions = context.user_data.get('test_questions', [])
    
    if current >= len(questions):
        await finish_test(query, context)
        return
    
    question = questions[current]
    
    keyboard = []
    for i, option in enumerate(question['options']):
        keyboard.append([InlineKeyboardButton(option, callback_data=f'answer_{i}')])
    
    keyboard.append([InlineKeyboardButton("❌ Отменить тест", callback_data='back_to_main')])
    
    await edit_and_track(
        query, context,
        f"📝 *Вопрос {current + 1} из {len(questions)}*\n\n"
        f"{question['question']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_test_answer(query, user_id, context):
    try:
        answer_index = int(query.data.replace('answer_', ''))
        current = context.user_data.get('test_current', 0)
        questions = context.user_data.get('test_questions', [])
        answers = context.user_data.get('test_answers', [])
        
        if not questions or current >= len(questions):
            await edit_and_track(
                query, context,
                "❌ Ошибка теста. Начните заново."
            )
            return
        
        question = questions[current]
        correct = question['correct']
        is_correct = (answer_index == correct)
        answers.append(is_correct)
        context.user_data['test_answers'] = answers
        
        if is_correct:
            text = "✅ *Верно!*"
        else:
            correct_text = question['options'][correct]
            text = f"❌ *Неверно!*\nПравильный ответ: *{correct_text}*"
        
        context.user_data['test_current'] = current + 1
        
        if context.user_data['test_current'] >= len(questions):
            await finish_test(query, context)
            return
        
        keyboard = [[InlineKeyboardButton("➡️ Далее", callback_data='next_question')]]
        await edit_and_track(
            query, context,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в handle_test_answer: {e}")
        await edit_and_track(
            query, context,
            "❌ Произошла ошибка. Начните тест заново."
        )

async def next_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        if 'test_current' not in context.user_data or 'test_questions' not in context.user_data:
            keyboard = [[InlineKeyboardButton("📝 Начать тест", callback_data='take_test')]]
            await edit_and_track(
                query, context,
                "❌ Тест не найден. Начните заново.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        await show_test_question(query, context)
        
    except Exception as e:
        logger.error(f"Ошибка в next_question_callback: {e}")
        await edit_and_track(
            query, context,
            "❌ Произошла ошибка. Начните тест заново."
        )

async def finish_test(query, context):
    answers = context.user_data.get('test_answers', [])
    correct_count = sum(1 for a in answers if a)
    user_id = query.from_user.id
    
    if correct_count >= 7:
        update_test_status(user_id, True)
        text = (
            f"🎉 *Тест пройден!*\n\n"
            f"Правильных ответов: *{correct_count} из 10*\n\n"
            f"✅ Вам открыт полный доступ ко всем разделам!"
        )
        keyboard = [[InlineKeyboardButton("🏠 В главное меню", callback_data='back_to_main')]]
    elif correct_count < 3:
        update_test_status(user_id, False)
        text = (
            f"❌ *Тест не пройден*\n\n"
            f"Правильных ответов: *{correct_count} из 10*\n\n"
            f"⏳ Следующая попытка будет доступна через *30 минут*."
        )
        keyboard = [[InlineKeyboardButton("🏠 В главное меню", callback_data='back_to_main')]]
    else:
        update_test_status(user_id, False)
        text = (
            f"⚠️ *Тест не пройден*\n\n"
            f"Правильных ответов: *{correct_count} из 10*\n\n"
            f"📝 Вы можете попробовать снова прямо сейчас."
        )
        keyboard = [[InlineKeyboardButton("📝 Пройти тест заново", callback_data='take_test')]]
    
    context.user_data.pop('test_answers', None)
    context.user_data.pop('test_current', None)
    context.user_data.pop('test_questions', None)
    
    await edit_and_track(
        query, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== МЕНЮ ИНФОРМАЦИИ ==========
async def show_all_info_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("📌 Если курьер нарушает правила", callback_data='info_rules_violation')],
        [InlineKeyboardButton("📢 Маркировка рекламы", callback_data='info_ad_marking')],
        [InlineKeyboardButton("🚨 ВНИМАНИЕ!", callback_data='info_warning')],
        [InlineKeyboardButton("📄 Документы для оформления", callback_data='info_documents')],
        [InlineKeyboardButton("🎯 Целевое действие (ЦД)", callback_data='info_target_action')],
        [InlineKeyboardButton("💰 Когда приходят выплаты?", callback_data='info_payments')],
        [InlineKeyboardButton("💬 Как общаться с кандидатом", callback_data='info_communication')],
        [InlineKeyboardButton("📈 Мотивация и доход курьера", callback_data='info_motivation')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    
    reply_markup = InlineKeyboardMarkup([
        keyboard[0], keyboard[1],
        keyboard[2], keyboard[3],
        keyboard[4], keyboard[5],
        keyboard[6], keyboard[7],
        keyboard[8]
    ])
    
    await edit_and_track(
        query, context,
        "📋 *Вся информация*\n\nВыберите интересующий вас раздел:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_info_section(query, context):
    section = query.data.replace('info_', '')
    
    info_texts = {
        'rules_violation': """
📌 *Если курьер нарушает правила сервиса*

⚠️ *Важно понимать!*

Вы как рекрутер несете полную ответственность за курьеров, которых привлекаете. Если курьер нарушает правила сервиса:

• Профиль рекрутера может быть заблокирован
• Вы лишаетесь доступа ко всем привлеченным курьерам
• Средства могут быть заморожены

*Помните:* вы гарантируете качество работы своих курьеров.
        """,
        'ad_marking': """
📢 *Соблюдайте требования по маркировке рекламы*

✅ *Разрешенные площадки:*
• Авито, hh.ru, Юла, SuperJob, Жердеш.ру, Бирге.ру
• Telegram-каналы о работе
• Группы ВК по трудоустройству

📝 *Как правильно писать:*
НЕЛЬЗЯ: "Яндекс Еда ищет курьеров"
МОЖНО: "Партнер Яндекс Еды ищет курьеров"

❌ *Запрещено:* спам в комментариях и личных сообщениях
        """,
        'warning': """
🚨 *ВНИМАНИЕ!*

*НЕДОПУСТИМО:*

❌ регистрация фейковых аккаунтов
❌ использование чужих данных
❌ вводящая в заблуждение информация о доходах

⚠️ *Фрод = блокировка навсегда!*
        """,
        'documents': """
📄 *Документы для оформления курьера*

🇷🇺 *Граждане РФ:*
• Паспорт с регистрацией
• ИНН
• Медкнижка (если есть)
• Согласие родителей (16+)

🌍 *Граждане ЕАЭС:*
• Паспорт
• ИНН
• СНИЛС (если есть)
• Трудовой договор
        """,
        'target_action': """
🎯 *Целевое действие (ЦД)*

*Что это?* Количество заказов после оформления

📊 *Максимум:* 130 заказов

👤 *Активный курьер:* вышел на первый слот

*Важно:* Минимум 25 заказов для безопасности рекрутера
        """,
        'payments': """
💰 *Когда приходят выплаты?*

Выплаты приходят после выполнения 5 доставленных заказов

📅 *Сроки:* не позднее 10 дней после отчётного периода

⚠️ *Внимание:* Минимум 25 заказов для безопасности рекрутера
        """,
        'communication': """
💬 *Как общаться с кандидатом*

👥 *Учитывайте возраст:*
• Молодым — неформально, на "ты"
• Старшим — деловое общение, на "вы"

📋 *Новичкам:* объясняйте пошагово

💰 *Личная выгода:* 
• Студентам — свободный режим
• Семейным — баланс работы и жизни
        """,
        'motivation': """
📈 *Мотивация и доход курьера*

✅ Фиксированная оплата
✅ Свободный режим
✅ Страхование (доставка + личное время)
✅ Юридическая поддержка (3 консультации/мес)
✅ Доплата за тяжёлые заказы (10-15 кг)
✅ Оплата ожидания (до 20 мин)
✅ Повышенные коэффициенты
✅ Чаевые
✅ Бонусы и спецпредложения

🧮 *Калькулятор дохода* внизу 👇
        """
    }
    
    text = info_texts.get(section, "Информация не найдена")
    
    if section == 'motivation':
        keyboard = [
            [InlineKeyboardButton("🧮 Открыть калькулятор дохода", url=CALCULATOR_URL)],
            [InlineKeyboardButton("🔙 Назад к разделам", callback_data='back_to_info')]
        ]
    else:
        keyboard = [[InlineKeyboardButton("🔙 Назад к разделам", callback_data='back_to_info')]]
    
    await edit_and_track(
        query, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== НАВИГАЦИЯ ==========
async def back_to_main(query, user_id, context):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    test_passed = result[0] if result else 0
    
    if test_passed == 1:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
            [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
            [InlineKeyboardButton("👤 Личный кабинет", callback_data='personal_account')],
            [InlineKeyboardButton("🆘 Обратиться в поддержку", callback_data='support')]
        ]
        menu_text = "🏠 *Главное меню*\n\nВыберите нужный раздел:"
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')]
        ]
        menu_text = "📚 *Для доступа к полному функционалу необходимо пройти тест*\n\nВыберите действие:"
    
    await edit_and_track(
        query, context,
        menu_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if context.user_data.get('awaiting_support_message'):
        await handle_support_message(update, context)
        return
    
    if context.user_data.get('replying_to_ticket'):
        await handle_admin_reply(update, context)
        return
    
    if context.user_data.get('awaiting_courier_data'):
        await handle_courier_input(update, context)
        return
    
    if context.user_data.get('awaiting_withdrawal_details'):
        await handle_withdrawal_input(update, context)
        return
    
    await send_and_track(
        update, context,
        "Используйте команду /start для навигации"
    )

# ========== АДМИН-КОМАНДЫ ==========
async def admin_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await send_and_track(
            update, context,
            "❌ У вас нет прав администратора"
        )
        return
    
    tickets = get_open_tickets()
    
    if not tickets:
        await send_and_track(
            update, context,
            "📭 Нет активных обращений в поддержку"
        )
    else:
        text = "🆘 *Активные обращения в поддержку:*\n\n"
        for ticket in tickets:
            text += f"🆔 *{ticket[0]}*\n"
            text += f"👤 {ticket[3]} (@{ticket[2]})\n"
            text += f"📝 {ticket[4][:100]}...\n"
            text += f"📅 {ticket[5]}\n"
            text += "─" * 20 + "\n"
        
        await send_and_track(update, context, text, parse_mode='Markdown')
    
    withdrawals = get_pending_withdrawals()
    
    if withdrawals:
        text = "💰 *Ожидающие заявки на вывод:*\n\n"
        for w in withdrawals:
            text += f"🆔 *{w[0]}*\n"
            text += f"👤 {w[2]} (@{w[3]})\n"
            text += f"💰 {w[4]} руб.\n"
            text += f"💳 {w[5]}\n"
            text += f"📝 {w[6]}\n"
            text += f"📅 {w[7]}\n"
            text += "─" * 20 + "\n"
        
        await send_and_track(update, context, text, parse_mode='Markdown')
# ========== ТЕСТ GOOGLE SHEETS ==========
async def test_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки Google Sheets"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для админа")
        return
    
    await update.message.reply_text("🔄 Тестирую подключение к Google Sheets...")
    
    try:
        # Проверяем переменные окружения
        creds_json = os.environ.get('GOOGLE_CREDS_JSON')
        sheet_id = os.environ.get('GOOGLE_SHEET_ID')
        
        if not creds_json:
            await update.message.reply_text("❌ GOOGLE_CREDS_JSON не найдена")
            return
        
        if not sheet_id:
            await update.message.reply_text("❌ GOOGLE_SHEET_ID не найдена")
            return
        
        await update.message.reply_text(f"✅ Переменные найдены\nID таблицы: {sheet_id}")
        
        # Пробуем подключиться
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # Парсим JSON
        try:
            creds_dict = json.loads(creds_json)
            await update.message.reply_text("✅ JSON распарсен успешно")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка парсинга JSON: {str(e)}")
            return
        
        # Создаем credentials
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            await update.message.reply_text("✅ Credentials созданы")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка создания credentials: {str(e)}")
            return
        
        # Авторизуемся
        try:
            client = gspread.authorize(creds)
            await update.message.reply_text("✅ Авторизация в Google Sheets успешна")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка авторизации: {str(e)}")
            return
        
        # Открываем таблицу
        try:
            sheet = client.open_by_key(sheet_id).sheet1
            await update.message.reply_text("✅ Таблица открыта успешно")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка открытия таблицы: {str(e)}")
            return
        
        # Пробуем записать тестовые данные
        try:
            test_row = [
                datetime.now().strftime("%d.%m.%Y %H:%M"),
                "ТЕСТ",
                "@test",
                "Тестовый Курьер",
                "Тест-город"
            ]
            sheet.append_row(test_row)
            await update.message.reply_text("✅ Тестовая запись успешно добавлена в таблицу!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка записи в таблицу: {str(e)}")
            return
            
    except Exception as e:
        await update.message.reply_text(f"❌ Общая ошибка: {str(e)}")
# ========== ЗАПУСК ==========
def main():
    init_database()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_requests))
    application.add_handler(CommandHandler("testgoogle", test_google))  # 👈 Добавь эту строку
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CallbackQueryHandler(next_question_callback, pattern='^next_question$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

