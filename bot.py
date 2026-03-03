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
import time

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
import json
import os
import threading
import atexit
import time

DB_CONN = None
BACKUP_FILE = 'backup.json'

def get_db():
    """Возвращает соединение с БД (ФАЙЛ, а не память!)"""
    global DB_CONN
    try:
        if DB_CONN is None:
            # ВАЖНО: используем ФАЙЛ, а не :memory:
            DB_CONN = sqlite3.connect('bot_database.db', check_same_thread=False)
            init_database_tables(DB_CONN)
            load_backup()  # загружаем бэкап если есть
        return DB_CONN
    except Exception as e:
        logger.error(f"❌ Ошибка в get_db: {e}")
        DB_CONN = sqlite3.connect('bot_database.db', check_same_thread=False)
        init_database_tables(DB_CONN)
        load_backup()
        return DB_CONN

def init_database_tables(conn):
    """Создает таблицы в переданном соединении"""
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
                  last_test_attempt TEXT)''')
    
    # Таблица заявок на вывод
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount REAL,
                  payment_method TEXT,
                  payment_details TEXT,
                  status TEXT DEFAULT 'pending',
                  request_date TEXT,
                  completed_date TEXT)''')
    
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
                  status TEXT DEFAULT 'pending',
                  balance REAL DEFAULT 0,
                  registered_at TEXT,
                  confirmed_at TEXT,
                  sheet_row INTEGER)''')
    
    conn.commit()
    logger.info("✅ Таблицы созданы в памяти")

def backup_database():
    """Сохраняет все данные в JSON файл"""
    conn = None
    try:
        # ВАЖНО: создаем НОВОЕ соединение, а не используем глобальное
        conn = sqlite3.connect(':memory:')
        
        # Копируем данные из глобальной БД, если она существует и не закрыта
        if DB_CONN is not None:
            try:
                # Проверяем, открыто ли соединение
                DB_CONN.cursor().execute("SELECT 1").fetchone()
                DB_CONN.backup(conn)
            except:
                logger.warning("⚠️ Глобальное соединение с БД закрыто, создаем новую БД для бэкапа")
                # Если не получается скопировать, создаем новую БД с таблицами
                init_database_tables(conn)
        else:
            init_database_tables(conn)
        
        c = conn.cursor()
        
        # Собираем все данные
        backup = {
            'users': c.execute("SELECT * FROM users").fetchall(),
            'withdrawals': c.execute("SELECT * FROM withdrawals").fetchall(),
            'support_tickets': c.execute("SELECT * FROM support_tickets").fetchall(),
            'couriers': c.execute("SELECT * FROM couriers").fetchall(),
            'timestamp': datetime.now().isoformat()
        }
        
        # Сохраняем в файл
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            json.dump(backup, f, default=str, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Автосохранение: {len(backup['users'])} users, {len(backup['couriers'])} couriers")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения бэкапа: {e}")
        return False
                
def load_backup():
    """Загружает данные из JSON файла"""
    try:
        if not os.path.exists(BACKUP_FILE):
            logger.info("📭 Файл бэкапа не найден, начинаем с пустой БД")
            return
        
        with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
            backup = json.load(f)
        
        conn = get_db()
        c = conn.cursor()
        
        # Загружаем пользователей
        for row in backup.get('users', []):
            placeholders = ','.join(['?'] * len(row))
            c.execute(f"INSERT OR REPLACE INTO users VALUES ({placeholders})", row)
        
        # Загружаем заявки на вывод
        for row in backup.get('withdrawals', []):
            placeholders = ','.join(['?'] * len(row))
            c.execute(f"INSERT OR REPLACE INTO withdrawals VALUES ({placeholders})", row)
        
        # Загружаем тикеты
        for row in backup.get('support_tickets', []):
            placeholders = ','.join(['?'] * len(row))
            c.execute(f"INSERT OR REPLACE INTO support_tickets VALUES ({placeholders})", row)
        
        # Загружаем курьеров
        for row in backup.get('couriers', []):
            placeholders = ','.join(['?'] * len(row))
            c.execute(f"INSERT OR REPLACE INTO couriers VALUES ({placeholders})", row)
        
        conn.commit()
        logger.info(f"✅ Загружено из бэкапа: {len(backup.get('users', []))} users, {len(backup.get('couriers', []))} couriers")
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки бэкапа: {e}")

def start_auto_backup():
    """Запускает автосохранение каждые 5 минут"""
    def backup_worker():
        while True:
            time.sleep(300)  # 5 минут
            backup_database()
    
    thread = threading.Thread(target=backup_worker, daemon=True)
    thread.start()
    logger.info("✅ Автосохранение запущено (каждые 5 минут)")

# Сохраняем при выходе
atexit.register(backup_database)
def init_database():
    """Инициализирует БД"""
    get_db()  # Создаем таблицы
    load_from_google_sheets()  # Загружаем курьеров из Google Sheets
    logger.info("✅ База данных инициализирована")
    
# ========== GOOGLE SHEETS ИНТЕГРАЦИЯ ==========
def get_google_sheet():
    """Подключается к Google Sheets и возвращает рабочий лист"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 
                 'https://www.googleapis.com/auth/drive',
                 'https://www.googleapis.com/auth/spreadsheets']
        
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
            return None, None
        
        # Добавляем строку с данными (теперь есть колонка для баланса)
        row = [
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            recruiter_name,
            f"@{recruiter_username}" if recruiter_username else "-",
            full_name,
            city,
            "⏳ Ожидает",  # Статус
            0,  # Баланс курьера (ты будешь заполнять)
            0,  # 0 = не принято, 1 = принято
            0   # 0 = не отклонено, 1 = отклонено
        ]
        sheet.append_row(row, value_input_option='USER_ENTERED')
        
        # Получаем номер добавленной строки
        time.sleep(2)
        all_records = sheet.get_all_records()
        row_number = len(all_records) + 1
        
        logger.info(f"✅ Курьер {full_name} добавлен в Google Sheets (строка {row_number})")
        return True, row_number
    except Exception as e:
        logger.error(f"Ошибка добавления в Google Sheets: {e}")
        return None, None
def update_courier_status_in_sheet(sheet_row, status_text):
    """Обновляет статус в Google Sheets"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            logger.error("❌ Не удалось подключиться к Google Sheets для обновления статуса")
            return False
        
        # Обновляем статус в колонке СТАТУС (колонка F, т.к. A=1, B=2, C=3, D=4, E=5, F=6)
        sheet.update_cell(sheet_row, 6, status_text)  # 6 = колонка F (СТАТУС)
        logger.info(f"✅ Обновлен статус в Google Sheets: строка {sheet_row}, статус {status_text}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления статуса в Google Sheets: {e}")
        return False
def check_pending_couriers():
    """Проверяет статусы курьеров в Google Sheets и синхронизирует с БД в обе стороны"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            logger.warning("⚠️ Не удалось подключиться к Google Sheets для проверки статусов")
            return
        
        records = sheet.get_all_records()
        logger.info(f"🔍 Проверяем {len(records)} записей в Google Sheets")
        
        conn = get_db()
        c = conn.cursor()
        
        updated_count = 0          # сколько обновлено в БД
        new_count = 0               # сколько добавлено в БД
        balance_updated_count = 0   # сколько обновлено балансов
        sheet_updated_count = 0     # сколько обновлено в таблице
        
        for i, record in enumerate(records):
            try:
                # ========== ПОЛУЧАЕМ ДАННЫЕ ИЗ ТАБЛИЦЫ ==========
                full_name = record.get('ФИО клиента', '').strip()
                city = record.get('Город', '').strip()
                status_text = record.get('СТАТУС', '').strip()
                
                # ПОЛУЧАЕМ БАЛАНС (может быть в колонке Время или Баланс)
                balance_raw = record.get('Время', '0') or record.get('Баланс', '0')
                
                # ПРИНЯТО и ОТКЛОНЕНО
                accepted_raw = record.get('ПРИНЯТО', '0')
                rejected_raw = record.get('ОТКЛОНЕНО', '0')
                
                # Преобразуем в строку и чистим
                accepted = str(accepted_raw).strip()
                rejected = str(rejected_raw).strip()
                
                # Преобразуем баланс в число
                try:
                    balance = float(str(balance_raw).replace(',', '.').replace(' ', ''))
                except:
                    balance = 0.0
                
                sheet_row = i + 2  # номер строки в таблице
                
                # Пропускаем пустые строки
                if not full_name or not city:
                    continue
                
                # ========== ОПРЕДЕЛЯЕМ СТАТУС ==========
                new_status = None
                new_status_text = None
                
                if accepted in ['1', 'true', 'True', 'TRUE', 'yes', 'Yes', 'YES', '✅', '☑']:
                    new_status = 'confirmed'
                    new_status_text = "✅ Подтвержден"
                    logger.info(f"✅ Курьер {full_name} ПОДТВЕРЖДЕН (ПРИНЯТО={accepted_raw})")
                
                elif rejected in ['1', 'true', 'True', 'TRUE', 'yes', 'Yes', 'YES', '❌']:
                    new_status = 'rejected'
                    new_status_text = "❌ Отклонен"
                    logger.info(f"❌ Курьер {full_name} ОТКЛОНЕН (ОТКЛОНЕНО={rejected_raw})")
                
                else:
                    if 'Подтвержден' in status_text or '✅' in status_text or '☑' in status_text:
                        new_status = 'confirmed'
                    elif 'Отклонен' in status_text or '❌' in status_text:
                        new_status = 'rejected'
                    else:
                        new_status = 'pending'
                        new_status_text = "⏳ Ожидает"
                
                # ========== ПРОВЕРЯЕМ, ЕСТЬ ЛИ КУРЬЕР В БД ==========
                c.execute('''SELECT id, status, sheet_row, balance, recruiter_id FROM couriers 
                             WHERE full_name = ? AND city = ? ORDER BY id DESC LIMIT 1''',
                          (full_name, city))
                existing = c.fetchone()
                
                if existing:
                    # КУРЬЕР УЖЕ ЕСТЬ В БД
                    existing_id, existing_status, existing_sheet_row, existing_balance, recruiter_id = existing
                    
                    # ===== ОБНОВЛЕНИЕ СТАТУСА =====
                    if existing_status != new_status:
                        c.execute('''UPDATE couriers 
                                     SET status = ?, confirmed_at = ? 
                                     WHERE id = ?''',
                                  (new_status, 
                                   datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status == 'confirmed' else None,
                                   existing_id))
                        updated_count += 1
                        logger.info(f"🔄 Обновлен статус в БД: {full_name}: {existing_status} -> {new_status}")
                        
                        if new_status_text and existing_sheet_row:
                            update_courier_status_in_sheet(existing_sheet_row, new_status_text)
                            sheet_updated_count += 1
                    
                    # ===== ОБНОВЛЕНИЕ БАЛАНСА КУРЬЕРА =====
                    if existing_balance != balance:
                        c.execute("UPDATE couriers SET balance = ? WHERE id = ?", (balance, existing_id))
                        balance_updated_count += 1
                        logger.info(f"💰 Обновлен баланс курьера {full_name}: {existing_balance} -> {balance}")
                        
                        # ========== ОБНОВЛЯЕМ ОБЩИЙ БАЛАНС РЕКРУТЕРА ==========
                        if recruiter_id:
                            c.execute("SELECT SUM(balance) FROM couriers WHERE recruiter_id = ?", (recruiter_id,))
                            total_balance = c.fetchone()[0] or 0
                            
                            c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (total_balance, recruiter_id))
                            logger.info(f"👤 Обновлен общий баланс рекрутера {recruiter_id}: {total_balance}")
                        # =====================================================
                    
                    # Проверяем, нужно ли обновить номер строки в БД
                    if existing_sheet_row != sheet_row:
                        c.execute("UPDATE couriers SET sheet_row = ? WHERE id = ?", (sheet_row, existing_id))
                        logger.info(f"📝 Обновлен номер строки для {full_name}: {existing_sheet_row} -> {sheet_row}")
                
                else:
                    # НОВЫЙ КУРЬЕР (не можем обновить баланс рекрутера, т.к. не знаем recruiter_id)
                    registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO couriers 
                                 (full_name, city, status, balance, registered_at, sheet_row) 
                                 VALUES (?, ?, ?, ?, ?, ?)''',
                              (full_name, city, new_status, balance, registered_at, sheet_row))
                    new_count += 1
                    logger.info(f"✅ Добавлен новый курьер в БД: {full_name} (статус: {new_status}, баланс: {balance})")
                    
                    if new_status_text:
                        update_courier_status_in_sheet(sheet_row, new_status_text)
                        sheet_updated_count += 1
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке строки {i+2}: {e}")
                logger.error(f"   Данные строки: {record}")
                continue
        
        conn.commit()
        
        # ========== ЛОГИРУЕМ РЕЗУЛЬТАТЫ ==========
        if updated_count > 0 or new_count > 0 or balance_updated_count > 0 or sheet_updated_count > 0:
            logger.info(f"📊 ИТОГИ СИНХРОНИЗАЦИИ:")
            logger.info(f"   • Обновлено статусов в БД: {updated_count}")
            logger.info(f"   • Обновлено балансов в БД: {balance_updated_count}")
            logger.info(f"   • Добавлено новых курьеров: {new_count}")
            logger.info(f"   • Обновлено в таблице: {sheet_updated_count}")
        else:
            logger.info("📊 Синхронизация завершена - изменений нет")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА В check_pending_couriers: {e}")
        import traceback
        traceback.print_exc()
def load_from_google_sheets():
    """Загружает курьеров из Google Sheets в БД при старте"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            logger.warning("⚠️ Не удалось подключиться к Google Sheets для загрузки")
            return
        
        records = sheet.get_all_records()
        logger.info(f"📥 Загружаем {len(records)} курьеров из Google Sheets")
        
        conn = get_db()
        c = conn.cursor()
        
        for i, record in enumerate(records):
            try:
                # ========== ПОЛУЧАЕМ ДАННЫЕ ИЗ ТАБЛИЦЫ ==========
                full_name = record.get('ФИО клиента') or ''
                city = record.get('Город') or ''
                status_text = record.get('СТАТУС') or ''
                accepted = record.get('ПРИНЯТО') or '0'
                rejected = record.get('ОТКЛОНЕНО') or '0'
                
                # ========== ЛОГИРОВАНИЕ БАЛАНСА ==========
                balance_raw = record.get('Баланс', '0')
                logger.info(f"📊 Строка {i+2}: {full_name}")
                logger.info(f"   Баланс raw: '{balance_raw}'")
                
                # Преобразуем баланс в число
                try:
                    # Убираем пробелы, заменяем запятую на точку
                    balance_str = str(balance_raw).strip().replace(' ', '').replace(',', '.')
                    if balance_str and balance_str != '0':
                        balance = float(balance_str)
                        logger.info(f"   ✅ Баланс после преобразования: {balance}")
                    else:
                        balance = 0.0
                        logger.info(f"   ℹ️ Баланс пустой или 0")
                except Exception as e:
                    balance = 0.0
                    logger.warning(f"   ⚠️ Ошибка преобразования баланса '{balance_raw}': {e}")
                # =============================================
                
                # Пропускаем пустые строки
                if not full_name or not city:
                    logger.warning(f"⚠️ Строка {i+2} пропущена: нет имени или города")
                    continue
                
                # Определяем статус
                status = 'pending'
                if str(accepted).strip() == '1':
                    status = 'confirmed'
                elif str(rejected).strip() == '1':
                    status = 'rejected'
                elif 'Подтвержден' in status_text or '✅' in status_text:
                    status = 'confirmed'
                
                # ========== ИЩЕМ RECRUITER_ID по username из таблицы ==========
                recruiter_username = record.get('Username рекрутера', '').replace('@', '').strip()
                recruiter_id = None
                
                if recruiter_username:
                    c.execute("SELECT user_id FROM users WHERE username = ?", (recruiter_username,))
                    user = c.fetchone()
                    if user:
                        recruiter_id = user[0]
                        logger.info(f"   👤 Найден рекрутер @{recruiter_username} с ID {recruiter_id}")
                    else:
                        logger.warning(f"   ⚠️ Рекрутер @{recruiter_username} не найден в БД")
                else:
                    logger.warning(f"   ⚠️ В строке {i+2} нет username рекрутера")
                # ============================================================
                
                # Вставляем или обновляем запись С recruiter_id и балансом
                if recruiter_id:
                    # Проверяем, есть ли уже такой курьер
                    c.execute('''SELECT id FROM couriers 
                                 WHERE full_name = ? AND city = ?''', (full_name, city))
                    existing = c.fetchone()
                    
                    if existing:
                        # Обновляем существующего курьера
                        c.execute('''
                            UPDATE couriers 
                            SET status = ?, balance = ?, sheet_row = ?, recruiter_id = ?
                            WHERE id = ?
                        ''', (status, balance, i + 2, recruiter_id, existing[0]))
                        logger.info(f"🔄 Обновлен курьер {full_name}, баланс: {balance}")
                    else:
                        # Вставляем нового курьера
                        c.execute('''
                            INSERT INTO couriers 
                            (recruiter_id, full_name, city, status, balance, registered_at, sheet_row) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (recruiter_id, full_name, city, status, balance, 
                              datetime.now().strftime("%Y-%m-%d %H:%M:%S"), i + 2))
                        logger.info(f"✅ Добавлен новый курьер {full_name}, баланс: {balance}")
                else:
                    logger.warning(f"⚠️ Курьер {full_name} пропущен - рекрутер не найден")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке строки {i+2}: {e}")
                logger.error(f"   Данные строки: {record}")
                continue
        
        conn.commit()
        
        # ========== ПРОВЕРЯЕМ, ЧТО ЗАГРУЗИЛОСЬ ==========
        c.execute("SELECT COUNT(*) FROM couriers")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM couriers WHERE balance > 0")
        with_balance = c.fetchone()[0]
        logger.info(f"📊 ИТОГ ЗАГРУЗКИ: всего {total} курьеров, из них {with_balance} с балансом > 0")
        # ================================================
        
        logger.info(f"✅ Загружено {len(records)} курьеров из Google Sheets")
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки из Google Sheets: {e}")
        import traceback
        traceback.print_exc()
def start_sheet_monitoring():
    """Запускает мониторинг Google Sheets в фоне"""
    def monitor_worker():
        while True:
            try:
                check_pending_couriers()
                time.sleep(300)  # Проверяем каждые 5 минут вместо 1 минуты
            except Exception as e:
                logger.error(f"Ошибка в мониторинге: {e}")
                time.sleep(300)
    
    thread = threading.Thread(target=monitor_worker, daemon=True)
    thread.start()
    logger.info("✅ Мониторинг Google Sheets запущен (интервал 5 минут)")


# ========== ФУНКЦИИ ПРОВЕРКИ ПОЛЬЗОВАТЕЛЕЙ ==========
def is_registered(user_id):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        if result:
            logger.info(f"✅ Пользователь {user_id} найден в БД")
            return True
        else:
            logger.info(f"❌ Пользователь {user_id} НЕ найден в БД")
            return False
    except Exception as e:
        logger.error(f"Ошибка в is_registered: {e}")
        return False
                
def register_user(user_id, username, first_name, last_name):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        registration_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registration_date, balance) VALUES (?, ?, ?, ?, ?, 0)",
                  (user_id, username, first_name, last_name, registration_date))
        conn.commit()
        logger.info(f"✅ Пользователь {user_id} зарегистрирован")
    except Exception as e:
        logger.error(f"Ошибка в register_user: {e}")

# ========== СЮДА ВСТАВЬ НОВУЮ ФУНКЦИЮ ==========
def update_test_status(user_id, passed):
    """Обновляет статус теста пользователя"""
    conn = None
    try:
        conn = get_db()
        if conn is None:
            logger.error("❌ Не удалось получить соединение с БД в update_test_status")
            return
            
        c = conn.cursor()
        
        # Проверяем, есть ли пользователь
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            # Если пользователя нет - НЕ СОЗДАЕМ ФЕЙКОВОГО!
            # Просто логируем и выходим
            logger.warning(f"⚠️ Пользователь {user_id} не найден в БД")
            return
        
        # Обновляем статус
        logger.info(f"📝 Обновление test_passed для user_id={user_id} на {1 if passed else 0}")
        c.execute("UPDATE users SET test_passed = ?, last_test_attempt = ? WHERE user_id = ?",
                  (1 if passed else 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
        conn.commit()
        
        # Проверяем, что обновилось
        c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
        new_value = c.fetchone()
        
        if new_value:
            logger.info(f"   ✅ После обновления test_passed={new_value[0]}")
            if passed and new_value[0] == 1:
                logger.info(f"   🎉 ПОЛЬЗОВАТЕЛЬ {user_id} УСПЕШНО СДАЛ ТЕСТ!")
        else:
            logger.error(f"   ❌ Не удалось прочитать обновленное значение")
            
    except Exception as e:
        logger.error(f"Ошибка в update_test_status: {e}")
        import traceback
        traceback.print_exc()

# ========== КОНЕЦ НОВОЙ ФУНКЦИИ ==========

def can_take_test(user_id):
    conn = None
    try:
        conn = get_db()
        if conn is None:
            return True, 0
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
    except Exception as e:
        logger.error(f"Ошибка в can_take_test: {e}")
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
    conn = get_db()
    c = conn.cursor()
    try:
        ticket_id = str(uuid.uuid4())[:8]
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''INSERT INTO support_tickets 
                     (ticket_id, user_id, username, first_name, message, created_at) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (ticket_id, user_id, username, first_name, message, created_at))
        conn.commit()
        return ticket_id
    except Exception as e:
        logger.error(f"Ошибка в create_support_ticket: {e}")
        return None

def get_open_tickets():
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''SELECT ticket_id, user_id, username, first_name, message, created_at 
                     FROM support_tickets 
                     WHERE status = 'open' 
                     ORDER BY created_at ASC''')
        return c.fetchall()
    except Exception as e:
        logger.error(f"Ошибка в get_open_tickets: {e}")
        return []

def get_ticket(ticket_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''SELECT * FROM support_tickets WHERE ticket_id = ?''', (ticket_id,))
        return c.fetchone()
    except Exception as e:
        logger.error(f"Ошибка в get_ticket: {e}")
        return None

def close_ticket(ticket_id, admin_reply):
    conn = get_db()
    c = conn.cursor()
    try:
        answered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''UPDATE support_tickets 
                     SET status = 'closed', answered_at = ?, admin_reply = ? 
                     WHERE ticket_id = ?''',
                  (answered_at, admin_reply, ticket_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка в close_ticket: {e}")

# ========== ФУНКЦИИ ДЛЯ ВЫВОДА ==========
def get_user_balance(user_id):
    """Получает баланс пользователя (сумму всех курьеров)"""
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Ошибка в get_user_balance: {e}")
        return 0

def create_withdrawal_request(user_id, amount, method, details):
    conn = get_db()
    c = conn.cursor()
    try:
        request_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''INSERT INTO withdrawals 
                     (user_id, amount, payment_method, payment_details, request_date, status) 
                     VALUES (?, ?, ?, ?, ?, 'pending')''',
                  (user_id, amount, method, details, request_date))
        request_id = c.lastrowid
        conn.commit()
        return request_id
    except Exception as e:
        logger.error(f"Ошибка в create_withdrawal_request: {e}")
        return None

def get_pending_withdrawals():
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''SELECT w.id, w.user_id, u.first_name, u.username, 
                            w.amount, w.payment_method, w.payment_details, w.request_date
                     FROM withdrawals w
                     JOIN users u ON w.user_id = u.user_id
                     WHERE w.status = 'pending'
                     ORDER BY w.request_date ASC''')
        return c.fetchall()
    except Exception as e:
        logger.error(f"Ошибка в get_pending_withdrawals: {e}")
        return []

def confirm_withdrawal(request_id):
    """Подтверждает вывод средств и списывает баланс"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаем информацию о заявке
        c.execute('''SELECT user_id, amount FROM withdrawals WHERE id = ?''', (request_id,))
        withdrawal = c.fetchone()
        
        if not withdrawal:
            logger.error(f"❌ Заявка {request_id} не найдена")
            return
        
        user_id, amount = withdrawal
        
        # Проверяем текущий баланс
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        current_balance = c.fetchone()[0]
        
        if current_balance < amount:
            logger.error(f"❌ Недостаточно средств: баланс {current_balance}, запрос {amount}")
            return
        
        # Обновляем баланс пользователя
        new_balance = current_balance - amount
        c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        
        # Обновляем статус заявки
        c.execute("UPDATE withdrawals SET status = 'completed' WHERE id = ?", (request_id,))
        
        conn.commit()
        logger.info(f"✅ Подтвержден вывод {amount} для пользователя {user_id}. Новый баланс: {new_balance}")
        
    except Exception as e:
        logger.error(f"Ошибка в confirm_withdrawal: {e}")
# ========== ФУНКЦИИ ДЛЯ КУРЬЕРОВ ==========
def add_courier(recruiter_id, recruiter_username, recruiter_name, full_name, city):
    # ========== ПРИНУДИТЕЛЬНОЕ ЛОГИРОВАНИЕ ==========
    logger.info("="*50)
    logger.info("🔥🔥🔥 ADD_COURIER ВЫЗВАНА!")
    logger.info(f"  recruiter_id: {recruiter_id} (тип: {type(recruiter_id)})")
    logger.info(f"  recruiter_username: {recruiter_username}")
    logger.info(f"  recruiter_name: {recruiter_name}")
    logger.info(f"  full_name: {full_name}")
    logger.info(f"  city: {city}")
    logger.info("="*50)
    # ================================================
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Проверяем, есть ли вообще пользователь с таким ID
        c.execute("SELECT * FROM users WHERE user_id = ?", (recruiter_id,))
        user = c.fetchone()
        if user:
            logger.info(f"   ✅ Рекрутер найден: {user[2]} (@{user[1]})")
        else:
            logger.warning(f"   ⚠️ Рекрутер с ID {recruiter_id} не найден в БД, создаем...")
            registration_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO users 
                (user_id, username, first_name, last_name, registration_date, balance, test_passed) 
                VALUES (?, ?, ?, ?, ?, 0, 0)
            """, (recruiter_id, recruiter_username, recruiter_name, "", registration_date))
            conn.commit()
            logger.info(f"✅ Пользователь {recruiter_id} создан с username @{recruiter_username}")
        
        # Проверяем, нет ли уже такого курьера у этого рекрутера
        c.execute('''SELECT id FROM couriers 
                     WHERE recruiter_id = ? AND full_name = ? AND city = ? AND status = 'confirmed' ''',
                  (recruiter_id, full_name, city))
        exists = c.fetchone()
        
        if exists:
            logger.info(f"   ⚠️ Курьер уже существует в БД с id={exists[0]}")
            return False, "Курьер с такими данными уже подтвержден"
        
        # ========== ВСТАВЛЯЕМ КУРЬЕРА ==========
        registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"   📦 Вставляем в БД: recruiter_id={recruiter_id}, {full_name}, {city}")
        
        c.execute('''INSERT INTO couriers 
                     (recruiter_id, full_name, city, status, registered_at)
                     VALUES (?, ?, ?, ?, ?)''',
                  (recruiter_id, full_name, city, 'pending', registered_at))
        
        logger.info(f"   ✅ INSERT выполнен, rows affected: {conn.total_changes}")
        conn.commit()
        
        # ========== ПРОВЕРЯЕМ, ЧТО ЗАПИСАЛОСЬ ==========
        c.execute("SELECT * FROM couriers WHERE recruiter_id = ? AND full_name = ? AND city = ? ORDER BY id DESC LIMIT 1", 
                  (recruiter_id, full_name, city))
        last = c.fetchone()
        if last:
            logger.info(f"   ✅ ЗАПИСЬ НАЙДЕНА В БД:")
            logger.info(f"      id: {last[0]}")
            logger.info(f"      recruiter_id: {last[1]}")
            logger.info(f"      full_name: {last[2]}")
            logger.info(f"      city: {last[3]}")
            logger.info(f"      status: {last[4]}")
            logger.info(f"      balance: {last[5]}")
        else:
            logger.error(f"   ❌ ЗАПИСЬ НЕ НАЙДЕНА В БД ПОСЛЕ INSERT!")
        # ==============================================
        
        # ========== ОБНОВЛЯЕМ ОБЩИЙ БАЛАНС РЕКРУТЕРА ==========
        c.execute("SELECT SUM(balance) FROM couriers WHERE recruiter_id = ?", (recruiter_id,))
        total_balance = c.fetchone()[0] or 0
        c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (total_balance, recruiter_id))
        logger.info(f"👤 Обновлен общий баланс рекрутера {recruiter_id}: {total_balance}")
        # =====================================================
        
        # Получаем актуальные данные для Google Sheets
        c.execute("SELECT first_name, username FROM users WHERE user_id = ?", (recruiter_id,))
        recruiter = c.fetchone()
        final_recruiter_name = recruiter[0] if recruiter and recruiter[0] else recruiter_name
        final_recruiter_username = recruiter[1] if recruiter and recruiter[1] else recruiter_username
        
        # Отправляем в Google Sheets
        success, row_number = add_courier_to_google_sheet(
            final_recruiter_name, final_recruiter_username, full_name, city
        )
        
        if success and row_number:
            # Обновляем номер строки в БД
            c.execute('''UPDATE couriers SET sheet_row = ? 
                         WHERE recruiter_id = ? AND full_name = ? AND city = ? AND status = 'pending' ''',
                      (row_number, recruiter_id, full_name, city))
            conn.commit()
            logger.info(f"✅ Курьер {full_name} добавлен, строка в таблице: {row_number}")
        
        return True, "Заявка на курьера отправлена на проверку! ✅"
        
    except Exception as e:
        logger.error(f"❌ Ошибка в add_courier: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Ошибка: {str(e)}"
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
    else:
        logger.info(f"👤 Пользователь {user_id} уже зарегистрирован")
    
    # Получаем статус теста
    test_passed = 0
    conn = None
    try:
        conn = get_db()  # ← ЭТО ВАЖНО!
        if conn is None:
            logger.error("❌ Не удалось получить соединение с БД")
            test_passed = 0
        else:
            c = conn.cursor()
            c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            test_passed = result[0] if result else 0
            logger.info(f"👤 Пользователь {user_id} test_passed={test_passed}")
            if test_passed == 1:
                logger.info(f"   ✅ Тест пройден, показываем полное меню")
            else:
                logger.info(f"   ❌ Тест не пройден, показываем ограниченное меню")
    except Exception as e:
        logger.error(f"Ошибка при проверке test_passed в start: {e}")
        test_passed = 0
    
    if test_passed == 1:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
            [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
            [InlineKeyboardButton("👤 Личный кабинет", callback_data='personal_account')],
            [InlineKeyboardButton("💼 Ставки по городам", callback_data='rates')],
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
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        test_passed = result[0] if result else 0
    except Exception as e:
        logger.error(f"Ошибка при проверке test_passed: {e}")
        test_passed = 0
    protected_sections = ['withdrawal', 'personal_account', 'my_couriers', 'add_courier', 'rates']
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
    elif data == 'rates':
        await show_rates(query, context)
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

async def show_rates(query, context):
    """Временная заглушка для ставок по городам"""
    text = (
        "💼 *Ставки по городам*\n\n"
        "⚙️ Раздел находится в разработке.\n\n"
        "Скоро здесь появится актуальная информация о:\n"
        "• Доходах курьеров в разных городах\n"
        "• Бонусных программах\n"
        "• Специальных предложениях\n\n"
        "Следите за обновлениями! 🚀"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
    await edit_and_track(
        query, context,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

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
    
    # КНОПКИ ДЛЯ АДМИНА
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
def get_recruiter_couriers(recruiter_id):
    """Получает всех курьеров рекрутера"""
    conn = None
    try:
        conn = get_db()
        if conn is None:
            logger.error("❌ Не удалось получить соединение с БД в get_recruiter_couriers")
            return []
            
        c = conn.cursor()
        c.execute('''SELECT full_name, city, status, registered_at, confirmed_at, balance 
                     FROM couriers 
                     WHERE recruiter_id = ? 
                     ORDER BY registered_at DESC''', (recruiter_id,))
        return c.fetchall()
    except Exception as e:
        logger.error(f"Ошибка в get_recruiter_couriers: {e}")
        return []
async def show_my_couriers(query, user_id, context):
    couriers = get_recruiter_couriers(user_id)
    total_balance = get_user_balance(user_id)
    
    if not couriers:
        text = f"📭 *У вас пока нет записанных курьеров*\n\n💰 *Общий баланс:* {total_balance} руб."
    else:
        text = f"👥 *Ваши курьеры:*\n\n💰 *Общий баланс:* {total_balance} руб.\n\n"
        for full_name, city, status, reg_date, conf_date, balance in couriers:  # ← добавил balance
            date_obj = datetime.strptime(reg_date, "%Y-%m-%d %H:%M:%S")
            date_str = date_obj.strftime("%d.%m.%Y")
            
            if status == 'confirmed':
                status_emoji = "✅"
                conf_info = f" (подтвержден"
                if conf_date:
                    conf_date_obj = datetime.strptime(conf_date, "%Y-%m-%d %H:%M:%S")
                    conf_info += f" {conf_date_obj.strftime('%d.%m.%Y')}"
                conf_info += ")"
            elif status == 'rejected':
                status_emoji = "❌"
                conf_info = f" (отклонен)"
            else:
                status_emoji = "⏳"
                conf_info = f" (ожидает проверки)"
            
            # ========== ДОБАВЛЯЕМ БАЛАНС ==========
            text += f"{status_emoji} *{full_name}* — {city}\n"
            text += f"   📅 {date_str}{conf_info}\n"
            text += f"   💰 Баланс: {balance} руб.\n\n"  # ← вот эта строка
            # ======================================
    
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
        "`Иванов Иван, Москва`\n\n"
        "После отправки заявка будет отправлена на проверку администратору. ✅"
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
    username = update.effective_user.username or f"user_{user_id}"
    first_name = update.effective_user.first_name or "Пользователь"
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
        
        success, message = add_courier(user_id, username, first_name, full_name, city)
        
        if success:
            await send_and_track(
                update, context,
                f"✅ *{message}*\n\n"
                f"👤 *Имя:* {full_name}\n"
                f"🏙 *Город:* {city}\n\n"
                f"Статус будет обновлен после проверки администратором.",
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
            logger.info("🔥 ТЕСТ ЗАВЕРШЕН, вызываем finish_test")
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
        # Пытаемся обновить статус в БД
        try:
            update_test_status(user_id, True)
            logger.info(f"✅ Тест сдан успешно, статус обновлен для user_id={user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении статуса: {e}")
        
        # Принудительно показываем главное меню
        await back_to_main(query, user_id, context)
        return
        
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

💰 *Бонусы за приглашение курьеров*

Вы можете приглашать курьеров и получать бонусы за успешных кандидатов. Однако помните:

• ❌ Попытки обмана (фейковые анкеты, накрутки) приведут к мгновенной блокировке аккаунта
• ✅ Работайте честно, привлекайте реальных курьеров
• 💰 Только качественные кандидаты приносят стабильный доход

*Будьте честны с сервисом — и сервис будет честен с вами!*
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
    test_passed = 0
    try:
        conn = get_db()  # Получаем глобальное соединение
        c = conn.cursor()
        c.execute("SELECT test_passed FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        test_passed = result[0] if result else 0
        logger.info(f"📊 back_to_main: user_id={user_id}, test_passed={test_passed}")
    except Exception as e:
        logger.error(f"Ошибка при проверке test_passed в back_to_main: {e}")
        test_passed = 0
    
    # НЕ закрываем соединение здесь!
    
    if test_passed == 1:
        keyboard = [
            [InlineKeyboardButton("📋 Вся информация", callback_data='all_info')],
            [InlineKeyboardButton("📝 Пройти тест", callback_data='take_test')],
            [InlineKeyboardButton("💰 Вывод средств", callback_data='withdrawal')],
            [InlineKeyboardButton("👤 Личный кабинет", callback_data='personal_account')],
            [InlineKeyboardButton("💼 Ставки по городам", callback_data='rates')],
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
# ========== АДМИН-КОМАНДЫ ==========
async def admin_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return
    
    tickets = get_open_tickets()
    withdrawals = get_pending_withdrawals()
    
    if not tickets and not withdrawals:
        await update.message.reply_text("📭 Нет активных обращений")
        return
    
    text = ""
    
    if tickets:
        text += "🆘 АКТИВНЫЕ ОБРАЩЕНИЯ В ПОДДЕРЖКУ:\n\n"
        for ticket in tickets:
            text += f"🆔 {ticket[0]}\n"
            text += f"👤 {ticket[3]} (@{ticket[2]})\n"
            text += f"📝 {ticket[4][:100]}...\n"
            text += f"📅 {ticket[5]}\n"
            text += "──────────────────────\n"
    
    if withdrawals:
        if tickets:
            text += "\n"
        text += "💰 ОЖИДАЮЩИЕ ЗАЯВКИ НА ВЫВОД:\n\n"
        for w in withdrawals:
            text += f"🆔 {w[0]}\n"
            text += f"👤 {w[2]} (@{w[3]})\n"
            text += f"💰 {w[4]} руб.\n"
            text += f"💳 {w[5]}\n"
            text += f"📝 {w[6]}\n"
            text += f"📅 {w[7]}\n"
            text += "──────────────────────\n"
    
    await update.message.reply_text(text)

# ========== СЮДА ВСТАВЛЯЕМ НОВУЮ ФУНКЦИЮ ==========
async def admin_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительная синхронизация статусов с Google Sheets (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return
    
    status_msg = await update.message.reply_text("🔄 Начинаю синхронизацию с Google Sheets...")
    
    try:
        # Запускаем синхронизацию
        check_pending_couriers()
        
        # Получаем статистику
        conn = get_db()
        c = conn.cursor()
        
        # Считаем курьеров по статусам
        c.execute("SELECT status, COUNT(*) FROM couriers GROUP BY status")
        stats = c.fetchall()
        
        stats_text = "\n".join([f"• {s[0]}: {s[1]}" for s in stats]) if stats else "• нет данных"
        
        await status_msg.edit_text(
            f"✅ *Синхронизация завершена!*\n\n"
            f"📊 *Текущая статистика курьеров:*\n{stats_text}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка синхронизации: {str(e)}")

# ========== СЮДА ВСТАВЛЯЕМ НОВУЮ ФУНКЦИЮ ==========
async def admin_check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка файла БД"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        # Проверяем существование файла
        if os.path.exists('bot_database.db'):
            size = os.path.getsize('bot_database.db')
            text = f"✅ Файл БД существует\n📦 Размер: {size} байт\n📍 Путь: {os.path.abspath('bot_database.db')}\n\n"
            
            # Показываем статистику
            conn = get_db()
            c = conn.cursor()
            
            # Сколько курьеров
            c.execute("SELECT COUNT(*) FROM couriers")
            couriers_count = c.fetchone()[0]
            text += f"👥 Курьеров в БД: {couriers_count}\n"
            
            # Сколько пользователей
            c.execute("SELECT COUNT(*) FROM users")
            users_count = c.fetchone()[0]
            text += f"👤 Пользователей в БД: {users_count}\n"
            
            # Показываем первых 5 курьеров
            if couriers_count > 0:
                c.execute("SELECT full_name, city, status FROM couriers LIMIT 5")
                couriers = c.fetchall()
                text += "\n📋 Первые 5 курьеров:\n"
                for i, (name, city, status) in enumerate(couriers, 1):
                    emoji = "✅" if status == 'confirmed' else "⏳" if status == 'pending' else "❌"
                    text += f"{i}. {emoji} {name} - {city}\n"
            else:
                text += "\n❌ В БД нет курьеров!"
            
        else:
            text = f"❌ Файл БД НЕ существует!\n📍 Путь: {os.path.abspath('bot_database.db')}"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
# ========== СЮДА ВСТАВЛЯЕМ НОВУЮ ФУНКЦИЮ ==========
async def admin_check_couriers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка всех курьеров в БД"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Смотрим всех курьеров с их рекрутерами
        c.execute('''
            SELECT c.id, c.full_name, c.city, c.status, c.balance, c.recruiter_id, u.username, u.first_name
            FROM couriers c
            LEFT JOIN users u ON c.recruiter_id = u.user_id
            ORDER BY c.id DESC
        ''')
        couriers = c.fetchall()
        
        if not couriers:
            await update.message.reply_text("📭 В БД нет курьеров")
            return
        
        text = "📋 *ВСЕ КУРЬЕРЫ В БД:*\n\n"
        for courier in couriers:
            id, name, city, status, balance, recruiter_id, username, first_name = courier
            status_emoji = "✅" if status == 'confirmed' else "⏳" if status == 'pending' else "❌"
            recruiter_info = f"@{username}" if username else f"ID:{recruiter_id}"
            if recruiter_id == update.effective_user.id:
                recruiter_info += " 👈 ЭТО ТЫ!"
            
            text += f"{status_emoji} *{name}* - {city}\n"
            text += f"   🆔 Курьера: {id}\n"
            text += f"   👤 Рекрутер: {recruiter_info}\n"
            text += f"   💰 Баланс: {balance}\n\n"
        
        # Разбиваем на части если слишком длинно
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await update.message.reply_text(text[i:i+4000], parse_mode='Markdown')
        else:
            await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
async def admin_check_couriers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка всех курьеров в БД"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Смотрим всех курьеров с их рекрутерами
        c.execute('''
            SELECT c.id, c.full_name, c.city, c.status, c.balance, c.recruiter_id, u.username, u.first_name
            FROM couriers c
            LEFT JOIN users u ON c.recruiter_id = u.user_id
            ORDER BY c.id DESC
        ''')
        couriers = c.fetchall()
        
        if not couriers:
            await update.message.reply_text("📭 В БД нет курьеров")
            return
        
        text = "📋 *ВСЕ КУРЬЕРЫ В БД:*\n\n"
        for courier in couriers:
            id, name, city, status, balance, recruiter_id, username, first_name = courier
            status_emoji = "✅" if status == 'confirmed' else "⏳" if status == 'pending' else "❌"
            recruiter_info = f"@{username}" if username else f"ID:{recruiter_id}"
            if recruiter_id == update.effective_user.id:
                recruiter_info += " 👈 ЭТО ТЫ!"
            
            text += f"{status_emoji} *{name}* - {city}\n"
            text += f"   🆔 Курьера: {id}\n"
            text += f"   👤 Рекрутер: {recruiter_info}\n"
            text += f"   💰 Баланс: {balance}\n\n"
        
        # Разбиваем на части если слишком длинно
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await update.message.reply_text(text[i:i+4000], parse_mode='Markdown')
        else:
            await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ========== СЮДА ВСТАВЛЯЕМ НОВУЮ ФУНКЦИЮ ==========
async def admin_fix_my_couriers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исправляет только курьеров, созданных через бота"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Находим курьеров, у которых нет recruiter_id, но они есть в Google Sheets с твоим username
        c.execute('''
            UPDATE couriers 
            SET recruiter_id = ? 
            WHERE recruiter_id IS NULL 
            AND sheet_row IS NOT NULL
        ''', (ADMIN_ID,))
        
        updated = c.rowcount
        conn.commit()
        
        await update.message.reply_text(
            f"✅ Исправлено {updated} курьеров!\n"
            f"Теперь они привязаны к твоему ID ({ADMIN_ID})"
        )
        
        # Показываем обновленный список
        await admin_check_couriers(update, context)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
async def admin_fix_my_couriers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исправляет только курьеров, созданных через бота"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Находим курьеров, у которых нет recruiter_id, но они есть в Google Sheets с твоим username
        c.execute('''
            UPDATE couriers 
            SET recruiter_id = ? 
            WHERE recruiter_id IS NULL 
            AND sheet_row IS NOT NULL
        ''', (ADMIN_ID,))
        
        updated = c.rowcount
        conn.commit()
        
        await update.message.reply_text(
            f"✅ Исправлено {updated} курьеров!\n"
            f"Теперь они привязаны к твоему ID ({ADMIN_ID})"
        )
        
        # Показываем обновленный список
        await admin_check_couriers(update, context)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ========== СЮДА ВСТАВЛЯЕМ НОВУЮ ФУНКЦИЮ ==========
async def admin_fix_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исправляет фейковых пользователей на реальные данные"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Обновляем твоего пользователя
        c.execute('''
            UPDATE users 
            SET username = ?, first_name = ? 
            WHERE user_id = ?
        ''', ("unknownsorcerer", "costa", ADMIN_ID))
        
        updated = c.rowcount
        conn.commit()
        
        await update.message.reply_text(
            f"✅ Исправлен пользователь с ID {ADMIN_ID}\n"
            f"Теперь username: @unknownsorcerer, имя: costa"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ========== ТЕСТ GOOGLE SHEETS ==========
async def test_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки Google Sheets"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для админа")
        return
    
    await update.message.reply_text("🔄 Тестирую подключение к Google Sheets...")
    
    try:
        creds_json = os.environ.get('GOOGLE_CREDS_JSON')
        sheet_id = os.environ.get('GOOGLE_SHEET_ID')
        
        if not creds_json:
            await update.message.reply_text("❌ GOOGLE_CREDS_JSON не найдена")
            return
        
        if not sheet_id:
            await update.message.reply_text("❌ GOOGLE_SHEET_ID не найдена")
            return
        
        await update.message.reply_text(f"✅ Переменные найдены\nID таблицы: {sheet_id}")
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        
        try:
            creds_dict = json.loads(creds_json)
            await update.message.reply_text("✅ JSON распарсен успешно")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка парсинга JSON: {str(e)}")
            return
        
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            await update.message.reply_text("✅ Credentials созданы")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка создания credentials: {str(e)}")
            return
        
        try:
            client = gspread.authorize(creds)
            await update.message.reply_text("✅ Авторизация в Google Sheets успешна")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка авторизации: {str(e)}")
            return
        
        try:
            sheet = client.open_by_key(sheet_id).sheet1
            await update.message.reply_text("✅ Таблица открыта успешно")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка открытия таблицы: {str(e)}")
            return
        
        try:
            test_row = [
                datetime.now().strftime("%d.%m.%Y %H:%M"),
                "ТЕСТ",
                "@test",
                "Тестовый Курьер",
                "Тест-город",
                "⏳ Ожидает",
                "",
                ""
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
    start_auto_backup()
    init_database()
    start_sheet_monitoring()
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("sync", admin_sync))
    application.add_handler(CommandHandler("checkdb", admin_check_db))
    application.add_handler(CommandHandler("couriers", admin_check_couriers))
    application.add_handler(CommandHandler("fixmy", admin_fix_my_couriers))  # ← добавить эту строку
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_requests))
    application.add_handler(CommandHandler("testgoogle", test_google))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CallbackQueryHandler(next_question_callback, pattern='^next_question$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("fixusers", admin_fix_users))
    
    logger.info("Бот запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()














































