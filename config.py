import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
ADMIN_GROUP_ID = os.getenv('ADMIN_GROUP_ID')

if ADMIN_GROUP_ID:
    ADMIN_GROUP_ID = int(ADMIN_GROUP_ID)

# ============================================
# АДМИНИСТРАТОРЫ
# ============================================
ADMIN_ACCESS = {
    8494622112: {
        'role': 'owner',
        'code': 'admin672345',
        'username': '@voloki4'
    },
    1302410770: {
        'role': 'admin',
        'code': 'zxcmayoho222',
        'username': '@myhzxc'
    },
    # 🥈 Заместитель владельца
    1427959789: {
        'role': 'deputy',
        'code': 'Zmadmin56',
        'username': '@Mementaaa'
    },
}

ADMIN_IDS = list(ADMIN_ACCESS.keys())
OWNER_ID = 8494622112
TECH_ADMIN_ID = 1302410770

# ============================================
# НАЗВАНИЯ ЛИСТОВ
# ============================================
PRODUCTS_SHEET = 'Табель цеников'
CATEGORIES_SHEET = 'Категории'
ORDERS_SHEET = 'Заказы'
REVIEWS_SHEET = 'Отзывы'

# ============================================
# ФУНКЦИИ
# ============================================
def get_admin_info(user_id):
    return ADMIN_ACCESS.get(user_id)

def get_admin_role(user_id):
    info = get_admin_info(user_id)
    return info.get('role') if info else None

def get_admin_code(user_id):
    info = get_admin_info(user_id)
    return info.get('code') if info else None

def get_admin_username(user_id):
    info = get_admin_info(user_id)
    return info.get('username') if info else None

def is_admin(user_id):
    return user_id in ADMIN_ACCESS

def is_owner(user_id):
    info = get_admin_info(user_id)
    return info.get('role') == 'owner' if info else False

def is_deputy(user_id):
    info = get_admin_info(user_id)
    return info.get('role') == 'deputy' if info else False

def is_owner_or_deputy(user_id):
    return is_owner(user_id) or is_deputy(user_id)

def check_access_code(user_id, code):
    valid_code = get_admin_code(user_id)
    return valid_code and valid_code == code
