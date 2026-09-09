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
    get_products_by_category, get_subcategories, get_products_by_subcategory, add_order,
    update_order_status, save_review
)
from cart import (
    get_cart, add_to_cart, remove_from_cart, clear_cart,
    get_cart_total, get_cart_text, save_order_data, get_order_data, clear_order_data
)

# ============================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================
# РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ ПО КАРТЕ
# ============================================
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

# ============================================
# ХРАНИЛИЩЕ
# ============================================
admin_sessions = {}

# ============================================
# ГЛАВНОЕ МЕНЮ
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Каталог", callback_data='catalog')],
        [InlineKeyboardButton("🛒 Корзина", callback_data='view_cart')],
        [InlineKeyboardButton("ℹ️ О магазине", callback_data='about')],
    ]
    
    if user_id in admin_sessions and admin_sessions[user_id]:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data='admin_panel')])
    
    greeting = f"@{username}" if username else "Гость"
    
    await update.message.reply_text(
        f"🛍️ *VapeCity - 24/7*\n\n"
        f"Добро пожаловать, {greeting}!\n"
        f"Здесь вы найдете:\n"
        f"💨 *Вейп-продукцию* (доступно сейчас)\n"
        f"👕 *Одежду* (скоро)\n"
        f"📱 *Технику* (скоро)\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============================================
# ВХОД ДЛЯ АДМИНОВ
# ============================================
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скрытая команда для входа в админ-панель"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав доступа к этой команде.", parse_mode='Markdown')
        return
    
    args = context.args
    if not args:
        admin_info = get_admin_info(user_id)
        role_name = "Владелец" if admin_info['role'] == 'owner' else "Технический администратор"
        await update.message.reply_text(
            f"🔑 *Вход в админ-панель*\n\n"
            f"👤 Ваша роль: *{role_name}*\n"
            f"🆔 Ваш ID: `{user_id}`\n\n"
            f"Использование: `/admin [код_доступа]`\n\n"
            f"Если вы забыли код, обратитесь к владельцу бота.",
            parse_mode='Markdown'
        )
        return
    
    entered_code = args[0]
    
    if check_access_code(user_id, entered_code):
        admin_sessions[user_id] = True
        role = get_admin_role(user_id)
        role_name = "Владелец" if role == 'owner' else "Технический администратор"
        admin_username = get_admin_username(user_id)
        
        await update.message.reply_text(
            f"✅ *Доступ подтвержден!*\n\n"
            f"👤 Вы вошли как: *{role_name}*\n"
            f"🆔 Ваш ID: `{user_id}`\n"
            f"📱 Username: {admin_username}\n\n"
            f"Теперь админ-панель доступна в главном меню.\n"
            f"Для выхода используйте `/admin logout`",
            parse_mode='Markdown'
        )
        logger.info(f"🔐 Администратор {admin_username} ({user_id}) вошел в систему")
        
        if not is_owner(user_id):
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"🔔 *Вход в админ-панель*\n\n"
                    f"👤 Администратор: {admin_username}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить владельца: {e}")
    else:
        await update.message.reply_text(
            "❌ *Неверный код доступа!*",
            parse_mode='Markdown'
        )
        admin_info = get_admin_info(user_id)
        admin_username = admin_info.get('username', str(user_id))
        logger.warning(f"⚠️ Неудачная попытка входа от {admin_username} ({user_id})")

async def admin_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из админ-панели"""
    user_id = update.effective_user.id
    if user_id in admin_sessions:
        del admin_sessions[user_id]
        await update.message.reply_text("👋 *Выход выполнен*", parse_mode='Markdown')
        logger.info(f"🔒 Администратор вышел из системы ({user_id})")

# ============================================
# КОМАНДЫ
# ============================================
async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = get_active_categories()
    if not categories:
        await update.message.reply_text("📭 Каталог пуст.")
        return
    keyboard = []
    for cat in categories:
        emoji = cat['emoji']
        status = " (Скоро)" if not cat['active'] else ""
        keyboard.append([InlineKeyboardButton(f"{emoji} {cat['name']}{status}", callback_data=f'cat_{cat["name"]}')])
    await update.message.reply_text("📦 *Выберите категорию:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart_text = get_cart_text(user_id)
    cart_items = get_cart(user_id)
    if not cart_items:
        await update.message.reply_text(cart_text, parse_mode='Markdown')
        return
    keyboard = []
    for item in cart_items:
        keyboard.append([InlineKeyboardButton(f"❌ Убрать {item['name']} (x{item['quantity']})", callback_data=f'remove_{item["id"]}')])
    keyboard.append([InlineKeyboardButton("🔄 Очистить корзину", callback_data='clear_cart')])
    keyboard.append([InlineKeyboardButton("✅ Оформить заказ", callback_data='checkout')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')])
    await update.message.reply_text(
        cart_text + "\n\nЧто хотите сделать?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    help_text = (
        "🛍️ *VapeCity - 24/7*\n\n"
        "📖 *Доступные команды:*\n"
        "/start - Главное меню\n"
        "/catalog - Каталог товаров\n"
        "/cart - Моя корзина\n"
        "/help - Эта справка\n\n"
        "🛒 *Как сделать заказ:*\n"
        "1. Выберите товары в каталоге\n"
        "2. Добавьте их в корзину\n"
        "3. Оформите заказ\n"
        "4. Укажите адрес и способ оплаты\n\n"
        "📞 *Контакты:*\n"
        "По всем вопросам: @support"
    )
    if is_admin(user_id):
        role = get_admin_role(user_id)
        role_name = "Владелец" if role == 'owner' else "Технический администратор"
        help_text += f"\n\n👑 *Ваша роль:* {role_name}"
        help_text += f"\n🔑 *Пароль:* `{get_admin_code(user_id)}`"
        help_text += f"\n📝 *Вход:* `/admin [пароль]`"
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ============================================
# ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
# ============================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if text.lower() == '/cancel':
        context.user_data['awaiting_address'] = False
        context.user_data['awaiting_review'] = False
        clear_order_data(user_id)
        await update.message.reply_text("❌ Оформление заказа отменено.")
        return
    
    if context.user_data.get('awaiting_address'):
        cart_items = get_cart(user_id)
        if not cart_items:
            await update.message.reply_text("🛒 Корзина пуста.")
            context.user_data['awaiting_address'] = False
            return
        save_order_data(user_id, text, None)
        context.user_data['awaiting_address'] = False
        total = get_cart_total(user_id)
        keyboard = [
            [InlineKeyboardButton("💵 Наличные (при получении)", callback_data='payment_cash')],
            [InlineKeyboardButton("💳 Перевод по карте", callback_data='payment_card')],
            [InlineKeyboardButton("🔙 Назад", callback_data='view_cart')],
        ]
        await update.message.reply_text(
            f"📍 Адрес: {text}\n💰 Сумма: *{total:.2f}* руб.\n\n*Выберите способ оплаты:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    if context.user_data.get('awaiting_review'):
        review_data = context.user_data.get('review_data', {})
        if review_data:
            if text.isdigit() and 1 <= int(text) <= 5:
                return
            user_username = update.effective_user.username
            review_data['comment'] = text
            context.user_data['review_data'] = review_data
            save_review(
                user_id,
                f"@{user_username}" if user_username else str(user_id),
                review_data.get('order_id', 'N/A'),
                review_data.get('product_rating', 0),
                review_data.get('service_rating', 0),
                text
            )
            context.user_data['awaiting_review'] = False
            context.user_data['review_data'] = {}
            await update.message.reply_text(
                "⭐ *Спасибо за ваш отзыв!*\n\n"
                "Ваше мнение очень важно для нас.\n"
                "Возвращайтесь в VapeCity - 24/7! 🚀",
                parse_mode='Markdown'
            )
        return

# ============================================
# ОФОРМЛЕНИЕ ЗАКАЗА
# ============================================
async def process_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    user_id = update.effective_user.id
    cart_items = get_cart(user_id)
    if not cart_items:
        await query.edit_message_text("🛒 Корзина пуста.")
        return
    out_of_stock = []
    for item in cart_items:
        product = get_product_by_id(item['id'])
        if product and not product['in_stock']:
            out_of_stock.append(item['name'])
    if out_of_stock:
        await query.edit_message_text(f"❌ Нет в наличии:\n" + "\n".join(out_of_stock) + "\n\nУдалите их из корзины.")
        return
    context.user_data['awaiting_address'] = True
    await query.edit_message_text("📍 Введите адрес доставки.\nДля отмены: /cancel")

async def process_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, query, payment_method):
    user_id = update.effective_user.id
    order_data = get_order_data(user_id)
    if not order_data.get('address'):
        await query.edit_message_text("❌ Ошибка: не указан адрес.")
        return
    save_order_data(user_id, order_data['address'], payment_method)
    if payment_method == 'cash':
        await process_cash_order(update, query, user_id)
    elif payment_method == 'card':
        await process_card_order(update, query, user_id)

async def process_cash_order(update, query, user_id):
    cart_items = get_cart(user_id)
    total = get_cart_total(user_id)
    order_data = get_order_data(user_id)
    username = update.effective_user.username
    
    order = {
        'user_id': user_id,
        'username': f"@{username}" if username else str(user_id),
        'items': cart_items.copy(),
        'total': total,
        'address': order_data.get('address', ''),
        'status': 'Ожидает оплаты (наличные)'
    }
    
    order_row = add_order(order)
    clear_cart(user_id)
    clear_order_data(user_id)
    context.user_data['awaiting_address'] = False
    
    await query.edit_message_text(
        f"✅ *Заказ оформлен!*\n\n"
        f"📍 Адрес: {order['address']}\n"
        f"💰 Сумма: *{total:.2f}* руб.\n"
        f"💳 Оплата: *Наличные (при получении)*\n\n"
        f"📦 Ожидайте доставку.\n"
        f"Спасибо за покупку! 🎉",
        parse_mode='Markdown'
    )
    await notify_admins(context, order, 'наличные', order_row)

async def process_card_order(update, query, user_id):
    cart_items = get_cart(user_id)
    total = get_cart_total(user_id)
    order_data = get_order_data(user_id)
    username = update.effective_user.username
    order_id = f"{user_id % 10000}{int(time.time()) % 10000}"
    payment_text = PAYMENT_DETAILS.format(total=total, order_id=order_id)
    
    order = {
        'user_id': user_id,
        'username': f"@{username}" if username else str(user_id),
        'items': cart_items.copy(),
        'total': total,
        'address': order_data.get('address', ''),
        'status': 'Ожидает оплаты (карта)'
    }
    
    order_row = add_order(order)
    clear_cart(user_id)
    clear_order_data(user_id)
    context.user_data['awaiting_address'] = False
    
    await query.edit_message_text(
        f"✅ *Заказ оформлен!*\n\n"
        f"📍 Адрес: {order['address']}\n"
        f"💰 Сумма: *{total:.2f}* руб.\n"
        f"💳 Оплата: *Перевод по карте*\n"
        f"🆔 Заказ: #{order_id}\n\n"
        f"{payment_text}\n\n"
        f"⚠️ Заказ отправится после подтверждения оплаты.\n"
        f"Спасибо за покупку! 🎉",
        parse_mode='Markdown'
    )
    await notify_admins(context, order, 'карта', order_row, order_id)

async def notify_admins(context, order, payment_type, order_row, order_id=None):
    items_text = "\n".join([f"• {item['name']} x{item['quantity']} = {item['price'] * item['quantity']:.2f} руб." for item in order['items']])
    order_info = (
        f"🆕 *Новый заказ!*\n\n"
        f"👤 {order['username']}\n"
        f"📍 {order['address']}\n"
        f"💰 {order['total']:.2f} руб.\n"
        f"💳 {payment_type}\n"
        f"📦 Строка: #{order_row}"
    )
    if order_id:
        order_info += f"\n🆔 Номер: #{order_id}"
    order_info += f"\n\n*Товары:*\n{items_text}"
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, order_info, parse_mode='Markdown')
            keyboard = [
                [InlineKeyboardButton("📦 Отметить доставленным", callback_data=f'deliver_{order["user_id"]}_{order_row}')],
            ]
            await context.bot.send_message(
                admin_id,
                "Дей
