import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, PRODUCTS_SHEET, CATEGORIES_SHEET, ORDERS_SHEET, REVIEWS_SHEET
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import json
import os
import time
import random
from functools import wraps
from gspread.exceptions import APIError

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
BRATSK_TZ = ZoneInfo("Asia/Irkutsk")

MIN_INTERVAL_BETWEEN_REQUESTS = 1.2
CACHE_TTL_SECONDS = 60
MAX_RETRIES = 5

_last_request_time = 0.0
_categories_cache = None
_categories_cache_time = 0.0
_client = None


def _throttle():
    global _last_request_time
    now = time.time()
    wait = MIN_INTERVAL_BETWEEN_REQUESTS - (now - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.time()


def retry_on_429(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                _throttle()
                return func(*args, **kwargs)
            except APIError as e:
                code = getattr(e.response, "status_code", None)
                if code == 429 or "429" in str(e):
                    wait = 2 ** attempt + random.uniform(0, 1)
                    logger.warning(f"⚠️ 429 от Google Sheets. Ждём {wait:.1f} сек (попытка {attempt + 1})")
                    time.sleep(wait)
                else:
                    raise
            except Exception as e:
                logger.error(f"❌ Ошибка Sheets API: {e}")
                raise
        raise RuntimeError("429 не отпустил после всех попыток")
    return wrapper


def get_client():
    global _client
    if _client is not None:
        return _client

    try:
        creds_json = os.getenv('GOOGLE_CREDENTIALS')

        if creds_json:
            logger.info("✅ Используем GOOGLE_CREDENTIALS из переменных окружения")
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            logger.info("📁 GOOGLE_CREDENTIALS не найдена, пробуем credentials.json")
            creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)

        _client = gspread.authorize(creds)
        return _client

    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга GOOGLE_CREDENTIALS: {e}")
        raise
    except FileNotFoundError as e:
        logger.error(f"❌ Файл credentials.json не найден: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации Google Sheets: {e}")
        raise


def get_products_sheet():
    return get_client().open_by_key(SHEET_ID).worksheet(PRODUCTS_SHEET)


def get_categories_sheet():
    return get_client().open_by_key(SHEET_ID).worksheet(CATEGORIES_SHEET)


def get_orders_sheet():
    return get_client().open_by_key(SHEET_ID).worksheet(ORDERS_SHEET)


def get_reviews_sheet():
    client = get_client()
    try:
        return client.open_by_key(SHEET_ID).worksheet(REVIEWS_SHEET)
    except gspread.WorksheetNotFound:
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.add_worksheet(title=REVIEWS_SHEET, rows=100, cols=20)


@retry_on_429
def _read_active_categories():
    sheet = get_categories_sheet()
    data = sheet.get_all_values()
    if len(data) < 2:
        return []

    categories = []
    for i, row in enumerate(data[1:], start=2):
        if len(row) >= 4 and row[0].strip():
            is_active = row[3].strip().lower() == 'да' if len(row) > 3 else True
            if is_active:
                categories.append({
                    'name': row[0].strip(),
                    'emoji': row[1].strip() if len(row) > 1 else '📦',
                    'order': int(row[2]) if len(row) > 2 and row[2].strip().isdigit() else 999,
                    'active': is_active
                })
    return sorted(categories, key=lambda x: x['order'])


def get_active_categories(force_refresh=False):
    global _categories_cache, _categories_cache_time
    now = time.time()
    if (
        not force_refresh
        and _categories_cache is not None
        and (now - _categories_cache_time) < CACHE_TTL_SECONDS
    ):
        logger.debug("📦 Категории из кэша")
        return _categories_cache

    try:
        cats = _read_active_categories()
        _categories_cache = cats
        _categories_cache_time = time.time()
        logger.info(f"✅ Категорий получено: {len(cats)}")
        return cats
    except Exception as e:
        logger.error(f"❌ Ошибка получения категорий: {type(e).__name__}: {e}")
        if _categories_cache is not None:
            logger.warning("↩️ Возвращаем устаревший кэш")
            return _categories_cache
        return []


@retry_on_429
def get_all_products(force_update=False):
    sheet = get_products_sheet()
    data = sheet.get_all_values()
    if len(data) < 2:
        return []

    products = []
    for i, row in enumerate(data[1:], start=2):
        if len(row) < 2:
            continue
        name = row[1].strip() if len(row) > 1 else ''
        if not name:
            continue

        try:
            price_str = row[2].strip().replace(',', '.').replace(' ', '') if len(row) > 2 else '0'
            price = float(price_str) if price_str else 0

            quantity = 0
            if len(row) > 3 and row[3].strip():
                try:
                    quantity = int(float(row[3].strip()))
                except Exception:
                    quantity = 0

            product_id = f"V{name[:3].upper()}{i}"
            product = {
                'id': product_id,
                'name': name,
                'category': 'Вейп',
                'price': price,
                'in_stock': quantity > 0,
                'quantity': quantity,
                'row': i
            }
            if product['price'] > 0:
                products.append(product)
        except (ValueError, IndexError) as e:
            logger.warning(f"Ошибка товара строка {i}: {e}")
            continue

    return products


def get_products_by_category(category):
    products = get_all_products()
    return [p for p in products if p['category'].lower() == category.lower()]


def get_product_by_id(product_id):
    products = get_all_products()
    for p in products:
        if p['id'] == product_id:
            return p
    return None


@retry_on_429
def update_product_quantity(product_row, new_quantity):
    sheet = get_products_sheet()
    sheet.update_cell(product_row, 4, str(new_quantity))
    return True


@retry_on_429
def decrease_product_quantity(product_row, amount=1):
    sheet = get_products_sheet()
    current_quantity = sheet.cell(product_row, 4).value
    try:
        current = int(float(current_quantity)) if current_quantity else 0
    except Exception:
        current = 0

    new_quantity = max(0, current - amount)
    sheet.update_cell(product_row, 4, str(new_quantity))
    logger.info(f"📦 Товар строка {product_row}: {current} → {new_quantity}")
    return new_quantity


@retry_on_429
def add_product_to_sheet(name, price, quantity):
    sheet = get_products_sheet()
    data = sheet.get_all_values()

    row_number = 2
    for i, row in enumerate(data[1:], start=2):
        if len(row) < 2 or not row[1].strip():
            row_number = i
            break
        row_number = i + 1

    sheet.update_cell(row_number, 2, name)
    sheet.update_cell(row_number, 3, str(price))
    sheet.update_cell(row_number, 4, str(quantity))
    sheet.update_cell(row_number, 5, f"=C{row_number}*D{row_number}")
    logger.info(f"✅ Товар добавлен: {name} (строка {row_number})")
    return row_number


@retry_on_429
def add_order(order_data):
    now = datetime.now(BRATSK_TZ)
    sheet = get_orders_sheet()
    data = sheet.get_all_values()
    order_number = len(data)

    items_str = "\n".join([
        f"{item['name']} x{item['quantity']} = {item['price'] * item['quantity']:.2f} руб."
        for item in order_data['items']
    ])

    row = [
        str(order_data['user_id']),
        order_data['username'] or 'Без юзернейма',
        items_str,
        f"{order_data['total']:.2f}",
        order_data['address'],
        order_data.get('status', 'Новый'),
        now.strftime('%d.%m.%Y %H:%M')
    ]
    sheet.append_row(row)
    logger.info(f"✅ Заказ #{order_number} добавлен: {order_data['user_id']}")
    return order_number


@retry_on_429
def update_order_status(order_row, status):
    sheet = get_orders_sheet()
    row_in_sheet = order_row + 1
    sheet.update_cell(row_in_sheet, 6, status)
    logger.info(f"✅ Заказ #{order_row}: статус → {status}")
    return True


@retry_on_429
def get_user_orders(user_id):
    sheet = get_orders_sheet()
    data = sheet.get_all_values()
    if len(data) < 2:
        return []

    orders = []
    for i, row in enumerate(data[1:], start=2):
        if len(row) >= 1 and str(row[0]).strip() == str(user_id):
            orders.append({
                'row': i - 1,
                'user_id': row[0].strip() if len(row) > 0 else '',
                'username': row[1].strip() if len(row) > 1 else '',
                'items': row[2].strip() if len(row) > 2 else '',
                'total': row[3].strip() if len(row) > 3 else '0',
                'address': row[4].strip() if len(row) > 4 else '',
                'status': row[5].strip() if len(row) > 5 else 'Новый',
                'date': row[6].strip() if len(row) > 6 else ''
            })
    return orders


@retry_on_429
def save_review(user_id, username, order_id, product_rating, service_rating, comment):
    sheet = get_reviews_sheet()

    headers = sheet.row_values(1)
    if not headers:
        headers = ['ID пользователя', 'Юзернейм', 'Номер заказа', 'Оценка товара', 'Оценка сервиса', 'Комментарий', 'Дата']
        sheet.insert_row(headers, 1)

    now = datetime.now(BRATSK_TZ)
    row = [
        str(user_id),
        username or 'Без юзернейма',
        str(order_id),
        str(product_rating),
        str(service_rating),
        comment or '-',
        now.strftime('%d.%m.%Y %H:%M')
    ]
    sheet.append_row(row)
    logger.info(f"Отзыв сохранен от {username} (заказ #{order_id})")
    return True


@retry_on_429
def get_orders_stats():
    """
    Собирает статистику по всем заказам из листа «Заказы».
    Возвращает словарь:
    {
        'total_orders': int,
        'total_clients': int,
        'total_revenue': float,
        'avg_check': float,
        'orders_today': int,
        'orders_week': int,
        'by_status': {status: count},
        'top_products': [(name, count), ...]
    }
    """
    sheet = get_orders_sheet()
    data = sheet.get_all_values()

    stats = {
        'total_orders': 0,
        'total_clients': 0,
        'total_revenue': 0.0,
        'avg_check': 0.0,
        'orders_today': 0,
        'orders_week': 0,
        'by_status': {},
        'top_products': [],
    }

    if len(data) < 2:
        return stats

    now = datetime.now(BRATSK_TZ)
    today = now.strftime('%d.%m.%Y')
    week_ago = now.timestamp() - 7 * 24 * 3600

    clients = set()
    product_counter = {}

    for row in data[1:]:
        if len(row) < 7:
            continue

        user_id = row[0].strip()
        items_str = row[2].strip() if len(row) > 2 else ''
        total_str = row[3].strip() if len(row) > 3 else '0'
        status = row[5].strip() if len(row) > 5 else 'Новый'
        date_str = row[6].strip() if len(row) > 6 else ''

        if user_id:
            clients.add(user_id)

        try:
            total = float(total_str.replace(',', '.').replace(' ', ''))
        except Exception:
            total = 0.0

        stats['total_orders'] += 1
        stats['total_revenue'] += total

        stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

        if date_str.startswith(today):
            stats['orders_today'] += 1

        try:
            order_dt = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
            order_dt = order_dt.replace(tzinfo=BRATSK_TZ)
            if order_dt.timestamp() >= week_ago:
                stats['orders_week'] += 1
        except Exception:
            pass

        for line in items_str.split('\n'):
            try:
                if ' x' in line:
                    name = line.rsplit(' x', 1)[0].strip()
                    if name:
                        product_counter[name] = product_counter.get(name, 0) + 1
            except Exception:
                pass

    stats['total_clients'] = len(clients)
    if stats['total_orders'] > 0:
        stats['avg_check'] = stats['total_revenue'] / stats['total_orders']

    stats['top_products'] = sorted(
        product_counter.items(), key=lambda x: x[1], reverse=True
    )[:5]

    return stats
