import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, PRODUCTS_SHEET, CATEGORIES_SHEET, ORDERS_SHEET, REVIEWS_SHEET
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import json
import os

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
BRATSK_TZ = ZoneInfo("Asia/Irkutsk")


def get_client():
    try:
        creds_json = os.getenv('GOOGLE_CREDENTIALS')
        
        if creds_json:
            logger.info("✅ Используем GOOGLE_CREDENTIALS из переменных окружения")
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            return gspread.authorize(creds)
        else:
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
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(PRODUCTS_SHEET)


def get_categories_sheet():
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(CATEGORIES_SHEET)


def get_orders_sheet():
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(ORDERS_SHEET)


def get_reviews_sheet():
    client = get_client()
    try:
        return client.open_by_key(SHEET_ID).worksheet(REVIEWS_SHEET)
    except gspread.WorksheetNotFound:
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.add_worksheet(title=REVIEWS_SHEET, rows=100, cols=20)


def get_active_categories():
    try:
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
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения категорий: {type(e).__name__}: {e}")
        return []


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
                except:
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


def update_product_quantity(product_row, new_quantity):
    try:
        sheet = get_products_sheet()
        sheet.update_cell(product_row, 4, str(new_quantity))
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления количества: {e}")
        return False


def decrease_product_quantity(product_row, amount=1):
    try:
        sheet = get_products_sheet()
        current_quantity = sheet.cell(product_row, 4).value
        try:
            current = int(float(current_quantity)) if current_quantity else 0
        except:
            current = 0
        
        new_quantity = max(0, current - amount)
        sheet.update_cell(product_row, 4, str(new_quantity))
        
        logger.info(f"📦 Товар строка {product_row}: {current} → {new_quantity}")
        return new_quantity
    except Exception as e:
        logger.error(f"❌ Ошибка списания: {e}")
        return 0


def add_product_to_sheet(name, price, quantity):
    try:
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
        
    except Exception as e:
        logger.error(f"❌ Ошибка добавления товара: {e}")
        return None


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


def update_order_status(order_row, status):
    try:
        sheet = get_orders_sheet()
        row_in_sheet = order_row + 1
        sheet.update_cell(row_in_sheet, 6, status)
        logger.info(f"✅ Заказ #{order_row}: статус → {status}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления статуса: {e}")
        return False


def get_user_orders(user_id):
    try:
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
    except Exception as e:
        logger.error(f"❌ Ошибка получения заказов: {type(e).__name__}: {e}")
        return []


def save_review(user_id, username, order_id, product_rating, service_rating, comment):
    try:
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
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения отзыва: {e}")
        return False
