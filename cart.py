# Хранилище корзин пользователей
user_carts = {}
user_orders = {}


def get_cart(user_id):
    if user_id not in user_carts:
        user_carts[user_id] = []
    return user_carts[user_id]


def add_to_cart(user_id, product, quantity=1):
    """Добавить товар в корзину"""
    cart = get_cart(user_id)
    for item in cart:
        if item['id'] == product['id']:
            item['quantity'] += quantity
            return True
    cart.append({
        'id': product['id'],
        'name': product['name'],
        'price': product['price'],
        'quantity': quantity,
        'row': product.get('row', 0)
    })
    return True


def remove_from_cart(user_id, product_id):
    cart = get_cart(user_id)
    for i, item in enumerate(cart):
        if item['id'] == product_id:
            if item['quantity'] > 1:
                item['quantity'] -= 1
            else:
                cart.pop(i)
            return True
    return False


def clear_cart(user_id):
    if user_id in user_carts:
        user_carts[user_id] = []


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
    if user_id not in user_orders:
        user_orders[user_id] = {}
    user_orders[user_id]['address'] = address
    user_orders[user_id]['payment_method'] = payment_method
    return True


def get_order_data(user_id):
    return user_orders.get(user_id, {})


def clear_order_data(user_id):
    if user_id in user_orders:
        user_orders[user_id] = {}
