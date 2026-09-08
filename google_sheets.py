import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, PRODUCTS_SHEET, CATEGORIES_SHEET, ORDERS_SHEET
import logging

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_client():
    creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    return gspread.authorize(creds)

def get_products_sheet():
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(PRODUCTS_SHEET)

def get_categories_sheet():
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(CATEGORIES_SHEET)

def get_orders_sheet():
    client = get_client()
    return client.open_by_key(SHEET_ID).worksheet(ORDERS_SHEET)

def get_active_categories():
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
    products = get_all_products()
    return [p for p in products if p['category'].lower() == category.lower()]

def get_product_by_id(product_id):
    products = get_all_products()
    for p in products:
        if p['id'] == product_id:
            return p
    return None

def get_subcategories(category):
    products = get_products_by_category(category)
    subcategories = set()
    for p in products:
        if p.get('subcategory'):
            subcategories.add(p['subcategory'])
    return sorted(list(subcategories))

def get_products_by_subcategory(category, subcategory):
    products = get_products_by_category(category)
    return [p for p in products if p.get('subcategory', '').lower() == subcategory.lower()]

def add_order(order_data):
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
        ''
    ]
    sheet.append_row(row)
    logger.info(f"Заказ добавлен: {order_data['user_id']}")