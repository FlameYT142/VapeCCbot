import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, PRODUCTS_SHEET, CATEGORIES_SHEET, ORDERS_SHEET, REVIEWS_SHEET
from datetime import datetime
import logging
import json
import os

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def get_client():
    """
    Получить авторизованного клиента для Google Sheets.
    
    Приоритет:
    1. Переменная окружения GOOGLE_CREDENTIALS (для продакшена)
    2. Файл credentials.json (для локальной разработки)
    """
    try:
        # Пробуем получить credentials из переменной окружения
        creds_json = os.getenv('GOOGLE_CREDENTIALS')
        
        if creds_json:
            # Используем переменную окружения
            logger.info("✅ Используем GOOGLE_CREDENTIALS из переменных окружения")
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            return gspread.authorize(creds)
        else:
            # Если переменной нет, пробуем загрузить из файла (для локального запуска)
            logger.info("📁 GOOGLE_CREDENTIALS не найдена, пробуем загрузить credentials.json")
            creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
            return gspread.authorize(creds)
            
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
    """Получить лист с товарами"""
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(PRODUCTS_SHEET)


def get_categories_sheet():
    """Получить лист с категориями"""
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(CATEGORIES_SHEET)


def get_orders_sheet():
    """Получить лист с заказами"""
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(ORDERS_SHEET)


def get_reviews_sheet():
    """Получить лист с отзывами (создает, если не существует)"""
    client = get_client()
    try:
        return client.open_by_key(SHEET_ID).worksheet(REVIEWS_SHEET)
    except gspread.WorksheetNotFound:
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.add_worksheet(title=REVIEWS_SHEET, rows=100, cols=20)


def get_active_categories():
    """Получить активные категории для отображения в меню"""
    try:
        sheet = get_categories_sheet()
        data = sheet.get_all_values()
        if len(data) < 2:
            return []
        
        categories = []
        for row in data[1:]:
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
    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}")
        return []


def get_all_products():
    """Получить все товары из таблицы"""
    sheet = get_products_sheet()
    data = sheet.get_all_values()
    if len(data) < 2:
        return []
    
    products = []
    for row in data[1:]:
        if len(row) >= 7 and row[0] and row[0].strip():
            try:
                product = {
                    'id': row[0].strip(),
                    'name': row[1].strip(),
                    'category': row[2].strip() if len(row) > 2 else 'Другое',
                    'price': float(row[3].strip().replace(',', '.')) if len(row) > 3 and row[3] else 0,
                    'description': row[4].strip() if len(row) > 4 else '',
                    'photo': row[5].strip() if len(row) > 5 else '',
                    'in_stock': row[6].strip().lower() == 'да' if len(row) > 6 else False
                }
                if product['price'] > 0 and product['name']:
                    products.append(product)
            except (ValueError, IndexError) as e:
                logger.warning(f"Ошибка товара {row}: {e}")
                continue
    return products


def get_products_by_category(category):
    """Получить товары по категории"""
    products = get_all_products()
    return [p for p in products if p['category'].lower() == category.lower()]


def get_product_by_id(product_id):
    """Найти товар по ID"""
    products = get_all_products()
    for p in products:
        if p['id'] == product_id:
            return p
    return None


def get_subcategories(category):
    """Получить подкатегории для категории"""
    products = get_products_by_category(category)
    subcategories = set()
    for p in products:
        if p.get('subcategory'):
            subcategories.add(p['subcategory'])
    return sorted(list(subcategories))


def get_products_by_subcategory(category, subcategory):
    """Получить товары по подкатегории"""
    products = get_products_by_category(category)
    return [p for p in products if p.get('subcategory', '').lower() == subcategory.lower()]


def add_order(order_data):
    """
    Добавить заказ в таблицу
    
    order_data: {
        'user_id': int,
        'username': str,
        'items': list,
        'total': float,
        'address': str,
        'status': str
    }
    """
    sheet = get_orders_sheet()
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
        datetime.now().strftime('%d.%m.%Y %H:%M')
    ]
    sheet.append_row(row)
    logger.info(f"Заказ добавлен: {order_data['user_id']}")
    return len(sheet.get_all_values()) - 1  # Возвращаем номер строки заказа


def update_order_status(order_row, status):
    """Обновить статус заказа"""
    sheet = get_orders_sheet()
    sheet.update_cell(order_row, 6, status)  # Столбец F - статус


def save_review(user_id, username, order_id, product_rating, service_rating, comment):
    """Сохранить отзыв в таблицу"""
    sheet = get_reviews_sheet()
    
    # Проверяем, есть ли заголовки
    headers = sheet.row_values(1)
    if not headers:
        headers = ['ID пользователя', 'Юзернейм', 'Номер заказа', 'Оценка товара', 'Оценка сервиса', 'Комментарий', 'Дата']
        sheet.insert_row(headers, 1)
    
    row = [
        str(user_id),
        username or 'Без юзернейма',
        str(order_id),
        str(product_rating),
        str(service_rating),
        comment or '-',
        datetime.now().strftime('%d.%m.%Y %H:%M')
    ]
    sheet.append_row(row)
    logger.info(f"Отзыв сохранен от {username} (заказ #{order_id})")
    return True
