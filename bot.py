import logging
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import (
    BOT_TOKEN, ADMIN_ACCESS, ADMIN_IDS, OWNER_ID, TECH_ADMIN_ID,
    is_admin, is_owner, get_admin_role, get_admin_code, get_admin_username, check_access_code
)
from google_sheets import (
    get_all_products, get_product_by_id, get_active_categories,
    get_products_by_category, get_subcategories, get_products_by_subcategory, add_order
)
from cart import (
    get_cart, add_to_cart, remove_from_cart, clear_cart,
    get_cart_total, get_cart_text, save_order_data, get_order_data, clear_order_data
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Реквизиты для оплаты по карте
PAYMENT_DETAILS = """
💳 *Реквизиты для перевода:*

🏦 Банк: Т-Банк
📱 Номер карты: 1234 5678 9012 3456
👤 Получатель: Иванов Иван Иванович

📝 *Инструкция:*
1. Переведите сумму *{total:.2f}* руб. на указанную карту
2. В комментарии укажите номер заказа: #{order_id}
3. После оплаты пришлите скриншот чек-экрана в личные сообщения @support
4. Ожидайте подтверждения от менеджера
"""

# Хранилище активных сессий админов
admin_sessions = {}