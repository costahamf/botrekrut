import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import os

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота (берем из переменных окружения)
TOKEN = os.environ.get('BOT_TOKEN', '8685226609:AAEA8vHoWELRP7_KwXfV9Qbpq1usLUfdJ6o')

# ID администратора
ADMIN_ID = 860845946

# URL для личного кабинета
PERSONAL_ACCOUNT_URL = "https://partners-app.yandex.ru/team_ref/8647844ed8ee4d0eb3d60155113dafb1?locale=ru"

# URL для калькулятора дохода
CALCULATOR_URL = "https://eda.yandex.ru/partner/perf/samara/?utm_medium=cpc&utm_source=yandex-hr&utm_campaign=%5BEDA%5DMX_Courier_RU-ALL-1M_Brand_search_NU%7C73792274&utm_term=49415175552%7C---autotargeting&utm_content=k50id%7C0100000049415175552_49415175552%7Ccid%7C73792274%7Cgid%7C5378729251%7Caid%7C15662855932%7Cadp%7Cno%7Cpos%7Cpremium1%7Csrc%7Csearch_none%7Cdvc%7Cdesktop%7Cmain&etext=2202.H1-umiWOxa1IhaqocPaUS69zT9wHAZdkgZEGqorPY5rJ_ebzkat1FDn2yZO3bEqDYssRPcp0IyJXzD9sTJXJ7293dG14ZXB1Z2VrdW1hemM.0d27564e0c3a01c61971ab0f3d5b481a3ae88ee1&yclid=14506292526793097215"

# Инициализация базы данных
def init_database():
    conn = sqlite3.connect('users.db')
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

# Обработчик callback-запросов
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'all_info':
        await show_all_info_menu(query)
    elif data == 'take_test':
        await take_test(query, user_id)
    elif data == 'withdrawal':
        await withdrawal_menu(query, user_id)
    elif data == 'support':
        await support_menu(query)
    elif data.startswith('info_'):
        await show_info_section(query)
    elif data == 'check_balance':
        await check_balance(query, user_id)
    elif data.startswith('withdrawal_'):
        await process_withdrawal_option(query, user_id, context)
    elif data == 'back_to_main':
        await back_to_main(query)
    elif data == 'back_to_info':
        await show_all_info_menu(query)

# Меню "Вся информация"
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
        [InlineKeyboardButton("🔙 Назад в главное меню", callback_data='back_to_main')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📋 *Вся информация*\n\n"
        "Выберите интересующий вас раздел:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Отображение конкретного раздела информации
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

*Помните:* вы гарантируете качество работы своих курьеров. Регулярно напоминайте им о правилах и требованиях сервиса. Один недобросовестный курьер может поставить под угрозу всё ваше сотрудничество!

Будьте внимательны при отборе кандидатов и контролируйте их работу на начальном этапе.
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

⚠️ *ВАЖНОЕ ПРАВИЛО:*
Запрещен спам в комментариях, личных сообщениях и под постами. Размещайте информацию только в соответствующих разделах и тематических группах.

📝 *Как правильно писать текст:*
НЕЛЬЗЯ: "Яндекс Еда в поисках курьеров"
МОЖНО: "Партнер Яндекс Еды в поисках курьеров"

Соблюдение этих правил защитит вас от блокировки и штрафов!
        """,
        
        'warning': """
🚨 *ВНИМАНИЕ!*

*НЕДОПУСТИМО:*

❌ регистрация фейковых аккаунтов
❌ использование чужих данных
❌ распространение вводящей в заблуждение информации о доходах или условиях работы

⚠️ *Если будет выявлен фрод — сотрудничество будет немедленно прекращено без возможности восстановления.*

Будьте честны с кандидатами и сервисом! Только честная работа гарантирует стабильный доход и долгосрочное сотрудничество.
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

🇺🇦 *Граждане Украины:*
• Паспорт с регистрацией
• Дактилоскопия

🌎 *Граждане других стран:*
• Паспорт с регистрацией
• Миграционная карта
• ИНН (если есть)
• Патент с чеками об оплате / ВНЖ / РВП (по региону работы)
• СНИЛС (если есть)
• Дактилоскопия (если есть)

👤 *Лица без гражданства:*
• Свидетельство о регистрации
• ИНН (если есть)
• СНИЛС (если есть)
• Дактилоскопия (если есть)

🆘 *Важно:* Если есть ВНЖ или РВП — достаточно временного удостоверения личности.

🏳️ *Лица в статусе беженца:*
• Свидетельство о регистрации
• Миграционная карта
• Удостоверение беженца
• ИНН, СНИЛС, дактилоскопия (если есть)

🏠 *Лица с временным убежищем:*
• Свидетельство о регистрации
• Миграционная карта
• Свидетельство о предоставлении временного убежища
• Дактилоскопия
• ИНН, СНИЛС (если есть)
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
Если привлекать кандидатов, которые делают только 5 заказов, это может привести к блокировке. Минимальный порог для качественного кандидата — 25 выполненных заказов.

Стремитесь привлекать мотивированных кандидатов, настроенных на долгосрочную работу!
        """,
        
        'payments': """
💰 *Когда приходят выплаты?*

*Как начисляются выплаты:*
Выплаты за активного курьера приходят после выполненного целевого действия — 5 доставленных заказов.

📅 *Сроки:*
Сроки выплат зависят от тарифного плана, но не позднее 10 дней после окончания отчётного периода.

⚠️ *ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ:*
Если привлекать кандидатов только ради 5 заказов — это приведет к блокировке! Минимальный порог для качественного кандидата — 25 выполненных заказов.

Работайте на качество, а не на количество! Только так вы построите стабильный доход.
        """,
        
        'communication': """
💬 *Как общаться с кандидатом*

Даже при хорошей стратегии привлечения, многое решает то, как вы выстраиваете личное общение. Чтобы человек захотел стать курьером, важно найти к нему подход, адаптировать стиль общения и четко донести преимущества.

*Общие рекомендации*

👥 *1. Учитывайте возраст кандидата*
Соблюдайте подходящую дистанцию:

• С молодыми людьми допустим более неформальный стиль, можно использовать мемы или разговорный сленг, переходить на «ты»
• Со старшими кандидатами лучше придерживаться делового общения, обращаться на «вы» и соблюдать вежливый тон

📋 *2. Узнайте об опыте*
Новичков без опыта стоит поддержать — объясните пошагово, что нужно будет делать, развейте сомнения.

💰 *3. Подчёркивайте личную выгоду*
Постарайтесь понять, зачем именно человек ищет работу:

• Если это студент — акцентируйте свободный режим доставки
• Если нужна стабильность — расскажите про фиксированный доход
• Если важно больше времени проводить с семьёй — покажите, как сотрудничество с Яндекс Едой позволяет сочетать доход и личную жизнь
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

Все расходы покрываются сервисом совместно со страховой компанией.

*4. Юридическая поддержка*
Каждому курьеру доступно до трёх бесплатных юридических консультаций в месяц.

*5. Доплаты за тяжёлые заказы*
Если заказ весит от 10 до 15 кг, пешие и велокурьеры получают дополнительную выплату.

*6. Оплата ожидания*
Если курьер пришёл в ресторан, а заказ ещё не готов — время ожидания (до 20 минут) оплачивается.

*7. Повышенные коэффициенты*
Система анализирует историю доставок и может предложить слоты с повышенным коэффициентом — он увеличивает оплату за каждый заказ.

*8. Чаевые*
Все чаевые от клиентов полностью остаются у курьера.

*9. Бонусы и спецпредложения*
Сервис регулярно предлагает акции и бонусы — за количество заказов, доставки в час пик, в выходные и т.д.

🧮 *Калькулятор дохода*
Кандидат может заранее рассчитать свой потенциальный доход.
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

# Функция для прохождения теста
async def take_test(query, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result and result[0] == 1:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "✅ Вы уже прошли тест!",
            reply_markup=reply_markup
        )
    else:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET test_passed = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "✅ Поздравляем! Вы успешно прошли тест!\n\n"
            "Теперь вам доступен вывод средств.",
            reply_markup=reply_markup
        )

# Меню вывода средств
async def withdrawal_menu(query, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT test_passed, balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or result[0] == 0:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "❌ Для вывода средств необходимо сначала пройти тест!",
            reply_markup=reply_markup
        )
        return
    
    balance = result[1] if result[1] else 0
    
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
        f"Минимальная сумма вывода: *100 руб.*\n"
        f"Комиссия: *5%*\n\n"
        f"Выберите способ вывода:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Обработка выбора способа вывода
async def process_withdrawal_option(query, user_id, context):
    method = query.data.replace('withdrawal_', '')
    context.user_data['withdrawal_method'] = method
    
    keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data='withdrawal')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Выбран способ: *{method}*\n\n"
        f"Введите сумму для вывода и реквизиты в формате:\n"
        f"Сумма|Реквизиты\n\n"
        f"Пример: 500|1234567890123456",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_withdrawal_details'] = True

# Проверка баланса
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

# Меню поддержки
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

# Возврат в главное меню
async def back_to_main(query):
    keyboard = [
        [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
        [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
        [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
        [InlineKeyboardButton("👤 Личный кабинет", url=PERSONAL_ACCOUNT_URL)],
        [InlineKeyboardButton("🆘 Обратиться в поддержку", callback_data='support')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🏠 *Главное меню*\n\n"
        "Выберите нужный раздел:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if context.user_data.get('awaiting_withdrawal_details'):
        try:
            amount, details = text.split('|')
            amount = float(amount.strip())
            details = details.strip()
            method = context.user_data.get('withdrawal_method', 'unknown')
            
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            balance = c.fetchone()[0]
            
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
                
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🔔 *Новая заявка на вывод*\n\n"
                         f"Пользователь: {update.effective_user.first_name} (ID: {user_id})\n"
                         f"Сумма: {amount} руб.\n"
                         f"Способ: {method}\n"
                         f"Реквизиты: {details}",
                    parse_mode='Markdown'
                )
                
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

# Команда для администратора: просмотр заявок
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
    
    await update.message.reply_text(text, parse_mode='Markdown')

# Команда для администратора: подтверждение вывода
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

# Основная функция для запуска
def main():
    init_database()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_requests))
    application.add_handler(CommandHandler("confirm", admin_confirm))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен и готов к работе")
    application.run_polling()

if __name__ == '__main__':
    main()
