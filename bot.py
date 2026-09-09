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
                "Действия с заказом:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")

# ============================================
# ПОДТВЕРЖДЕНИЕ ДОСТАВКИ И ОТЗЫВЫ
# ============================================
async def deliver_order(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id, order_row):
    admin_id = update.effective_user.id
    if not is_admin(admin_id):
        await query.edit_message_text("⛔ У вас нет прав.")
        return
    update_order_status(int(order_row), 'Доставлен')
    try:
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить получение", callback_data=f'confirm_{user_id}_{order_row}')]
        ]
        await context.bot.send_message(
            user_id,
            f"📦 *Ваш заказ доставлен!*\n\nПожалуйста, подтвердите получение товара.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        await query.edit_message_text("✅ Пользователь уведомлен о доставке.")
        logger.info(f"📦 Заказ #{order_row} доставлен пользователю {user_id}")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def confirm_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id, order_row):
    current_user = update.effective_user.id
    if current_user != int(user_id):
        await query.edit_message_text("⛔ Это не ваш заказ.")
        return
    update_order_status(int(order_row), 'Подтвержден получение')
    keyboard = [
        [InlineKeyboardButton("⭐ Оценить товар", callback_data=f'rate_product_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ Оценить сервис", callback_data=f'rate_service_{user_id}_{order_row}')],
        [InlineKeyboardButton("✏️ Написать комментарий", callback_data=f'comment_{user_id}_{order_row}')],
        [InlineKeyboardButton("⏭️ Пропустить", callback_data=f'skip_review_{user_id}_{order_row}')],
    ]
    await query.edit_message_text(
        f"✅ *Получение подтверждено!*\n\nСпасибо, что выбрали VapeCity!\n\n*Оцените наш сервис:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    context.user_data['review_data'] = {'user_id': user_id, 'order_id': order_row}
    context.user_data['awaiting_review'] = True
    logger.info(f"✅ Пользователь {user_id} подтвердил получение заказа #{order_row}")

async def rate_product(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id, order_row):
    current_user = update.effective_user.id
    if current_user != int(user_id):
        await query.edit_message_text("⛔ Это не ваш заказ.")
        return
    keyboard = [
        [InlineKeyboardButton("⭐ 1", callback_data=f'product_rate_1_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 2", callback_data=f'product_rate_2_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 3", callback_data=f'product_rate_3_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 4", callback_data=f'product_rate_4_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 5", callback_data=f'product_rate_5_{user_id}_{order_row}')],
    ]
    await query.edit_message_text(
        "⭐ *Оцените качество товара:*\n\n1 - Очень плохо\n5 - Отлично",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def rate_service(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id, order_row):
    current_user = update.effective_user.id
    if current_user != int(user_id):
        await query.edit_message_text("⛔ Это не ваш заказ.")
        return
    keyboard = [
        [InlineKeyboardButton("⭐ 1", callback_data=f'service_rate_1_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 2", callback_data=f'service_rate_2_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 3", callback_data=f'service_rate_3_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 4", callback_data=f'service_rate_4_{user_id}_{order_row}')],
        [InlineKeyboardButton("⭐ 5", callback_data=f'service_rate_5_{user_id}_{order_row}')],
    ]
    await query.edit_message_text(
        "⭐ *Оцените качество сервиса:*\n\n1 - Очень плохо\n5 - Отлично",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def process_rating(update: Update, context: ContextTypes.DEFAULT_TYPE, query, rating_type, value, user_id, order_row):
    current_user = update.effective_user.id
    if current_user != int(user_id):
        await query.edit_message_text("⛔ Это не ваш заказ.")
        return
    review_data = context.user_data.get('review_data', {})
    if rating_type == 'product':
        review_data['product_rating'] = int(value)
        await query.edit_message_text(f"✅ Оценка товара: {value} ⭐")
    elif rating_type == 'service':
        review_data['service_rating'] = int(value)
        await query.edit_message_text(f"✅ Оценка сервиса: {value} ⭐")
    context.user_data['review_data'] = review_data
    if review_data.get('product_rating') and review_data.get('service_rating'):
        keyboard = [
            [InlineKeyboardButton("✏️ Написать комментарий", callback_data=f'comment_{user_id}_{order_row}')],
            [InlineKeyboardButton("⏭️ Пропустить", callback_data=f'skip_review_{user_id}_{order_row}')],
        ]
        await query.edit_message_text(
            "✏️ *Хотите оставить комментарий?*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def skip_review(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id, order_row):
    current_user = update.effective_user.id
    if current_user != int(user_id):
        await query.edit_message_text("⛔ Это не ваш заказ.")
        return
    review_data = context.user_data.get('review_data', {})
    save_review(
        user_id,
        f"@{update.effective_user.username}" if update.effective_user.username else str(user_id),
        order_row,
        review_data.get('product_rating', 0),
        review_data.get('service_rating', 0),
        ''
    )
    context.user_data['awaiting_review'] = False
    context.user_data['review_data'] = {}
    await query.edit_message_text(
        "⭐ *Спасибо!*\n\nВаше мнение очень важно для нас.\nВозвращайтесь в VapeCity - 24/7! 🚀",
        parse_mode='Markdown'
    )

async def comment_review(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id, order_row):
    current_user = update.effective_user.id
    if current_user != int(user_id):
        await query.edit_message_text("⛔ Это не ваш заказ.")
        return
    await query.edit_message_text(
        "✏️ *Напишите ваш комментарий:*\n\n"
        "Поделитесь впечатлениями о товаре и сервисе.",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_review'] = True

# ============================================
# АДМИН-ПАНЕЛЬ
# ============================================
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    user_id = update.effective_user.id
    if user_id not in admin_sessions or not admin_sessions[user_id]:
        await query.edit_message_text("🔑 *Доступ запрещен*\n\nДля доступа используйте `/admin [код]`", parse_mode='Markdown')
        return
    role = get_admin_role(user_id)
    role_name = "Владелец" if role == 'owner' else "Технический администратор"
    keyboard = [
        [InlineKeyboardButton("📦 Управление товарами", callback_data='admin_products')],
        [InlineKeyboardButton("📊 Просмотр заказов", callback_data='admin_orders')],
        [InlineKeyboardButton("📈 Статистика", callback_data='admin_stats')],
    ]
    if is_owner(user_id):
        keyboard.append([InlineKeyboardButton("👥 Управление админами", callback_data='admin_users')])
        keyboard.append([InlineKeyboardButton("⚙️ Настройки бота", callback_data='admin_settings')])
    keyboard.append([InlineKeyboardButton("🚪 Выйти", callback_data='admin_logout')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')])
    await query.edit_message_text(
        f"⚙️ *Админ-панель*\n\n👤 *{role_name}*\n🆔 `{user_id}`\n🔐 Сессия активна\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    user_id = update.effective_user.id
    if user_id not in admin_sessions or not admin_sessions[user_id]:
        await query.edit_message_text("🔑 Пожалуйста, авторизуйтесь.")
        return
    keyboard = [
        [InlineKeyboardButton("➕ Добавить товар", callback_data='admin_add_product')],
        [InlineKeyboardButton("✏️ Редактировать товар", callback_data='admin_edit_product')],
        [InlineKeyboardButton("🗑️ Удалить товар", callback_data='admin_delete_product')],
        [InlineKeyboardButton("📋 Список товаров", callback_data='admin_list_products')],
        [InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')],
    ]
    await query.edit_message_text("📦 *Управление товарами*\n\nВыберите действие:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    user_id = update.effective_user.id
    if user_id not in admin_sessions or not admin_sessions[user_id]:
        await query.edit_message_text("🔑 Пожалуйста, авторизуйтесь.")
        return
    keyboard = [
        [InlineKeyboardButton("📋 Все заказы", callback_data='admin_list_orders')],
        [InlineKeyboardButton("🆕 Новые заказы", callback_data='admin_new_orders')],
        [InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')],
    ]
    await query.edit_message_text("📊 *Управление заказами*\n\nВыберите статус:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    user_id = update.effective_user.id
    if user_id not in admin_sessions or not admin_sessions[user_id]:
        await query.edit_message_text("🔑 Пожалуйста, авторизуйтесь.")
        return
    stats_text = """
📈 *Статистика магазина*

👥 Всего клиентов: 0
📦 Всего заказов: 0
💰 Общая выручка: 0.00 руб.
📊 Средний чек: 0.00 руб.
"""
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data='admin_stats')], [InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')]]
    await query.edit_message_text(stats_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await query.edit_message_text("⛔ Только для владельца.")
        return
    admins_list = ""
    for uid, info in ADMIN_ACCESS.items():
        role_name = "👑 Владелец" if info['role'] == 'owner' else "🛠️ Технический администратор"
        admins_list += f"• `{uid}` - {role_name}\n  Пароль: `{info['code']}`\n"
    keyboard = [
        [InlineKeyboardButton("➕ Добавить админа", callback_data='admin_add_user')],
        [InlineKeyboardButton("🗑️ Удалить админа", callback_data='admin_remove_user')],
        [InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')],
    ]
    await query.edit_message_text(f"👥 *Управление админами*\n\n{admins_list}\n\nВыберите действие:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============================================
# ГЛАВНЫЙ ОБРАБОТЧИК КНОПОК
# ============================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    # Каталог
    if data == 'catalog':
        categories = get_active_categories()
        if not categories:
            await query.edit_message_text("📭 Каталог пуст.")
            return
        keyboard = []
        for cat in categories:
            emoji = cat['emoji']
            status = " (Скоро)" if not cat['active'] else ""
            keyboard.append([InlineKeyboardButton(f"{emoji} {cat['name']}{status}", callback_data=f'cat_{cat["name"]}')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')])
        await query.edit_message_text("📦 *Выберите категорию:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data.startswith('cat_'):
        category = data[4:]
        products = get_products_by_category(category)
        if not products:
            await query.edit_message_text(f"❌ В категории '{category}' нет товаров.")
            return
        keyboard = []
        for p in products:
            status = "✅" if p['in_stock'] else "❌"
            keyboard.append([InlineKeyboardButton(f"{p['name']} - {p['price']:.2f} руб. {status}", callback_data=f'product_{p["id"]}')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='catalog')])
        await query.edit_message_text(f"📦 *{category}*\n\nВыберите товар:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data.startswith('product_'):
        product_id = data[8:]
        product = get_product_by_id(product_id)
        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return
        text = f"*{product['name']}*\n\n💰 Цена: *{product['price']:.2f}* руб.\n📂 Категория: {product['category']}\n"
        if product['description']:
            text += f"📝 {product['description']}\n"
        text += f"📦 В наличии: {'✅ Да' if product['in_stock'] else '❌ Нет'}"
        keyboard = []
        if product['in_stock']:
            keyboard.append([InlineKeyboardButton("➕ Добавить в корзину", callback_data=f'add_{product_id}')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'cat_{product["category"]}')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # Корзина
    elif data.startswith('add_'):
        product_id = data[4:]
        product = get_product_by_id(product_id)
        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return
        add_to_cart(user_id, product)
        total = get_cart_total(user_id)
        await query.edit_message_text(f"✅ *{product['name']}* добавлен!\n💰 Сумма: *{total:.2f}* руб.", parse_mode='Markdown')
    
    elif data == 'view_cart':
        cart_text = get_cart_text(user_id)
        cart_items = get_cart(user_id)
        if not cart_items:
            await query.edit_message_text(cart_text, parse_mode='Markdown')
            return
        keyboard = []
        for item in cart_items:
            keyboard.append([InlineKeyboardButton(f"❌ Убрать {item['name']} (x{item['quantity']})", callback_data=f'remove_{item["id"]}')])
        keyboard.append([InlineKeyboardButton("🔄 Очистить корзину", callback_data='clear_cart')])
        keyboard.append([InlineKeyboardButton("✅ Оформить заказ", callback_data='checkout')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')])
        await query.edit_message_text(cart_text + "\n\nЧто хотите сделать?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data.startswith('remove_'):
        product_id = data[7:]
        remove_from_cart(user_id, product_id)
        cart_text = get_cart_text(user_id)
        if not get_cart(user_id):
            await query.edit_message_text("🛒 Корзина пуста.", parse_mode='Markdown')
            return
        keyboard = query.message.reply_markup
        await query.edit_message_text(cart_text + "\n\nЧто хотите сделать?", reply_markup=keyboard, parse_mode='Markdown')
    
    elif data == 'clear_cart':
        clear_cart(user_id)
        await query.edit_message_text("🛒 Корзина очищена.", parse_mode='Markdown')
    
    elif data == 'checkout':
        await process_checkout(update, context, query)
    
    elif data.startswith('payment_'):
        payment_method = data[8:]
        await process_payment_selection(update, context, query, payment_method)
    
    # О магазине
    elif data == 'about':
        await query.edit_message_text(
            "ℹ️ *О магазине VapeCity - 24/7*\n\n"
            "🛍️ Надежный поставщик вейп-продукции.\n\n"
            "📦 *Что мы предлагаем:*\n"
            "• 💨 Вейпы и жидкости\n"
            "• 👕 Одежда (скоро)\n"
            "• 📱 Техника (скоро)\n\n"
            "⏰ *Круглосуточно!*\n\n"
            "📞 *Контакты:* @support",
            parse_mode='Markdown'
        )
    
    # Админ-панель
    elif data == 'admin_panel':
        await show_admin_panel(update, context, query)
    
    elif data == 'admin_products':
        await admin_products(update, context, query)
    
    elif data == 'admin_orders':
        await admin_orders(update, context, query)
    
    elif data == 'admin_stats':
        await admin_stats(update, context, query)
    
    elif data == 'admin_users':
        await admin_users(update, context, query)
    
    elif data == 'admin_logout':
        if user_id in admin_sessions:
            del admin_sessions[user_id]
            await query.edit_message_text("👋 *Выход выполнен*", parse_mode='Markdown')
            logger.info(f"🔒 Администратор вышел ({user_id})")
    
    # Доставка и отзывы
    elif data.startswith('deliver_'):
        parts = data.split('_')
        if len(parts) >= 3:
            await deliver_order(update, context, query, parts[1], parts[2])
    
    elif data.startswith('confirm_'):
        parts = data.split('_')
        if len(parts) >= 3:
            await confirm_receipt(update, context, query, parts[1], parts[2])
    
    elif data.startswith('rate_product_'):
        parts = data.split('_')
        if len(parts) >= 4:
            await rate_product(update, context, query, parts[2], parts[3])
    
    elif data.startswith('rate_service_'):
        parts = data.split('_')
        if len(parts) >= 4:
            await rate_service(update, context, query, parts[2], parts[3])
    
    elif data.startswith('product_rate_'):
        parts = data.split('_')
        if len(parts) >= 5:
            await process_rating(update, context, query, 'product', parts[3], parts[4], parts[5])
    
    elif data.startswith('service_rate_'):
        parts = data.split('_')
        if len(parts) >= 5:
            await process_rating(update, context, query, 'service', parts[3], parts[4], parts[5])
    
    elif data.startswith('skip_review_'):
        parts = data.split('_')
        if len(parts) >= 4:
            await skip_review(update, context, query, parts[2], parts[3])
    
    elif data.startswith('comment_'):
        parts = data.split('_')
        if len(parts) >= 4:
            await comment_review(update, context, query, parts[1], parts[2])
    
    elif data == 'back_to_menu':
        await start(update, context)

# ============================================
# ЗАПУСК БОТА
# ============================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('catalog', catalog_command))
    app.add_handler(CommandHandler('cart', cart_command))
    
    # Скрытые команды для админов
    app.add_handler(CommandHandler('admin', admin_login))
    app.add_handler(CommandHandler('adminlogout', admin_logout))
    
    # Обработчики
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот VapeCity запущен!")
    logger.info(f"👑 Владелец: @voloki4 (ID: {OWNER_ID})")
    logger.info(f"🛠️ Технический администратор: @myhzxc (ID: {TECH_ADMIN_ID})")
    logger.info(f"👥 Всего администраторов: {len(ADMIN_ACCESS)}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
