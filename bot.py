import json
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import traceback
import random
import uuid

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

# ========== БАЗА ДАННЫХ ==========
def init_database():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
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
                  last_test_attempt TEXT,
                  withdrawal_info TEXT)''')
    
    # Таблица заявок на вывод
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount REAL,
                  payment_method TEXT,
                  payment_details TEXT,
                  status TEXT DEFAULT 'pending',
                  request_date TEXT,
                  FOREIGN KEY (user_id) REFERENCES users (user_id))''')
    
    # ===== НОВАЯ ТАБЛИЦА ДЛЯ ПОДДЕРЖКИ =====
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets
                 (ticket_id TEXT PRIMARY KEY,
                  user_id INTEGER,
                  username TEXT,
                  first_name TEXT,
                  message TEXT,
                  status TEXT DEFAULT 'open',
                  created_at TEXT,
                  answered_at TEXT,
                  admin_reply TEXT,
                  FOREIGN KEY (user_id) REFERENCES users (user_id))''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_db():
    return sqlite3.connect('users.db', check_same_thread=False)

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

def update_test_status(user_id, passed):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET test_passed = ?, last_test_attempt = ? WHERE user_id = ?",
              (1 if passed else 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

def can_take_test(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed, last_test_attempt FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
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

# ========== ФУНКЦИИ ПОДДЕРЖКИ ==========
def create_support_ticket(user_id, username, first_name, message):
    """Создает новый тикет поддержки"""
    conn = get_db()
    c = conn.cursor()
    ticket_id = str(uuid.uuid4())[:8]  # Короткий ID тикета
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('''INSERT INTO support_tickets 
                 (ticket_id, user_id, username, first_name, message, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (ticket_id, user_id, username, first_name, message, created_at))
    
    conn.commit()
    conn.close()
    return ticket_id

def get_open_tickets():
    """Получает все открытые тикеты"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT ticket_id, user_id, username, first_name, message, created_at 
                 FROM support_tickets 
                 WHERE status = 'open' 
                 ORDER BY created_at ASC''')
    tickets = c.fetchall()
    conn.close()
    return tickets

def get_ticket(ticket_id):
    """Получает информацию о тикете"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT * FROM support_tickets WHERE ticket_id = ?''', (ticket_id,))
    ticket = c.fetchone()
    conn.close()
    return ticket

def close_ticket(ticket_id, admin_reply):
    """Закрывает тикет и сохраняет ответ админа"""
    conn = get_db()
    c = conn.cursor()
    answered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''UPDATE support_tickets 
                 SET status = 'closed', answered_at = ?, admin_reply = ? 
                 WHERE ticket_id = ?''',
              (answered_at, admin_reply, ticket_id))
    conn.commit()
    conn.close()

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if not is_registered(user_id):
        register_user(user_id, user.username, user.first_name, user.last_name)
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            "Вы успешно зарегистрированы в системе."
        )
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    test_passed = result[0] if result else 0
    conn.close()
    
    if test_passed == 1:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
            [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
            [InlineKeyboardButton("👤 Личный кабинет", url=PERSONAL_ACCOUNT_URL)],
            [InlineKeyboardButton("🆘 Обратиться в поддержку", callback_data='support')]
        ]
        menu_text = "🏠 *Главное меню*\n\nВыберите нужный раздел:"
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')]
        ]
        menu_text = "📚 *Для доступа к полному функционалу необходимо пройти тест*\n\nВыберите действие:"
    
    await update.message.reply_text(
        menu_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # ===== ОБРАБОТКА АДМИНСКИХ КНОПОК =====
    if data.startswith('admin_reply_'):
        await admin_reply_callback(update, context)
        return
    elif data.startswith('admin_close_'):
        await admin_close_callback(update, context)
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
    conn.close()
    
    protected_sections = ['withdrawal', 'check_balance', 'withdrawal_card', 'withdrawal_yoomoney', 'withdrawal_other']
    if test_passed == 0 and data in protected_sections:
        keyboard = [[InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')]]
        await query.edit_message_text(
            "❌ *Доступ запрещен!*\n\nДля доступа к этому разделу необходимо пройти тест.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # Обработка остальных callback'ов
    if data == 'all_info':
        await show_all_info_menu(query)
    elif data == 'take_test':
        await start_test(query, user_id, context)
    elif data == 'withdrawal':
        await withdrawal_menu(query, user_id)
    elif data == 'support':
        await support_start(query, user_id, context)
    elif data == 'send_support_message':
        await support_request_message(query, context)
    elif data.startswith('info_'):
        await show_info_section(query)
    elif data.startswith('withdrawal_') and data not in ['withdrawal']:
        await process_withdrawal_option(query, user_id, context)
    elif data == 'check_balance':
        await check_balance(query, user_id)
    elif data == 'back_to_main':
        await back_to_main(query, user_id)
    elif data == 'back_to_info':
        await show_all_info_menu(query)
    elif data.startswith('answer_'):
        await handle_test_answer(query, user_id, context)

# ========== ПОДДЕРЖКА ==========
async def support_start(query, user_id, context):
    """Начало обращения в поддержку"""
    text = (
        "🆘 *Поддержка*\n\n"
        "Опишите вашу проблему или вопрос. Я передам сообщение администратору.\n\n"
        "⏱ *Время ответа:* от 15 минут до 1 часа\n\n"
        "Напишите ваш вопрос одним сообщением:"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data='back_to_main')]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_support_message'] = True

async def support_request_message(query, context):
    """Запрос на ввод сообщения (заглушка для callback)"""
    await query.edit_message_text(
        "📝 Напишите ваш вопрос в чат:",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_support_message'] = True

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения в поддержку"""
    user = update.effective_user
    message_text = update.message.text
    
    # Создаем тикет
    ticket_id = create_support_ticket(
        user.id,
        user.username,
        user.first_name,
        message_text
    )
    
    # Отправляем подтверждение пользователю
    await update.message.reply_text(
        f"✅ *Ваше обращение принято!*\n\n"
        f"🆔 Номер обращения: `{ticket_id}`\n"
        f"⏱ Ожидаемое время ответа: от 15 минут до 1 часа\n\n"
        f"Как только администратор ответит, вы получите уведомление.",
        parse_mode='Markdown'
    )
    
    # Отправляем уведомление админу
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
    """Админ отвечает на тикет"""
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
    """Админ закрывает тикет без ответа"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    ticket_id = query.data.replace('admin_close_', '')
    ticket = get_ticket(ticket_id)
    
    if ticket:
        close_ticket(ticket_id, "Тикет закрыт администратором")
        
        # Уведомляем пользователя
        await context.bot.send_message(
            chat_id=ticket[1],  # user_id
            text=f"🆘 *Обращение #{ticket_id} закрыто*\n\nВаш тикет был закрыт администратором.",
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(f"✅ Тикет {ticket_id} закрыт")
    else:
        await query.edit_message_text("❌ Тикет не найден")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа админа на тикет"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    ticket_id = context.user_data.get('replying_to_ticket')
    if not ticket_id:
        return
    
    reply_text = update.message.text
    ticket = get_ticket(ticket_id)
    
    if ticket:
        # Закрываем тикет с ответом
        close_ticket(ticket_id, reply_text)
        
        # Отправляем ответ пользователю
        user_message = (
            f"🆘 *Ответ на обращение #{ticket_id}*\n\n"
            f"📝 *Ваш вопрос:*\n{ticket[4]}\n\n"
            f"💬 *Ответ администратора:*\n{reply_text}\n\n"
            f"⏱ Время ответа: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await context.bot.send_message(
            chat_id=ticket[1],  # user_id
            text=user_message,
            parse_mode='Markdown'
        )
        
        # Подтверждение админу
        await update.message.reply_text(f"✅ Ответ на тикет {ticket_id} отправлен пользователю")
        
        # Обновляем сообщение с тикетом в чате админа
        keyboard = [
            [InlineKeyboardButton("✅ Уже ответил", callback_data=f'admin_done_{ticket_id}')]
        ]
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ Ответ на тикет {ticket_id} отправлен",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("❌ Тикет не найден")
    
    context.user_data['replying_to_ticket'] = None

# ========== ТЕСТИРОВАНИЕ ==========
async def start_test(query, user_id, context):
    can_take, minutes_left = can_take_test(user_id)
    
    if not can_take:
        await query.edit_message_text(
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
    
    await query.edit_message_text(
        f"📝 *Вопрос {current + 1} из {len(questions)}*\n\n"
        f"{question['question']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_test_answer(query, user_id, context):
    """Обработка ответа на вопрос теста"""
    try:
        answer_index = int(query.data.replace('answer_', ''))
        current = context.user_data.get('test_current', 0)
        questions = context.user_data.get('test_questions', [])
        answers = context.user_data.get('test_answers', [])
        
        # Проверяем, что вопросы существуют
        if not questions or current >= len(questions):
            await query.edit_message_text("❌ Ошибка теста. Начните заново.")
            return
        
        # Получаем текущий вопрос
        question = questions[current]
        correct = question['correct']
        is_correct = (answer_index == correct)
        answers.append(is_correct)
        context.user_data['test_answers'] = answers
        
        # Формируем текст ответа
        if is_correct:
            text = "✅ *Верно!*"
        else:
            correct_text = question['options'][correct]
            text = f"❌ *Неверно!*\nПравильный ответ: *{correct_text}*"
        
        # Переходим к следующему вопросу
        context.user_data['test_current'] = current + 1
        
        # Проверяем, не закончился ли тест
        if context.user_data['test_current'] >= len(questions):
            # Тест завершен
            await finish_test(query, context)
            return
        
        # Показываем результат и кнопку "Далее"
        keyboard = [[InlineKeyboardButton("➡️ Далее", callback_data='next_question')]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в handle_test_answer: {e}")
        await query.edit_message_text("❌ Произошла ошибка. Начните тест заново.")

async def next_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для кнопки 'Далее'"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Проверяем, есть ли активный тест
        if 'test_current' not in context.user_data or 'test_questions' not in context.user_data:
            await query.edit_message_text(
                "❌ Тест не найден. Начните заново.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📝 Начать тест", callback_data='take_test')
                ]])
            )
            return
        
        # Показываем следующий вопрос
        await show_test_question(query, context)
        
    except Exception as e:
        logger.error(f"Ошибка в next_question_callback: {e}")
        await query.edit_message_text("❌ Произошла ошибка. Начните тест заново.")
        
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
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== МЕНЮ ИНФОРМАЦИИ ==========
async def show_all_info_menu(query):
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
    
    await query.edit_message_text(
        "📋 *Вся информация*\n\n"
        "Выберите интересующий вас раздел:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_info_section(query):
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
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ========== ВЫВОД СРЕДСТВ ==========
async def withdrawal_menu(query, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    balance = result[0] if result else 0
    
    keyboard = [
        [InlineKeyboardButton("💰 Проверить баланс", callback_data='check_balance')],
        [InlineKeyboardButton("💳 Карта", callback_data='withdrawal_card')],
        [InlineKeyboardButton("📱 ЮMoney", callback_data='withdrawal_yoomoney')],
        [InlineKeyboardButton("🔄 Другой способ", callback_data='withdrawal_other')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💸 *Вывод средств*\n\n"
        f"Ваш баланс: *{balance} руб.*\n"
        f"Минимальная сумма вывода: *100 руб.*\n\n"
        f"Выберите способ вывода:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def process_withdrawal_option(query, user_id, context):
    method = query.data.replace('withdrawal_', '')
    context.user_data['withdrawal_method'] = method
    
    keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data='withdrawal')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Выбран способ: *{method}*\n\n"
        f"Введите сумму и реквизиты в формате:\n"
        f"Сумма|Реквизиты\n\n"
        f"Пример: 500|1234567890123456",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_withdrawal_details'] = True

async def check_balance(query, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    balance = result[0] if result else 0
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='withdrawal')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💰 *Ваш баланс*\n\n"
        f"Текущий баланс: *{balance} руб.*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ========== НАВИГАЦИЯ ==========
async def back_to_main(query, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    test_passed = result[0] if result else 0
    conn.close()
    
    if test_passed == 1:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
            [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
            [InlineKeyboardButton("👤 Личный кабинет", url=PERSONAL_ACCOUNT_URL)],
            [InlineKeyboardButton("🆘 Обратиться в поддержку", callback_data='support')]
        ]
        menu_text = "🏠 *Главное меню*\n\nВыберите нужный раздел:"
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')]
        ]
        menu_text = "📚 *Для доступа к полному функционалу необходимо пройти тест*\n\nВыберите действие:"
    
    await query.edit_message_text(
        menu_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем, ожидаем ли мы сообщение для поддержки
    if context.user_data.get('awaiting_support_message'):
        await handle_support_message(update, context)
        return
    
    # Проверяем, ожидаем ли мы ответ от админа на тикет
    if context.user_data.get('replying_to_ticket'):
        await handle_admin_reply(update, context)
        return
    
    # Проверяем, ожидаем ли мы ввод для вывода средств
    if context.user_data.get('awaiting_withdrawal_details'):
        try:
            text = update.message.text
            amount, details = text.split('|')
            amount = float(amount.strip())
            details = details.strip()
            method = context.user_data.get('withdrawal_method', 'unknown')
            
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            balance_row = c.fetchone()
            balance = balance_row[0] if balance_row else 0
            
            if amount < 100:
                await update.message.reply_text("❌ Минимальная сумма вывода: 100 руб.")
            elif amount > balance:
                await update.message.reply_text("❌ Недостаточно средств на балансе")
            else:
                request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""INSERT INTO withdrawals 
                           (user_id, amount, payment_method, payment_details, request_date) 
                           VALUES (?, ?, ?, ?, ?)""",
                           (user_id, amount, method, details, request_date))
                conn.commit()
                
                # Уведомляем админа
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💰 *Новая заявка на вывод*\n\n"
                         f"Пользователь: {update.effective_user.first_name} (ID: {user_id})\n"
                         f"Сумма: {amount} руб.\n"
                         f"Способ: {method}\n"
                         f"Реквизиты: {details}",
                    parse_mode='Markdown'
                )
                
                await update.message.reply_text(
                    "✅ Заявка на вывод создана!\n"
                    "Ожидайте обработки администратором."
                )
            
            conn.close()
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Сумма|Реквизиты\n"
                "Пример: 500|1234567890123456"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        
        context.user_data['awaiting_withdrawal_details'] = False
    else:
        await update.message.reply_text("Используйте команду /start для навигации")

# ========== АДМИН-КОМАНДЫ ==========
async def admin_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return
    
    # Показываем открытые тикеты
    tickets = get_open_tickets()
    
    if not tickets:
        await update.message.reply_text("📭 Нет активных обращений в поддержку")
        return
    
    text = "🆘 *Активные обращения в поддержку:*\n\n"
    for ticket in tickets:
        text += f"🆔 *{ticket[0]}*\n"
        text += f"👤 {ticket[3]} (@{ticket[2]})\n"
        text += f"📝 {ticket[4][:100]}...\n"
        text += f"📅 {ticket[5]}\n"
        text += "─" * 20 + "\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return
    
    try:
        request_id = int(context.args[0])
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ? AND status = 'pending'", (request_id,))
        request = c.fetchone()
        
        if request:
            user_id, amount = request
            
            c.execute("UPDATE withdrawals SET status = 'completed' WHERE id = ?", (request_id,))
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            
            conn.commit()
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Ваша заявка на вывод {amount} руб. подтверждена и обработана!"
            )
            
            await update.message.reply_text(f"✅ Заявка {request_id} подтверждена")
        else:
            await update.message.reply_text("❌ Заявка не найдена или уже обработана")
        
        conn.close()
        
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /confirm <ID заявки>")

# ========== ЗАПУСК ==========
def main():
    init_database()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_requests))
    application.add_handler(CommandHandler("confirm", admin_confirm))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CallbackQueryHandler(next_question_callback, pattern='^next_question$'))
    application.add_handler(CallbackQueryHandler(admin_reply_callback, pattern='^admin_reply_'))
    application.add_handler(CallbackQueryHandler(admin_close_callback, pattern='^admin_close_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()



