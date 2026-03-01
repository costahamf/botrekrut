import json
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import traceback
import random

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
            'Ничего не произойдет',
            'Профиль рекрутера может быть заблокирован',
            'Рекрутер получит предупреждение',
            'Курьер получит бонус'
        ],
        'correct': 1  # Индекс правильного ответа (с 0)
    },
    {
        'question': 'На каких площадках разрешено размещать рекламу?',
        'options': [
            'Только Авито и hh.ru',
            'Авито, hh.ru, Юла, SuperJob, Жердеш.ру, Бирге.ру',
            'Только Telegram-каналы',
            'Везде, где есть люди'
        ],
        'correct': 1
    },
    {
        'question': 'Что НЕДОПУСТИМО при работе с кандидатами?',
        'options': [
            'Регистрация фейковых аккаунтов',
            'Использование чужих данных',
            'Вводящая в заблуждение информация',
            'Всё вышеперечисленное'
        ],
        'correct': 3
    },
    {
        'question': 'Какие документы нужны гражданам РФ для оформления курьером?',
        'options': [
            'Только паспорт',
            'Паспорт и ИНН',
            'Паспорт с регистрацией, ИНН, медкнижка (если есть), согласие родителей (16+)',
            'Только водительские права'
        ],
        'correct': 2
    },
    {
        'question': 'Что такое целевое действие (ЦД)?',
        'options': [
            'Количество заказов курьера после оформления',
            'Первая доставка',
            'Регистрация в приложении',
            'Оплата заказа'
        ],
        'correct': 0
    },
    {
        'question': 'Какой максимальный норматив целевого действия?',
        'options': [
            '50 заказов',
            '100 заказов',
            '130 заказов',
            '200 заказов'
        ],
        'correct': 2
    },
    {
        'question': 'Сколько минимально должен сделать заказов кандидат, чтобы не заблокировали рекрутера?',
        'options': [
            '5 заказов',
            '15 заказов',
            '25 заказов',
            '50 заказов'
        ],
        'correct': 2
    },
    {
        'question': 'Когда приходят выплаты за активного курьера?',
        'options': [
            'Сразу после регистрации',
            'После 5 доставленных заказов',
            'После 10 доставленных заказов',
            'В конце месяца'
        ],
        'correct': 1
    },
    {
        'question': 'Как лучше общаться с кандидатом старшего возраста?',
        'options': [
            'Неформально, на "ты"',
            'Деловое общение, на "вы"',
            'Использовать мемы',
            'Кратко, только по делу'
        ],
        'correct': 1
    },
    {
        'question': 'Что из этого НЕ является мотивацией для курьера?',
        'options': [
            'Фиксированная оплата',
            'Свободный режим',
            'Штрафы за опоздания',
            'Чаевые и бонусы'
        ],
        'correct': 2
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
    
    # Если тест уже пройден - можно проходить заново? (по желанию)
    if test_passed == 1:
        return True, 0
    
    # Проверяем время последней попытки
    if last_attempt_str:
        last_attempt = datetime.strptime(last_attempt_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        time_diff = now - last_attempt
        
        # Если прошло меньше 30 минут - блокировка
        if time_diff < timedelta(minutes=30):
            remaining = 30 - int(time_diff.total_seconds() / 60)
            return False, remaining
    
    return True, 0

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Регистрируем пользователя, если его нет в базе
    if not is_registered(user_id):
        register_user(user_id, user.username, user.first_name, user.last_name)
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            "Вы успешно зарегистрированы в системе."
        )
    
    # Проверяем статус теста
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    test_passed = result[0] if result else 0
    conn.close()
    
    if test_passed == 1:
        # Тест пройден - полное меню
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
            [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
            [InlineKeyboardButton("👤 Личный кабинет", url=PERSONAL_ACCOUNT_URL)],
            [InlineKeyboardButton("🆘 Обратиться в поддержку", callback_data='support')]
        ]
        menu_text = "🏠 *Главное меню*\n\nВыберите нужный раздел:"
    else:
        # Тест не пройден - ограниченное меню
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
    
    # Проверяем статус теста для защищенных разделов
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    test_passed = result[0] if result else 0
    conn.close()
    
    # Если тест не пройден и это защищенный раздел - блокируем
    protected_sections = ['withdrawal', 'support', 'check_balance', 'withdrawal_card', 'withdrawal_yoomoney', 'withdrawal_other']
    if test_passed == 0 and data in protected_sections:
        keyboard = [[InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')]]
        await query.edit_message_text(
            "❌ *Доступ запрещен!*\n\nДля доступа к этому разделу необходимо пройти тест.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # Обработка callback'ов
    if data == 'all_info':
        await show_all_info_menu(query)
    elif data == 'take_test':
        await start_test(query, user_id, context)
    elif data == 'withdrawal':
        await withdrawal_menu(query, user_id)
    elif data == 'support':
        await support_menu(query)
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

# ========== ТЕСТИРОВАНИЕ ==========
async def start_test(query, user_id, context):
    # Проверяем, можно ли проходить тест
    can_take, minutes_left = can_take_test(user_id)
    
    if not can_take:
        await query.edit_message_text(
            f"⏳ *Тест временно недоступен*\n\n"
            f"Вы уже проходили тест недавно. Следующая попытка будет доступна через *{minutes_left} минут*.",
            parse_mode='Markdown'
        )
        return
    
    # Инициализируем тест
    context.user_data['test_answers'] = []
    context.user_data['test_current'] = 0
    context.user_data['test_questions'] = random.sample(TEST_QUESTIONS, len(TEST_QUESTIONS))  # Перемешиваем вопросы
    
    await show_test_question(query, context)

async def show_test_question(query, context):
    current = context.user_data.get('test_current', 0)
    questions = context.user_data.get('test_questions', [])
    
    if current >= len(questions):
        # Тест завершен
        await finish_test(query, context)
        return
    
    question = questions[current]
    
    # Создаем кнопки с вариантами ответов
    keyboard = []
    for i, option in enumerate(question['options']):
        keyboard.append([InlineKeyboardButton(option, callback_data=f'answer_{i}')])
    
    # Добавляем кнопку отмены
    keyboard.append([InlineKeyboardButton("❌ Отменить тест", callback_data='back_to_main')])
    
    await query.edit_message_text(
        f"📝 *Вопрос {current + 1} из {len(questions)}*\n\n"
        f"{question['question']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_test_answer(query, user_id, context):
    answer_index = int(query.data.replace('answer_', ''))
    current = context.user_data.get('test_current', 0)
    questions = context.user_data.get('test_questions', [])
    answers = context.user_data.get('test_answers', [])
    
    # Проверяем правильность ответа
    correct = questions[current]['correct']
    is_correct = (answer_index == correct)
    answers.append(is_correct)
    context.user_data['test_answers'] = answers
    
    # Показываем результат ответа
    if is_correct:
        text = "✅ *Верно!*"
    else:
        correct_text = questions[current]['options'][correct]
        text = f"❌ *Неверно!*\nПравильный ответ: *{correct_text}*"
    
    # Переходим к следующему вопросу
    context.user_data['test_current'] = current + 1
    
    keyboard = [[InlineKeyboardButton("➡️ Далее", callback_data='next_question')]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def next_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_test_question(query, context)

async def finish_test(query, context):
    answers = context.user_data.get('test_answers', [])
    correct_count = sum(1 for a in answers if a)
    user_id = query.from_user.id
    
    # Определяем результат
    if correct_count >= 7:
        # Тест пройден
        update_test_status(user_id, True)
        text = (
            f"🎉 *Тест пройден!*\n\n"
            f"Правильных ответов: *{correct_count} из 10*\n\n"
            f"✅ Вам открыт полный доступ ко всем разделам!"
        )
        keyboard = [[InlineKeyboardButton("🏠 В главное меню", callback_data='back_to_main')]]
    elif correct_count < 3:
        # Полная блокировка на 30 минут
        update_test_status(user_id, False)
        text = (
            f"❌ *Тест не пройден*\n\n"
            f"Правильных ответов: *{correct_count} из 10*\n\n"
            f"⏳ Следующая попытка будет доступна через *30 минут*."
        )
        keyboard = [[InlineKeyboardButton("🏠 В главное меню", callback_data='back_to_main')]]
    else:
        # Можно пересдать сразу
        update_test_status(user_id, False)
        text = (
            f"⚠️ *Тест не пройден*\n\n"
            f"Правильных ответов: *{correct_count} из 10*\n\n"
            f"📝 Вы можете попробовать снова прямо сейчас."
        )
        keyboard = [[InlineKeyboardButton("📝 Пройти тест заново", callback_data='take_test')]]
    
    # Очищаем данные теста
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
        [InlineKeyboardButton("📌 Если курьер нарушает правила сервиса", callback_data='info_rules_violation')],
        [InlineKeyboardButton("📢 Соблюдайте требования по маркировке рекламы", callback_data='info_ad_marking')],
        [InlineKeyboardButton("🚨 ВНИМАНИЕ!", callback_data='info_warning')],
        [InlineKeyboardButton("📄 Документы для оформления курьера", callback_data='info_documents')],
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

*Помните:* вы гарантируете качество работы своих курьеров. Один недобросовестный курьер может поставить под угрозу всё ваше сотрудничество!
        """,
        'ad_marking': """
📢 *Соблюдайте требования по маркировке рекламы*

✅ *Разрешенные площадки для размещения:*

• Авито
• hh.ru
• Юла
• SuperJob
• Жердеш.ру
• Бирге.ру

📱 *Социальные сети и мессенджеры:*
• Telegram-каналы, где люди ищут работу
• Группы ВКонтакте по трудоустройству

📝 *Как правильно писать текст:*
НЕЛЬЗЯ: "Яндекс Еда в поисках курьеров"
МОЖНО: "Партнер Яндекс Еды в поисках курьеров"
        """,
        'warning': """
🚨 *ВНИМАНИЕ!*

*НЕДОПУСТИМО:*

❌ регистрация фейковых аккаунтов
❌ использование чужих данных
❌ распространение вводящей в заблуждение информации о доходах или условиях работы

⚠️ *Если будет выявлен фрод — сотрудничество будет немедленно прекращено без возможности восстановления.*
        """,
        'documents': """
📄 *Документы для оформления курьера*

🇷🇺 *Граждане РФ:*
• Паспорт с регистрацией (или свидетельство о рождении – для партнёров 16+)
• ИНН
• Медицинская книжка (если есть)
• Согласие родителей (для партнёров 16+)

🌍 *Граждане ЕАЭС (Беларусь, Армения, Казахстан, Киргизия):*
• Паспорт с регистрацией
• Миграционная карта (кроме граждан Беларуси)
• ИНН
• СНИЛС (если есть)
• Дактилоскопия (если есть)
• Трудовой договор
        """,
        'target_action': """
🎯 *Целевое действие (ЦД)*

*Что это такое?*
Целевое действие (ЦД) — это количество заказов, которое нужно выполнить курьеру после оформления.

📊 *Норматив:*
Максимум — 130 заказов

👤 *Кто такой активный курьер?*
Активный курьер — курьер, который вышел на первый слот.

*Важно для рекрутера:*
Минимальный порог для качественного кандидата — 25 выполненных заказов.
        """,
        'payments': """
💰 *Когда приходят выплаты?*

*Как начисляются выплаты:*
Выплаты за активного курьера приходят после выполненного целевого действия — 5 доставленных заказов.

📅 *Сроки:*
Сроки выплат зависят от тарифного плана, но не позднее 10 дней после окончания отчётного периода.

⚠️ *ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ:*
Минимальный порог для качественного кандидата — 25 выполненных заказов.
        """,
        'communication': """
💬 *Как общаться с кандидатом*

*Общие рекомендации*

👥 *1. Учитывайте возраст кандидата*
Соблюдайте подходящую дистанцию:

• С молодыми людьми допустим более неформальный стиль, можно использовать мемы или разговорный сленг, переходить на «ты»
• Со старшими кандидатами лучше придерживаться делового общения, обращаться на «вы» и соблюдать вежливый тон

📋 *2. Узнайте об опыте*
Новичков без опыта стоит поддержать — объясните пошагово, что нужно будет делать, развейте сомнения.

💰 *3. Подчёркивайте личную выгоду*
Постарайтесь понять, зачем именно человек ищет работу.
        """,
        'motivation': """
📈 *Мотивация и доход курьера*

*1. Фиксированная оплата*
Даже если на слоте не было заказов, курьер получает минимальную гарантированную выплату.

*2. Свободный режим доставки*
Курьер сам выбирает, когда и сколько работать.

*3. Страхование*
Для курьеров действует две программы страхования:
• во время доставки
• в личное время (например, при болезни или травме)

*8. Чаевые*
Все чаевые от клиентов полностью остаются у курьера.

*9. Бонусы и спецпредложения*
Сервис регулярно предлагает акции и бонусы.

🧮 *Калькулятор дохода*
        """
    }
    
    text = info_texts.get(section, "Информация не найдена")
    
    # Добавляем кнопку калькулятора для раздела мотивации
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

# ========== ПОДДЕРЖКА ==========
async def support_menu(query):
    keyboard = [
        [InlineKeyboardButton("📞 Связаться с поддержкой", url='https://t.me/support')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🆘 *Поддержка*\n\n"
        "Если у вас возникли вопросы, вы можете написать в чат поддержки.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ========== НАВИГАЦИЯ ==========
async def back_to_main(query, user_id):
    # Проверяем статус теста
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
                # Создаем заявку
                request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""INSERT INTO withdrawals 
                           (user_id, amount, payment_method, payment_details, request_date) 
                           VALUES (?, ?, ?, ?, ?)""",
                           (user_id, amount, method, details, request_date))
                conn.commit()
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
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT w.id, w.user_id, u.first_name, u.username, 
                        w.amount, w.payment_method, w.payment_details, w.request_date
                 FROM withdrawals w
                 JOIN users u ON w.user_id = u.user_id
                 WHERE w.status = 'pending'
                 ORDER BY w.request_date DESC""")
    requests = c.fetchall()
    conn.close()
    
    if not requests:
        await update.message.reply_text("📭 Нет активных заявок на вывод")
        return
    
    text = "📋 *Активные заявки на вывод:*\n\n"
    for req in requests:
        text += f"ID: {req[0]}\n"
        text += f"Пользователь: {req[2]} (@{req[3]})\n"
        text += f"Сумма: {req[4]} руб.\n"
        text += f"Способ: {req[5]}\n"
        text += f"Реквизиты: {req[6]}\n"
        text += f"Дата: {req[7]}\n"
        text += "─" * 20 + "\n"
    
    # Разбиваем на части, если сообщение слишком длинное
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000], parse_mode='Markdown')
    else:
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
            
            # Уведомляем пользователя
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
    # Инициализация базы данных
    init_database()
    
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_requests))
    application.add_handler(CommandHandler("confirm", admin_confirm))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Добавляем обработчик для перехода к следующему вопросу
    application.add_handler(CallbackQueryHandler(next_question_callback, pattern='^next_question$'))
    
    # Запуск бота
    logger.info("Бот запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
