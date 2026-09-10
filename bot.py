import logging
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import (
    BOT_TOKEN, ADMIN_ACCESS, ADMIN_IDS, OWNER_ID, TECH_ADMIN_ID,
    is_admin, is_owner, get_admin_role, get_admin_code, get_admin_username, check_access_code,
    get_admin_info
)
from google_sheets import (
    get_all_products, get_product_by_id, get_active_categories,
    get_products_by_category, add_order,
    update_order_status, save_review,
    decrease_product_quantity,
    add_product_to_sheet
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
# 📸 ВСЕ ФОТОГРАФИИ БОТА
# ============================================
PHOTOS = {
    'start': 'https://i.ibb.co/fz9MMDdc/image.jpg',
    'catalog': 'https://i.ibb.co/Wp66WKzF/image.jpg',
    'cart': 'https://i.ibb.co/s9hmqnYQ/image.jpg',
    'payment': 'https://i.ibb.co/PsjnpMSz/image.jpg',
    'admin': 'https://i.ibb.co/7Jwchtyn/image.jpg',
}

CATEGORY_PHOTOS = {
    'Вейп': 'https://i.ibb.co/Jjkzb11W/image.jpg',
    'Одежда': 'https://i.ibb.co/SwB21cDP/image.jpg',
    'Техника': 'https://i.ibb.co/BYT9v1n/image.jpg',
}

# ============================================
# РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ ПО КАРТЕ
# ============================================
PAYMENT_DETAILS = """
💳 *Оплата по карте*

🏦 Банк: Альфа-Банк
📱 Номер карты: +7 901 659 30 98
👤 Получатель: Артём Николаевич И.

📝 *Инструкция:*
1. Переведите сумму *{total:.2f}* руб. на указанный номер карты
2. В комментарии укажите номер заказа: #{order_id}
3. После перевода **сохраните чек** (скриншот или фото)

📸 *Чек нужно сохранить!*
Если оплата вдруг не будет видна, чек останется подтверждением вашей оплаты.
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
    
    text = (
        f"✨ *VAPE CITY*\n"
        f"Тёплый маркетплейс в холодный сезон.\n"
        f"Оформляйте заказы через бота — быстро, уютно, без лишних движений.\n\n"
        f"🍂 @{username if username else 'Гость'}, мы рады видеть вас снова!\n"
        f"Осень — время новых вкусов и тёплых покупок.\n\n"
        f"💜 *Уже в каталоге*\n"
        f"Вейп-продукция — вся палитра осенних настроений.\n"
        f"Выбирайте и заказывайте с комфортом.\n\n"
        f"🌙 *Скоро появится*\n"
        f"Одежда · Техника\n"
        f"Следите за обновлениями — мы готовим что-то особенное.\n\n"
        f"Выберите раздел ниже и окунитесь в уютный шопинг 🍁💜"
    )
    
    keyboard = [
        [KeyboardButton("🛍️ Каталог"), KeyboardButton("🛒 Корзина")],
        [KeyboardButton("ℹ️ О магазине"), KeyboardButton("📋 Мои заказы")],
    ]
    
    if user_id in admin_sessions and admin_sessions[user_id]:
        keyboard.append([KeyboardButton("⚙️ Админ-панель")])
    
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    await update.message.reply_photo(
        photo=PHOTOS['start'],
        caption=text,
        reply_markup=reply_markup,
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
            f"Теперь админ-панель доступна в меню.\n"
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
# КАТАЛОГ
# ============================================
async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = get_active_categories()
    if not categories:
        await update.message.reply_text("📭 Каталог пуст.")
        return
    
    text = "📦 *Каталог VapeCity*\n\nВыберите категорию:\n\n"
    for cat in categories:
        status = "✅" if cat['active'] else "⏳"
        text += f"{cat['emoji']} *{cat['name']}* {status}\n"
    text += "\n⬇️ Нажмите на категорию ниже:"
    
    keyboard = []
    for cat in categories:
        emoji = cat['emoji']
        status = " (Скоро)" if not cat['active'] else ""
        keyboard.append([InlineKeyboardButton(f"{emoji} {cat['name']}{status}", callback_data=f'cat_{cat["name"]}')])
    
    await update.message.reply_photo(
        photo=PHOTOS['catalog'],
        caption=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============================================
# КОРЗИНА
# ============================================
async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart_text = get_cart_text(user_id)
    cart_items = get_cart(user_id)
    
    if not cart_items:
        await update.message.reply_photo(
            photo=PHOTOS['cart'],
            caption=cart_text + "\n\n🛍️ Добавьте товары из каталога!",
            parse_mode='Markdown'
        )
        return
    
    keyboard = []
    for item in cart_items:
        keyboard.append([InlineKeyboardButton(
            f"❌ Убрать {item['name']} (x{item['quantity']})", 
            callback_data=f'remove_{item["id"]}'
        )])
    keyboard.append([InlineKeyboardButton("🔄 Очистить корзину", callback_data='clear_cart')])
    keyboard.append([InlineKeyboardButton("✅ Оформить заказ", callback_data='checkout')])
    
    await update.message.reply_photo(
        photo=PHOTOS['cart'],
        caption=cart_text + "\n\nЧто хотите сделать?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============================================
# HELP
# ============================================
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
        "4. Укажите адрес и способ оплаты"
    )
    if is_admin(user_id):
        role = get_admin_role(user_id)
        role_name = "Владелец" if role == 'owner' else "Технический администратор"
        help_text += f"\n\n👑 *Ваша роль:* {role_name}"
        help_text += f"\n🔑 *Пароль:* `{get_admin_code(user_id)}`"
        help_text += f"\n📝 *Вход:* `/admin [пароль]`"
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ============================================
# О МАГАЗИНЕ
# ============================================
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *О магазине VapeCity - 24/7*\n\n"
        "🛍️ Мы - ваш надежный поставщик вейп-продукции.\n\n"
        "📦 *Что мы предлагаем:*\n"
        "  • 💨 Вейпы и жидкости\n"
        "  • 👕 Одежда (скоро)\n"
        "  • 📱 Техника (скоро)\n\n"
        "⏰ *Режим работы:* Круглосуточно!"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

# ============================================
# МОИ ЗАКАЗЫ
# ============================================
async def my_orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *История ваших заказов*\n\n"
        "📦 У вас пока нет заказов.\n\n"
        "🛍️ Перейдите в каталог, чтобы сделать первый заказ!"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

# ============================================
# ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
# ============================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # ===== ДОБАВЛЕНИЕ ТОВАРА =====
    if context.user_data.get('adding_product'):
        step = context.user_data.get('adding_step')
        
        if step == 'name':
            context.user_data['new_product_name'] = text
            context.user_data['adding_step'] = 'price'
            await update.message.reply_text(
                f"✅ Название: *{text}*\n\n"
                f"💰 Введите *цену* товара (в рублях):\n"
                f"Пример: `1200.50`\n\n"
                f"Для отмены: /cancel",
                parse_mode='Markdown'
            )
            return
        
        elif step == 'price':
            try:
                price = float(text.replace(',', '.'))
                context.user_data['new_product_price'] = price
                context.user_data['adding_step'] = 'quantity'
                await update.message.reply_text(
                    f"✅ Цена: *{price:.2f}* руб.\n\n"
                    f"📦 Введите *количество* товара:\n"
                    f"Пример: `10`\n\n"
                    f"Для отмены: /cancel",
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат цены.\n"
                    "Введите число, например: `1200.50`",
                    parse_mode='Markdown'
                )
            return
        
        elif step == 'quantity':
            try:
                quantity = int(text)
                name = context.user_data.get('new_product_name')
                price = context.user_data.get('new_product_price')
                
                row = add_product_to_sheet(name, price, quantity)
                
                if row:
                    context.user_data['adding_product'] = False
                    context.user_data['adding_step'] = None
                    context.user_data.pop('new_product_name', None)
                    context.user_data.pop('new_product_price', None)
                    
                    await update.message.reply_text(
                        f"✅ *Товар добавлен!*\n\n"
                        f"📦 Название: *{name}*\n"
                        f"💰 Цена: *{price:.2f}* руб.\n"
                        f"🔢 Количество: *{quantity}* шт.\n"
                        f"💵 Сумма: *{price * quantity:.2f}* руб.\n\n"
                        f"Товар появился в каталоге! 🎉",
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Админ {user_id} добавил товар: {name}")
                else:
                    await update.message.reply_text("❌ Ошибка добавления товара.")
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат количества.\n"
                    "Введите целое число, например: `10`",
                    parse_mode='Markdown'
                )
            return
    
    # ===== КНОПКИ МЕНЮ =====
    if text == "🛍️ Каталог":
        await catalog_command(update, context)
        return
    elif text == "🛒 Корзина":
        await cart_command(update, context)
        return
    elif text == "ℹ️ О магазине":
        await about_command(update, context)
        return
    elif text == "📋 Мои заказы":
        await my_orders_command(update, context)
        return
    elif text == "⚙️ Админ-панель":
        if user_id in admin_sessions and admin_sessions[user_id]:
            keyboard = [
                [InlineKeyboardButton("📦 Управление товарами", callback_data='admin_products')],
                [InlineKeyboardButton("📊 Просмотр заказов", callback_data='admin_orders')],
                [InlineKeyboardButton("📈 Статистика", callback_data='admin_stats')],
                [InlineKeyboardButton("🚪 Выйти", callback_data='admin_logout')],
            ]
            await update.message.reply_photo(
                photo=PHOTOS['admin'],
                caption="⚙️ *Админ-панель*\n\nВыберите действие:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "🔑 *Доступ запрещен*\n\nДля входа используйте:\n`/admin [пароль]`",
                parse_mode='Markdown'
            )
        return
    
    # ===== ОТМЕНА =====
    if text.lower() == '/cancel':
        context.user_data['awaiting_address'] = False
        context.user_data['awaiting_review'] = False
        context.user_data['adding_product'] = False
        context.user_data['adding_step'] = None
        context.user_data.pop('new_product_name', None)
        context.user_data.pop('new_product_price', None)
        clear_order_data(user_id)
        await update.message.reply_text("❌ Действие отменено.")
        return
    
    # ===== АДРЕС =====
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
        ]
        
        await update.message.reply_photo(
            photo=PHOTOS['payment'],
            caption=f"📍 Адрес: {text}\n💰 Сумма: *{total:.2f}* руб.\n\n*Выберите способ оплаты:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # ===== ОТЗЫВ =====
    if context.user_data.get('awaiting_review'):
        review_data = context.user_data.get('review_data', {})
        if review_data:
            if text.isdigit() and 1 <= int(text) <= 5:
                return
            user_username = update.effective_user.username
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
        await query.edit_message_text(
            f"❌ Нет в наличии:\n" + "\n".join(out_of_stock) + "\n\nУдалите их из корзины."
        )
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
    
    # СПИСЫВАЕМ ТОВАРЫ
    for item in cart_items:
        if item.get('row'):
            decrease_product_quantity(item['row'], item['quantity'])
            logger.info(f"📦 Списано: {item['name']} x{item['quantity']}")
    
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
    
    # СПИСЫВАЕМ ТОВАРЫ
    for item in cart_items:
        if item.get('row'):
            decrease_product_quantity(item['row'], item['quantity'])
            logger.info(f"📦 Списано: {item['name']} x{item['quantity']}")
    
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
    
    await query.message.reply_photo(
        photo=PHOTOS['payment'],
        caption=(
            f"✅ *Заказ оформлен!*\n\n"
            f"📍 Адрес: {order['address']}\n"
            f"💰 Сумма: *{total:.2f}* руб.\n"
            f"💳 Оплата: *Перевод по карте*\n"
            f"🆔 Заказ: #{order_id}\n\n"
            f"{payment_text}\n\n"
            f"⚠️ Заказ отправится после подтверждения оплаты.\n"
            f"Спасибо за покупку! 🎉"
        ),
        parse_mode='Markdown'
    )
    await query.message.delete()
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
# ПОДТВЕРЖДЕНИЕ ДОСТАВКИ
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

async def rate_product(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id, order_row):
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

# ============================================
# ГЛАВНЫЙ ОБРАБОТЧИК КНОПОК
# ============================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    # ===== КАТАЛОГ =====
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
        await query.edit_message_text("📦 *Выберите категорию:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data.startswith('cat_'):
        category = data[4:]
        products = get_products_by_category(category)
        if not products:
            await query.edit_message_text(f"❌ В категории '{category}' нет товаров.")
            return
        keyboard = []
        for p in products:
            if p['in_stock'] and p['quantity'] > 0:
                status = f"✅ {p['quantity']} шт."
            else:
                status = "❌ Нет"
            keyboard.append([InlineKeyboardButton(f"{p['name']} - {p['price']:.2f} руб. {status}", callback_data=f'product_{p["id"]}')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='catalog')])
        await query.edit_message_text(f"📦 *{category}*\n\nВыберите товар:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data.startswith('product_'):
        product_id = data[8:]
        product = get_product_by_id(product_id)
        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return
        text = f"*{product['name']}*\n\n💰 Цена: *{product['price']:.2f}* руб.\n"
        if product['in_stock'] and product['quantity'] > 0:
            text += f"📦 В наличии: ✅ Да\n🔢 Осталось: *{product['quantity']}* шт.\n"
        else:
            text += f"📦 В наличии: ❌ Нет\n"
        keyboard = []
        if product['in_stock'] and product['quantity'] > 0:
            keyboard.append([InlineKeyboardButton("➕ Добавить в корзину", callback_data=f'add_{product_id}')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'cat_{product["category"]}')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # ===== КОРЗИНА =====
    elif data.startswith('add_'):
        product_id = data[4:]
        product = get_product_by_id(product_id)
        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return
        
        if not product['in_stock'] or product['quantity'] <= 0:
            await query.edit_message_text(f"❌ *Товар закончился!*\n\n*{product['name']}* временно недоступен.", parse_mode='Markdown')
            return
        
        cart = get_cart(user_id)
        current_in_cart = 0
        for item in cart:
            if item['id'] == product_id:
                current_in_cart = item['quantity']
                break
        
        if current_in_cart >= product['quantity']:
            await query.edit_message_text(
                f"⚠️ *Максимум!*\n\nВ наличии только *{product['quantity']}* шт.\nУ вас уже {current_in_cart} шт. в корзине.",
                parse_mode='Markdown'
            )
            return
        
        add_to_cart(user_id, product)
        total = get_cart_total(user_id)
        await query.edit_message_text(
            f"✅ *{product['name']}* добавлен!\n💰 Сумма: *{total:.2f}* руб.\n🔢 Осталось: *{product['quantity'] - current_in_cart - 1}* шт.",
            parse_mode='Markdown'
        )
    
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
    
    # ===== АДМИН-ПАНЕЛЬ =====
    elif data == 'admin_panel':
        await show_admin_panel(update, context, query)
    
    elif data == 'admin_products':
        await admin_products(update, context, query)
    
    elif data == 'admin_orders':
        await admin_orders(update, context, query)
    
    elif data == 'admin_stats':
        await admin_stats(update, context, query)
    
    elif data == 'admin_add_product':
        if user_id not in admin_sessions or not admin_sessions[user_id]:
            await query.edit_message_text("🔑 Пожалуйста, авторизуйтесь.")
            return
        context.user_data['adding_product'] = True
        context.user_data['adding_step'] = 'name'
        await query.edit_message_text(
            "➕ *Добавление товара*\n\n📦 Шаг 1/3: Введите *название* товара\n\nПример: `Хаски Под`\n\nДля отмены: /cancel",
            parse_mode='Markdown'
        )
    
    elif data == 'admin_logout':
        if user_id in admin_sessions:
            del admin_sessions[user_id]
            await query.edit_message_text("👋 *Выход выполнен*", parse_mode='Markdown')
    
    # ===== ДОСТАВКА И ОТЗЫВЫ =====
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

# ============================================
# ЗАПУСК БОТА
# ============================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('catalog', catalog_command))
    app.add_handler(CommandHandler('cart', cart_command))
    app.add_handler(CommandHandler('admin', admin_login))
    app.add_handler(CommandHandler('adminlogout', admin_logout))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот VapeCity запущен!")
    logger.info(f"👑 Владелец: @voloki4 (ID: {OWNER_ID})")
    logger.info(f"🛠️ Технический администратор: @myhzxc (ID: {TECH_ADMIN_ID})")
    logger.info(f"👥 Всего администраторов: {len(ADMIN_ACCESS)}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
