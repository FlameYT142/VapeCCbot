import sqlite3
import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.getenv('DATA_DIR', '.') + '/cart.db'


def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS carts (
                user_id INTEGER,
                product_id TEXT,
                name TEXT,
                price REAL,
                quantity INTEGER,
                row INTEGER,
                PRIMARY KEY (user_id, product_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_data (
                user_id INTEGER PRIMARY KEY,
                address TEXT,
                payment_method TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_consents (
                user_id INTEGER PRIMARY KEY,
                confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"✅ База данных инициализирована: {DB_PATH}")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")


init_db()


def get_connection():
    return sqlite3.connect(DB_PATH)


def has_user_consented(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM user_consents WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logger.error(f"❌ Ошибка проверки согласия: {e}")
        return False


def save_user_consent(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_consents (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ Пользователь {user_id} подтвердил возраст 18+")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения согласия: {e}")
        return False


def get_cart(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT product_id, name, price, quantity, row FROM carts WHERE user_id = ?',
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        cart = []
        for row in rows:
            cart.append({
                'id': row[0],
                'name': row[1],
                'price': row[2],
                'quantity': row[3],
                'row': row[4]
            })
        return cart
    except Exception as e:
        logger.error(f"❌ Ошибка получения корзины: {e}")
        return []


def add_to_cart(user_id, product, quantity=1):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT quantity FROM carts WHERE user_id = ? AND product_id = ?',
            (user_id, product['id'])
        )
        existing = cursor.fetchone()
        
        if existing:
            new_quantity = existing[0] + quantity
            cursor.execute(
                'UPDATE carts SET quantity = ? WHERE user_id = ? AND product_id = ?',
                (new_quantity, user_id, product['id'])
            )
        else:
            cursor.execute(
                'INSERT INTO carts (user_id, product_id, name, price, quantity, row) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, product['id'], product['name'], product['price'], quantity, product.get('row', 0))
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления в корзину: {e}")
        return False


def remove_from_cart(user_id, product_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT quantity FROM carts WHERE user_id = ? AND product_id = ?',
            (user_id, product_id)
        )
        existing = cursor.fetchone()
        
        if not existing:
            conn.close()
            return False
        
        if existing[0] > 1:
            cursor.execute(
                'UPDATE carts SET quantity = quantity - 1 WHERE user_id = ? AND product_id = ?',
                (user_id, product_id)
            )
        else:
            cursor.execute(
                'DELETE FROM carts WHERE user_id = ? AND product_id = ?',
                (user_id, product_id)
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления из корзины: {e}")
        return False


def change_cart_quantity(user_id, product_id, delta):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT quantity FROM carts WHERE user_id = ? AND product_id = ?',
            (user_id, product_id)
        )
        existing = cursor.fetchone()
        
        if not existing:
            conn.close()
            return False
        
        current_quantity = existing[0]
        new_quantity = current_quantity + delta
        
        if new_quantity <= 0:
            cursor.execute(
                'DELETE FROM carts WHERE user_id = ? AND product_id = ?',
                (user_id, product_id)
            )
            logger.info(f"🗑️ Товар {product_id} удалён из корзины")
        else:
            cursor.execute(
                'UPDATE carts SET quantity = ? WHERE user_id = ? AND product_id = ?',
                (new_quantity, user_id, product_id)
            )
            logger.info(f"📦 Товар {product_id}: количество → {new_quantity}")
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка изменения количества: {e}")
        return False


def clear_cart(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM carts WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка очистки корзины: {e}")
        return False


def get_cart_total(user_id):
    cart = get_cart(user_id)
    return sum(item['price'] * item['quantity'] for item in cart)


def get_cart_text(user_id):
    cart = get_cart(user_id)
    if not cart:
        return "🛒 Ваша корзина пуста."
    text = "🛒 *Ваша корзина:*\n\n"
    for item in cart:
        text += f"• {item['name']} x{item['quantity']} = *{item['price'] * item['quantity']:.2f}* руб.\n"
    total = get_cart_total(user_id)
    text += f"\n💰 *Итого: {total:.2f}* руб."
    return text


def save_order_data(user_id, address, payment_method):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM order_data WHERE user_id = ?', (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute(
                'UPDATE order_data SET address = ?, payment_method = ? WHERE user_id = ?',
                (address, payment_method, user_id)
            )
        else:
            cursor.execute(
                'INSERT INTO order_data (user_id, address, payment_method) VALUES (?, ?, ?)',
                (user_id, address, payment_method)
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных заказа: {e}")
        return False


def get_order_data(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT address, payment_method FROM order_data WHERE user_id = ?',
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {'address': row[0], 'payment_method': row[1]}
        return {}
    except Exception as e:
        logger.error(f"❌ Ошибка получения данных заказа: {e}")
        return {}


def clear_order_data(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM order_data WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка очистки данных заказа: {e}")
        return False
