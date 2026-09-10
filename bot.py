import logging
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
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
    decrease_product_quantity, add_product_to_sheet,
    get_user_orders, get_orders_sheet
)
from cart import (
    get_cart, add_to_cart, remove_from_cart, clear_cart,
    get_cart_total, get_cart_text, save_order_data, get_order_data, clear_order_data,
    has_user_consented, save_user_consent, change_cart_quantity
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PHOTOS = {
    'start': 'https://i.ibb.co/fz9MMDdc/image.jpg',
    'catalog': 'https://i.ibb.co/Wp66WKzF/image.jpg',
    'cart': 'https://i.ibb.co/s9hmqnYQ/image.jpg',
    'payment': 'https://i.ibb.co/PsjnpMSz/image.jpg',
    'admin': 'https://i.ibb.co/7Jwchtyn/image.jpg',
    'age_warning': 'https://i.ibb.co/fz9MMDdc/image.jpg',
}

BRATSK_TZ = ZoneInfo("Asia/Irkutsk")
NIGHT_START = dt_time(21, 0)
NIGHT_END = dt_time(9, 0)
DELIVERY_PRICE = 250  # ← ИЗМЕНЕНО НА 250


def get_bratsk_time():
    return datetime.now(BRATSK_TZ)


def is_night_delivery():
    now = get_bratsk_time()
    current_time = now.time()
    return current_time >= NIGHT_START or current_time < NIGHT_END


def get_delivery_info():
    now = get_bratsk_time()
    is_night = is_night_delivery()
    
    if is_night:
        return {
            'is_night': True,
            'price': DELIVERY_PRICE,
            'time': now.strftime('%H:%M'),
            'message': f"🌙 *Ночная доставка*\n\n"
                       f"🕐 Время в Братске: *{now.strftime('%H:%M')}*\n"
                       f"💰 Стоимость доставки: *{DELIVERY_PRICE}* руб.\n\n"
                       f"Доставка с 21:00 до 09:00 — платная."
        }
    else:
        return {
            'is_night': False,
            'price': 0,
            'time': now.strftime('%H:%M'),
            'message': f"☀️ *Дневная доставка*\n\n"
                       f"🕐 Время в Братске: *{now.strftime('%H:%M')}*\n"
                       f"💰 Доставка: *Бесплатно*\n\n"
                       f"Доставка с 09:00 до 21:00 — бесплатная."
        }


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

admin_sessions = {}


async def safe_edit(query, text, reply_markup=None, parse_mode='Markdown'):
    try:
        if query.message.photo:
            await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not has_user_consented(user_id):
        keyboard = [
            [InlineKeyboardButton("✅ Мне есть 18 лет", callback_data='confirm_age')],
            [InlineKeyboardButton("❌ Мне нет 18 лет", callback_data='deny_age')]
        ]
        
        await update.message.reply_photo(
            photo=PHOTOS['age_warning'],
            caption=(
                "🔞 *ВНИМАНИЕ!*\n\n"
                "Наш магазин продает никотинсодержащую продукцию.\n\n"
                "В соответствии с Федеральным законом от 23.02.2013 № 15-ФЗ, продажа вейпов и жидкостей для них "
                "*запрещена лицам, не достигшим 18 лет*.\n\n"
                "Нажимая кнопку «Мне есть 18 лет», вы подтверждаете, что достигли совершеннолетия и согласны с правилами магазина."
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

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
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_photo(
        photo=PHOTOS['start'],
        caption=text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"Использование: `/admin [код_доступа]`",
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
        await update.message.reply_text("❌ *Неверный код доступа!*", parse_mode='Markdown')


async def admin_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admin_sessions:
        del admin_sessions[user_id]
        await update.message.reply_text("👋 *Выход выполнен*", parse_mode='Markdown')


async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not has_user_consented(user_id):
        await start(update, context)
        return
    
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


async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not has_user_consented(user_id):
        await start(update, context)
        return
    
    cart_text = get_cart_text(user_id)
    cart_items = get_cart(user_id)
    
    if not cart_items:
        await update.message.reply_photo(
            photo=PHOTOS['cart'],
            caption=cart_text + "\n\n🛍️ Добавьте товары из каталога!",
            parse_mode='Markdown'
        )
        return
    
    # К
