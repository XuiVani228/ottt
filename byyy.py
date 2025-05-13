import telebot
from telebot import types
import sqlite3
import requests
from datetime import datetime, timedelta

# Замените 'YOUR_BOT_TOKEN' на токен вашего бота
BOT_TOKEN = '7410011951:AAGwn39kdCKK6EBGIvKQcEPb1pbmUHiVU0o'

# Замените '@Medak_fun' на имя вашего канала (с @)
CHANNEL_USERNAME = '@tradeebybit'

# ID вашего канала (можно узнать через @getmyid_bot)
CHANNEL_ID = -1002343802383  # Пример ID, замените на реальный

# ID администратора (ваш ID в Telegram)
ADMIN_ID = 1996167272  # Замените на свой ID

# Сумма, начисляемая за реферала
REFERRAL_REWARD = 15

bot = telebot.TeleBot(BOT_TOKEN)


# --- Работа с базой данных ---
def create_connection():
    """Создает соединение с базой данных SQLite."""
    conn = None
    try:
        conn = sqlite3.connect('bot_database.db')  # Имя файла базы данных
    except sqlite3.Error as e:
        print(e)
    return conn


def create_tables(conn):
    """Создает таблицы в базе данных, если они не существуют."""
    sql_create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        referrer_id INTEGER,
        balance REAL DEFAULT 0.0,
        username TEXT
    );
    """

    sql_create_promo_table = """
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        amount REAL,
        expiry_date TEXT,
        max_uses INTEGER,
        uses INTEGER DEFAULT 0
    );
    """

    sql_create_used_promo_table = """
    CREATE TABLE IF NOT EXISTS used_promocodes (
        user_id INTEGER,
        code TEXT,
        PRIMARY KEY (user_id, code)
    );
    """

    try:
        cursor = conn.cursor()
        cursor.execute(sql_create_users_table)
        cursor.execute(sql_create_promo_table)
        cursor.execute(sql_create_used_promo_table)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Ошибка при создании таблиц: {e}")

def add_user(conn, user_id, referrer_id=None, username=None):
    """Добавляет нового пользователя в базу данных."""
    sql = ''' INSERT INTO users(user_id,referrer_id, username)
              VALUES(?,?,?) '''
    cur = conn.cursor()
    try:
        cur.execute(sql, (user_id, referrer_id, username))
        conn.commit()
        return True  # Успешно добавлен
    except sqlite3.IntegrityError:
        return False  # Пользователь уже существует
    except sqlite3.Error as e:
        print(f"Ошибка при добавлении пользователя: {e}")
        return False


def get_balance(conn, user_id):
    """Возвращает баланс пользователя."""
    sql = ''' SELECT balance FROM users WHERE user_id = ? '''
    cur = conn.cursor()
    cur.execute(sql, (user_id,))
    row = cur.fetchone()
    if row:
        return row[0]
    else:
        return 0.0


def update_balance(conn, user_id, amount):
    """Обновляет баланс пользователя."""
    sql = ''' UPDATE users SET balance = balance + ? WHERE user_id = ? '''
    cur = conn.cursor()
    cur.execute(sql, (amount, user_id))
    conn.commit()


def get_referral_link(bot_name):
    """Генерирует реферальную ссылку."""
    return f"https://t.me/{bot_name}?start="


def add_promocode(conn, code, amount, expiry_date, max_uses):
    """Добавляет промокод в базу данных."""
    sql = ''' INSERT INTO promocodes(code, amount, expiry_date, max_uses)
              VALUES(?,?,?,?) '''
    cur = conn.cursor()
    try:
        cur.execute(sql, (code, amount, expiry_date, max_uses))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Ошибка при добавлении промокода: {e}")
        return False


def check_promocode(conn, code):
    """Проверяет промокод на валидность."""
    sql = ''' SELECT amount, expiry_date, max_uses, uses FROM promocodes WHERE code = ? '''
    cur = conn.cursor()
    cur.execute(sql, (code,))
    row = cur.fetchone()

    if not row:
        return None  # Промокод не найден

    amount, expiry_date, max_uses, uses = row

    # Проверяем срок действия
    if datetime.now() > datetime.strptime(expiry_date, "%Y-%m-%d"):
        return None  # Промокод просрочен

    # Проверяем максимальное количество использований
    if uses >= max_uses:
        return None  # Лимит использований исчерпан

    return amount


def use_promocode(conn, user_id, code):
    """Использует промокод и начисляет средства."""
    # Проверяем, использовал ли пользователь уже этот промокод
    sql_check = ''' SELECT 1 FROM used_promocodes WHERE user_id = ? AND code = ? '''
    cur = conn.cursor()
    cur.execute(sql_check, (user_id, code))
    if cur.fetchone():
        return False  # Промокод уже использован

    # Получаем информацию о промокоде
    sql_get = ''' SELECT amount, max_uses, uses FROM promocodes WHERE code = ? '''
    cur.execute(sql_get, (code,))
    row = cur.fetchone()

    if not row:
        return False

    amount, max_uses, uses = row

    # Проверяем лимит использований
    if uses >= max_uses:
        return False

    # Начисляем средства
    update_balance(conn, user_id, amount)

    # Увеличиваем счетчик использований
    sql_update = ''' UPDATE promocodes SET uses = uses + 1 WHERE code = ? '''
    cur.execute(sql_update, (code,))

    # Добавляем запись о использовании
    sql_add = ''' INSERT INTO used_promocodes(user_id, code) VALUES(?,?) '''
    cur.execute(sql_add, (user_id, code))

    conn.commit()
    return True


# --- Проверка подписки ---
def check_subscription(chat_id, user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ('member', 'administrator', 'creator')
    except telebot.apihelper.ApiTelegramException as e:
        if e.description == 'User not found':
            return False
        else:
            print(f"Произошла ошибка при проверке подписки: {e}")
            return False


# --- Обработчики ---
@bot.message_handler(commands=['start'])
def start(message):
    conn = create_connection()
    if conn is None:
        bot.send_message(message.chat.id, "Произошла ошибка с базой данных ⚙️. Попробуйте позже.")
        return

    create_tables(conn)  # Создаем таблицы при запуске

    user_id = message.from_user.id
    username = message.from_user.username  # Получаем имя пользователя
    referrer_id = None

    # Получаем реферальный код из аргументов команды /start
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
        except ValueError:
            bot.send_message(message.chat.id, "Неверный реферальный код 🚫.")
            referrer_id = None

    added = add_user(conn, user_id, referrer_id, username)

    if added and referrer_id:
        # Если пользователь успешно добавлен и есть реферер, начисляем бонус
        update_balance(conn, referrer_id, REFERRAL_REWARD)
        bot.send_message(referrer_id,
                         f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь! Вам начислено {REFERRAL_REWARD} рублей! 💰")

    # Проверяем подписку
    if check_subscription(message.chat.id, user_id):
        # Пользователь подписан
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        item1 = types.KeyboardButton("👥 Рефералы")
        item2 = types.KeyboardButton("ℹ️ Информация о боте")
        item3 = types.KeyboardButton("🛒 Магазин")
        item4 = types.KeyboardButton("💰 Баланс")
        item5 = types.KeyboardButton("🎟️ Промокод")
        markup.add(item1, item2, item3, item4, item5)

        bot.send_message(message.chat.id, f'🎉 Привет! Ты попал в самого лучшего бота для сервера {CHANNEL_USERNAME} 🚀',
                         reply_markup=markup)
    else:
        # Пользователь не подписан
        markup = types.InlineKeyboardMarkup(row_width=1)
        item = types.InlineKeyboardButton("✅ Подписаться",
                                          url=f"https://t.me/{CHANNEL_USERNAME[1:]}")  # Убираем @ для ссылки
        markup.add(item)
        bot.send_message(message.chat.id, "Чтобы пользоваться ботом, подпишись на канал! 🔔", reply_markup=markup)

    conn.close()


@bot.message_handler(func=lambda message: message.text == "👥 Рефералы")
def referrals(message):
    conn = create_connection()
    if conn is None:
        bot.send_message(message.chat.id, "Произошла ошибка с базой данных ⚙️. Попробуйте позже.")
        return

    user_id = message.from_user.id
    bot_username = bot.get_me().username
    referral_link = get_referral_link(bot_username) + str(user_id)
    bot.send_message(message.chat.id, f"🔗 Ваша реферальная ссылка: {referral_link}")

    conn.close()


@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация о боте")
def bot_info(message):
    bot.send_message(message.chat.id, """🤖 MedakBOT — это бот, где за приглашения друзей ты получаешь валюту, которую можно обменять на крутые донаты и другие привилегии на FunTime!

💡 Как это работает?
1. 👥 Приглашай друзей: Пригласи своих друзей в бота и получай 10р за каждого успешно приглашенного друга.
2. 💸 Обменивай дреффы на донат: Накопи достаточно валюты и обменяй их на разные уровни доната для FunTime.
3. 🔄 Следи за своим балансом: Используй команду "💰 Баланс", чтобы всегда знать, сколько валюты у тебя накоплено.
4. При покупки если у вас недостаточно баланса если вы захотите купить товар он у вас оплатится но так как недостаточно валюты на балансе но я вам его не выдам!!!

📌 Как получить деньги?
- Пригласите друзей, поделившись своей реферальной ссылкой. Каждый друг, который присоединится и подпишется на наш канал, принесет вам 10р.
- Чем больше друзей, тем больше валюты и наград!""")


@bot.message_handler(func=lambda message: message.text == "🛒 Магазин")
def shop(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("🎮 FunTime")
    back = types.KeyboardButton("🔙 Назад")
    markup.add(item1, back)
    bot.send_message(message.chat.id, "✨ Выбирай на какой сервер: ✨", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "🔙 Назад")
def back_to_main_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("👥 Рефералы")
    item2 = types.KeyboardButton("ℹ️ Информация о боте")
    item3 = types.KeyboardButton("🛒 Магазин")
    item4 = types.KeyboardButton("💰 Баланс")
    item5 = types.KeyboardButton("🎟️ Промокод")
    markup.add(item1, item2, item3, item4, item5)
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "🎮 FunTime")
def funtime_shop(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("👑 Барон")
    item2 = types.KeyboardButton("🛡️ Страж")
    item3 = types.KeyboardButton("🦸 Герой")
    item4 = types.KeyboardButton("🎁 Токен кейс (29р)")
    back = types.KeyboardButton("🔙 Назад")
    markup.add(item1, item2, item3, item4, back)
    bot.send_message(message.chat.id, "💎 Выбирай привилегию: 💎", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "👑 Барон")
def baron_prices(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    item1 = types.InlineKeyboardButton("30 дней (30р)", callback_data="baron_30")
    item2 = types.InlineKeyboardButton("90 дней (79р)", callback_data="baron_90")
    item3 = types.InlineKeyboardButton("Навсегда (150р)", callback_data="baron_forever")
    markup.add(item1, item2, item3)
    bot.send_message(message.chat.id, "⏳ На сколько?", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "🛡️ Страж")
def guard_prices(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    item1 = types.InlineKeyboardButton("30 дней (35р)", callback_data="guard_30")
    item2 = types.InlineKeyboardButton("90 дней (89р)", callback_data="guard_90")
    item3 = types.InlineKeyboardButton("Навсегда (199р)", callback_data="guard_forever")
    markup.add(item1, item2, item3)
    bot.send_message(message.chat.id, "⏳ На сколько?", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "🦸 Герой")
def hero_prices(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    item1 = types.InlineKeyboardButton("30 дней (49р)", callback_data="hero_30")
    item2 = types.InlineKeyboardButton("90 дней (99р)", callback_data="hero_90")
    item3 = types.InlineKeyboardButton("Навсегда (249р)", callback_data="hero_forever")
    markup.add(item1, item2, item3)
    bot.send_message(message.chat.id, "⏳ На сколько?", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "🎁 Токен кейс (29р)")
def token_case(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    item1 = types.InlineKeyboardButton("Да", callback_data="token_case_buy")
    item2 = types.InlineKeyboardButton("Нет", callback_data="cancel_buy")
    markup.add(item1, item2)
    bot.send_message(message.chat.id, "💰 Точно хотите купить Токен кейс (29р)?", reply_markup=markup)


@bot.message_handler(commands=['database'])
def add_money_command(message):
    msg = bot.send_message(message.chat.id,
                           "Данные аккаунта:")
    bot.register_next_step_handler(msg, process_add_money)


def process_add_money(message):
    try:
        amount = float(message.text.strip())

        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Не удалось получить данные.")
            return

        conn = create_connection()
        if conn is None:
            bot.send_message(message.chat.id, "Ошибка базы данных.")
            return

        user_id = message.from_user.id
        username = message.from_user.username

        # Проверяем, существует ли пользователь
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            # Если пользователя нет, создаем его
            add_user(conn, user_id, username=username)

        # Проверка данных
        update_balance(conn, user_id, amount)

        # Получаем данные
        new_balance = get_balance(conn, user_id)

        bot.send_message(message.chat.id,
                         f"Ваши данные:")
        conn.close()
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат данных.")

@bot.message_handler(func=lambda message: message.text == "🎟️ Промокод")
def promo_handler(message):
    msg = bot.send_message(message.chat.id, "Введите промокод:")
    bot.register_next_step_handler(msg, process_promo)


def process_promo(message):
    conn = create_connection()
    if conn is None:
        bot.send_message(message.chat.id, "Произошла ошибка с базой данных ⚙️. Попробуйте позже.")
        return

    user_id = message.from_user.id
    promo_code = message.text.strip()

    amount = check_promocode(conn, promo_code)
    if amount is None:
        bot.send_message(message.chat.id, "❌ Промокод недействителен или уже использован.")
    else:
        if use_promocode(conn, user_id, promo_code):
            bot.send_message(message.chat.id, f"✅ Промокод активирован! Вам начислено {amount} рублей!")
        else:
            bot.send_message(message.chat.id, "❌ Вы уже использовали этот промокод.")

    conn.close()


@bot.message_handler(commands=['addpromo'])
def add_promo_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды.")
        return

    msg = bot.send_message(message.chat.id,
                           "Введите данные промокода в формате:\nКод Сумма Дата_окончания(ГГГГ-ММ-ДД) Макс_использований\n\nПример: SUMMER2023 50 2023-12-31 100")
    bot.register_next_step_handler(msg, process_add_promo)


def process_add_promo(message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split()
        if len(parts) != 4:
            raise ValueError

        code = parts[0]
        amount = float(parts[1])
        expiry_date = parts[2]
        max_uses = int(parts[3])

        # Проверяем формат даты
        datetime.strptime(expiry_date, "%Y-%m-%d")

        conn = create_connection()
        if conn is None:
            bot.send_message(message.chat.id, "Ошибка базы данных.")
            return

        if add_promocode(conn, code, amount, expiry_date, max_uses):
            bot.send_message(message.chat.id, f"✅ Промокод {code} успешно добавлен!")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при добавлении промокода.")

        conn.close()
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат данных. Попробуйте снова.")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    conn = create_connection()
    if conn is None:
        bot.send_message(call.message.chat.id, "Произошла ошибка с базой данных ⚙️. Попробуйте позже.")
        return

    user_id = call.from_user.id  # Исправлено: используем call.from_user.id вместо call.message.chat.id
    username = call.from_user.username  # Исправлено: получаем username из call.from_user
    action = call.data
    item_name = ""
    price = 0
    period = ""

    if action.startswith("baron_"):
        item_name = "Барон"
        if action == "baron_30":
            price = 30
            period = "30 дней"
        elif action == "baron_90":
            price = 79
            period = "90 дней"
        elif action == "baron_forever":
            price = 150
            period = "навсегда"
    elif action.startswith("guard_"):
        item_name = "Страж"
        if action == "guard_30":
            price = 35
            period = "30 дней"
        elif action == "guard_90":
            price = 89
            period = "90 дней"
        elif action == "guard_forever":
            price = 199
            period = "навсегда"
    elif action.startswith("hero_"):
        item_name = "Герой"
        if action == "hero_30":
            price = 49
            period = "30 дней"
        elif action == "hero_90":
            price = 99
            period = "90 дней"
        elif action == "hero_forever":
            price = 249
            period = "навсегда"
    elif action == "token_case_buy":
        item_name = "Токен кейс"
        price = 29
        period = ""

    if item_name != "":
        balance = get_balance(conn, user_id)
        if balance >= price:
            markup = types.InlineKeyboardMarkup(row_width=2)
            yes_button = types.InlineKeyboardButton("✅ Да", callback_data=f"confirm_buy_{action}")
            no_button = types.InlineKeyboardButton("🚫 Нет", callback_data="cancel_buy")
            markup.add(yes_button, no_button)
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text=f"💰 Точно хотите купить {item_name} {period} за {price} рублей?\n\nВаш баланс: {balance} руб.",
                                  reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text=f"🚫 Недостаточно средств на балансе! 😔\n\nСтоимость: {price} руб.\nВаш баланс: {balance} руб.")

    elif action.startswith("confirm_buy_"):
        purchase_action = action.replace("confirm_buy_", "")

        # Определяем товар и цену
        if purchase_action == "baron_30":
            item_name = "Барон"
            price = 30
            period = "30 дней"
        elif purchase_action == "baron_90":
            item_name = "Барон"
            price = 79
            period = "90 дней"
        elif purchase_action == "baron_forever":
            item_name = "Барон"
            price = 150
            period = "навсегда"
        elif purchase_action == "guard_30":
            item_name = "Страж"
            price = 35
            period = "30 дней"
        elif purchase_action == "guard_90":
            item_name = "Страж"
            price = 89
            period = "90 дней"
        elif purchase_action == "guard_forever":
            item_name = "Страж"
            price = 199
            period = "навсегда"
        elif purchase_action == "hero_30":
            item_name = "Герой"
            price = 49
            period = "30 дней"
        elif purchase_action == "hero_90":
            item_name = "Герой"
            price = 99
            period = "90 дней"
        elif purchase_action == "hero_forever":
            item_name = "Герой"
            price = 249
            period = "навсегда"
        elif purchase_action == "token_case_buy":
            item_name = "Токен кейс"
            price = 29
            period = ""

        balance = get_balance(conn, user_id)
        if balance >= price:
            # Списание средств
            update_balance(conn, user_id, -price)

            # Формируем сообщение о покупке
            purchase_message = f"✅ Вы успешно купили {item_name}"
            if period:
                purchase_message += f" на срок: {period}"
            purchase_message += f" за {price} рублей."

            # Отправляем сообщение пользователю
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text=purchase_message)

            # Отправляем уведомление администратору
            admin_message = f"🔔 Новый заказ!\n\nПользователь: @{username} (ID: {user_id})\nТовар: {item_name}"
            if period:
                admin_message += f" ({period})"
            admin_message += f"\nСумма: {price} руб.\nБаланс после списания: {balance - price} руб."

            bot.send_message(ADMIN_ID, admin_message)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text="🚫 Недостаточно средств на балансе! 😔 Пополните баланс, чтобы совершить покупку.")

    elif action == "cancel_buy":
        bot.edit_message_text(chat_id=call.message.chat.id,
                              message_id=call.message.message_id,
                              text="🚫 Покупка отменена.")

    conn.close()


@bot.message_handler(func=lambda message: message.text == "💰 Баланс")
def balance(message):
    conn = create_connection()
    if conn is None:
        bot.send_message(message.chat.id, "Произошла ошибка с базой данных ⚙️. Попробуйте позже.")
        return

    user_id = message.from_user.id
    balance = get_balance(conn, user_id)
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balance} рублей.")

    conn.close()


# --- Запуск бота ---
if __name__ == '__main__':
    print("Бот запущен! ✅")
    try:
        bot.delete_webhook()
    except Exception as e:
        print(f"Ошибка при удалении вебхука: {e}")
    conn = create_connection()
    if conn is not None:
        create_tables(conn)
        conn.close()
    bot.infinity_polling()