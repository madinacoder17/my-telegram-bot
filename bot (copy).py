import os
import telebot
from telebot import types
import sqlite3
import random
import threading
import time
import datetime
from flask import Flask  # Добавили Flask для обхода портов Render

# --- НАСТРОЙКА ВЕБ-СЕРВЕРА ДЛЯ RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

def run_web_server():
    # Render передает порт в переменных окружения PORT. По умолчанию ставим 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Запускаем веб-сервер в отдельном потоке, чтобы он не мешал боту
threading.Thread(target=run_web_server, daemon=True).start()
# ----------------------------------------

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан! Добавь его в секреты.")

bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 8235717528  

@bot.message_handler(commands=['broadcast'])
def start_broadcast(message):
    if message.chat.id != ADMIN_ID:
        return
    msg = bot.send_message(message.chat.id, "Напишите text сообщения для рассылки всем пользователям:")
    bot.register_next_step_handler(msg, send_broadcast_message)

def send_broadcast_message(message):
    text_to_send = message.text
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM rabbits")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "В базе данных пока нет пользователей.")
        return

    success_count = 0
    fail_count = 0
    bot.send_message(message.chat.id, f"Начинаю рассылку для {len(rows)} чатов...")

    for row in rows:
        user_chat_id = row[0]
        try:
            bot.send_message(user_chat_id, text_to_send)
            success_count += 1
            time.sleep(0.1)
        except Exception as e:
            fail_count += 1

    bot.send_message(
        message.chat.id, 
        f"Рассылка завершена! 🎉\n"
        f"Успешно доставлено: {success_count}\n"
        f"Не удалось отправить: {fail_count}"
    )


PHOTOS_DIR = os.path.join(os.path.dirname(__file__), 'photos')

PHOTOS = {
    "белый": [
        os.path.join(PHOTOS_DIR, "white1.jpg"),
        os.path.join(PHOTOS_DIR, "white2.jpg"),
        os.path.join(PHOTOS_DIR, "white3.jpg"),
    ],
    "черный": [
        os.path.join(PHOTOS_DIR, "black1.jpg"),
        os.path.join(PHOTOS_DIR, "black2.jpg"),
        os.path.join(PHOTOS_DIR, "black3.jpg"),
    ],
    "розовый": [
        os.path.join(PHOTOS_DIR, "pink1.jpg"),
        os.path.join(PHOTOS_DIR, "pink2.jpg"),
        os.path.join(PHOTOS_DIR, "pink3.jpg"),
    ],
}

DB_PATH = os.path.join(os.path.dirname(__file__), 'rabbits.db')

MAX_SATIETY = 8

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rabbits'")
    table_exists = cursor.fetchone()

    if table_exists:
        cursor.execute("PRAGMA table_info(rabbits)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'user_id' in columns and 'chat_id' not in columns:
            cursor.execute("ALTER TABLE rabbits RENAME COLUMN user_id TO chat_id")
            conn.commit()

        if 'last_fed' not in columns:
            cursor.execute("ALTER TABLE rabbits ADD COLUMN last_fed TEXT")
            cursor.execute("UPDATE rabbits SET last_fed = ? WHERE last_fed IS NULL", (str(time.time()),))
            conn.commit()

        if 'utc_offset' not in columns:
            cursor.execute("ALTER TABLE rabbits ADD COLUMN utc_offset INTEGER")
            conn.commit()
    else:
        cursor.execute('''
            CREATE TABLE rabbits (
                chat_id INTEGER PRIMARY KEY,
                status TEXT,
                name TEXT,
                color TEXT,
                satiety INTEGER,
                lives INTEGER,
                mood TEXT,
                last_life_gift TEXT,
                last_fed TEXT,
                utc_offset INTEGER
            )
        ''')
        conn.commit()

    conn.close()

init_db()

# --- НОЧНОЕ ВРЕМЯ ---
def is_night_for_user(utc_offset):
    if utc_offset is None:
        return False
    utc_now = datetime.datetime.utcnow()
    user_hour = (utc_now.hour + utc_offset) % 24
    return user_hour >= 23 or user_hour < 7

def parse_time_input(text):
    text = text.strip().lower()

    if ':' in text:
        parts = text.split(':')
        try:
            hour = int(parts[0])
            if 0 <= hour <= 23:
                return hour
        except ValueError:
            pass

    is_pm = any(w in text for w in ['вечера', 'ночи', 'pm', 'вечер'])
    is_am = any(w in text for w in ['утра', 'утром', 'am', 'дня'])

    digits = ''.join(c for c in text if c.isdigit())
    if digits:
        try:
            hour = int(digits[:2])
            if is_pm and hour != 12 and hour < 12:
                hour += 12
            elif is_am and hour == 12:
                hour = 0
            if 0 <= hour <= 23:
                return hour
        except ValueError:
            pass

    return None

def calc_utc_offset(user_hour):
    utc_hour = datetime.datetime.utcnow().hour
    offset = user_hour - utc_hour
    if offset > 14:
        offset -= 24
    elif offset < -12:
        offset += 24
    return offset

# --- КЛАВИАТУРЫ ---
def get_color_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("белый", "черный", "розовый")
    return markup

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add("📊 Состояние зайчика", "😋 Дать вкусняшку", "🎉 Поднять настроение", "⚙️ Настройки")
    return markup

def get_food_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🍼 Молочко", "🥕 Морковка", "🥬 Капуста", "🍓 Клубника", "🍽 Каша", "🍬 Сладкое", "⬅️ В меню")
    return markup

def get_game_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add("🎈 Поиграть с воздушным шариком", "🧩 Собрать пазлы", "🎨 Порисовать", "⚽️ Поиграть в мячик", "⬅️ В меню")
    return markup

def get_revive_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("❤️ Использовать жизнь", "👶 Создать нового")
    return markup

def get_settings_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add("Сбросить зайчика😭😭😭", "Изменить имя", "⬅️ В меню")
    return markup

def get_reset_confirm_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Да😪", "Нет😊")
    return markup

def get_timezone_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        "🕐 UTC+2 (Калининград)",
        "🕐 UTC+3 (Москва)",
        "🕐 UTC+4 (Самара)",
        "🕐 UTC+5 (Екатеринбург)",
        "🕐 UTC+6 (Омск)",
        "🕐 UTC+7 (Красноярск)",
        "🕐 UTC+8 (Иркутск)",
        "🕐 UTC+9 (Якутск)",
        "🕐 UTC+10 (Владивосток)",
        "🕐 UTC+12 (Камчатка)",
        "⏩ Пропустить"
    )
    return markup

def remove_keyboard():
    return types.ReplyKeyboardRemove()

# --- ХАРАКТЕР ЗАЙЧИКА ---
def rabbit_speak(name, mood, satiety):
    if satiety <= 2:
        return random.choice([
            f"у меня живот урчит... покорми меня пожалуйста 🥺🥕",
            f"я так голоден что даже говорить не могу нормально... 🥺",
            f"ты слышишь этот звук? это мой желудок... морковку дай...",
            f"я умираю с голоду тут буквально 😭 ГДЕ ЕДА",
            f"покорми сначала, потом разговоры! 🥕🥕🥕",
        ])

    if mood == "😍":
        phrases = [
            f"я тебя люблю! ты лучший хозяин на свете 🥰",
            f"сегодня такой хороший день... я счастлив 😍",
            f"мне так хорошо рядом с тобой ❤️",
            f"жизнь прекрасна! особенно когда есть морковка 🥕✨",
            f"ты написал мне! я так рад!! 🥰🐰",
            f"обними меня пожалуйста... мысленно 🤗",
        ]
    elif mood == "😃":
        phrases = [
            f"привет! у меня всё хорошо, а у тебя? 😊",
            f"я сегодня в отличном настроении! чего и тебе желаю 🐰",
            f"хм, что ты хотел сказать? я внимательно слушаю 👂",
            f"скучал по тебе немного если честно 😊",
            f"расскажи мне что-нибудь интересное! 🐰",
            f"я тут прыгал немного, разминался. что пишешь? 🐾",
        ]
    elif mood == "😔":
        phrases = [
            f"мне немного грустно сегодня... не знаю почему 😔",
            f"ладно... привет 😔",
            f"хотел бы я быть зайцем в лесу... свободным...",
            f"поиграй со мной, а? мне скучно и грустно 😔",
            f"я тут думал о смысле жизни... морковка это смысл наверное",
            f"ничего не хочется... может поиграем? 🧩",
        ]
    elif mood == "😭":
        phrases = [
            f"я плачу! у меня плохое настроение и никто не понимает 😭",
            f"оставь меня... хотя нет не оставляй 😭",
            f"всё плохо. ну и ладно. 😭",
            f"я несчастный маленький зайчик 😭🐰",
            f"почему жизнь такая несправедливая... 😭",
            f"поиграй со мной пожалуйста, может полегчает... 😭",
        ]
    elif mood == "😡":
        phrases = [
            f"ЧТО ТЕБЕ НАДО?! я злюсь! 😡",
            f"не трогай меня!! 😡",
            f"я в бешенстве! отстань! 😡",
            f"АААА!! всё раздражает сегодня!! 😡",
            f"ты что-то написал? мне всё равно! 😡",
            f"уйди! хотя... ладно. что хотел. 😡",
        ]
    else:
        phrases = [
            f"хм? 🐰",
            f"я тут. слушаю.",
            f"чего? 🐾",
        ]

    return random.choice(phrases)

# --- ОТОБРАЖЕНИЕ СЫТОСТИ ---
def format_satiety(satiety):
    if satiety >= MAX_SATIETY:
        return "🥕" * MAX_SATIETY, ""
    elif satiety >= 6:
        carrots = "🥕" * satiety
        return carrots, ""
    elif satiety >= 4:
        carrots = "🥕" * satiety + " (Немного голоден)"
        return carrots, ""
    elif satiety >= 2:
        carrots = "🥕" * satiety
        return carrots, "\n⚠️ Он откинет лапы, если не покормить сейчас же!"
    else:
        return "Нет еды", ""

# --- ОБРАБОТЧИКИ ---
@bot.message_handler(content_types=['new_chat_members'])
def on_added_to_group(message):
    bot_id = bot.get_me().id
    new_members = message.new_chat_members
    if not any(m.id == bot_id for m in new_members):
        return

    chat_id = message.chat.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM rabbits WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()

    if not row:
        current_time = str(time.time())
        cursor.execute(
            "INSERT INTO rabbits VALUES (?, 'creating_color', '', '', ?, 0, '😃', ?, ?, NULL)",
            (chat_id, MAX_SATIETY, current_time, current_time)
        )
        conn.commit()
        bot.send_message(chat_id, "Спасибо что добавили меня в группу🥰🐰")
        bot.send_message(chat_id, "Давайте создадим нашего группового зайчика! Выберите его цвет:", reply_markup=get_color_keyboard())
    else:
        if row[0] == 'dead':
            bot.send_message(chat_id, "Привет снова! Наш зайчик откинул лапки... 😢 Что будем делать?", reply_markup=get_revive_keyboard())
        else:
            bot.send_message(chat_id, "Я уже здесь! Наш зайчик ждёт вас 🐰", reply_markup=get_main_keyboard())
    conn.close()

@bot.message_handler(commands=['start'])
def start_game(message):
    chat_id = message.chat.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM rabbits WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()

    current_time = str(time.time())
    if not row:
        cursor.execute(
            "INSERT INTO rabbits VALUES (?, 'creating_color', '', '', ?, 0, '😃', ?, ?, NULL)",
            (chat_id, MAX_SATIETY, current_time, current_time)
        )
        conn.commit()
        bot.send_message(chat_id, "Добро пожаловать в бот Зайчик Милашек, для начала создайте своего зайчика!", reply_markup=get_color_keyboard())
    else:
        if row[0] == 'dead':
            bot.send_message(chat_id, "Твой зайчик откинул лапки... 😢 Что будем делать?", reply_markup=get_revive_keyboard())
        else:
            bot.send_message(chat_id, "Твой зайчик уже ждет тебя!", reply_markup=get_main_keyboard())
    conn.close()

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    text = message.text

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, name, color, satiety, lives, mood, utc_offset FROM rabbits WHERE chat_id = ?", (chat_id,))
    user_data = cursor.fetchone()

    if not user_data:
        conn.close()
        return

    status, name, color, satiety, lives, mood, utc_offset = user_data

    # 1. Выбор цвета при создании
    if status == 'creating_color':
        if text in ["белый", "черный", "розовый"]:
            photo_list = PHOTOS[text][:]
            random.shuffle(photo_list)
            random_photo = photo_list[0]
            print(f"[ФОТО] chat_id={chat_id} цвет={text} файл={os.path.basename(random_photo)}")
            cursor.execute("UPDATE rabbits SET color = ?, status = 'creating_name' WHERE chat_id = ?", (text, chat_id))
            conn.commit()
            try:
                with open(random_photo, 'rb') as photo_file:
                    bot.send_photo(chat_id, photo_file, caption="Зайчику нужно имя!")
            except Exception as e:
                print(f"Ошибка отправки фото: {e}")
                bot.send_message(chat_id, "Зайчику нужно имя!")
        else:
            bot.send_message(chat_id, "Выбери цвет на кнопках!", reply_markup=get_color_keyboard())

    # 2. Ввод имени при создании
    elif status == 'creating_name':
        cursor.execute("UPDATE rabbits SET name = ?, status = 'creating_time' WHERE chat_id = ?", (text, chat_id))
        conn.commit()
        bot.send_message(
            chat_id,
            f"Отличное имя — {text}! 🐰\n\n"
            "Выберите ваш часовой пояс — зайчик не будет тревожить вас ночью 🌙\n"
            "Или напишите текущее время вручную, например: 22:30",
            reply_markup=get_timezone_keyboard()
        )

    # 3. Ввод времени / часового пояса при создании
    elif status == 'creating_time':
        utc_offset = None

        if text == "⏩ Пропустить":
            utc_offset = None
            skip = True
        else:
            skip = False
            if text.startswith("🕐 UTC"):
                try:
                    sign_part = text.split("UTC")[1].split(" ")[0]
                    utc_offset = int(sign_part)
                except Exception:
                    utc_offset = None
            else:
                hour = parse_time_input(text)
                if hour is not None:
                    utc_offset = calc_utc_offset(hour)
                else:
                    bot.send_message(
                        chat_id,
                        "Не могу разобрать время 😅 Выберите кнопку или напишите время, например: 22:30",
                        reply_markup=get_timezone_keyboard()
                    )
                    conn.close()
                    return

        current_time = str(time.time())
        cursor.execute(
            "UPDATE rabbits SET status = 'alive', utc_offset = ?, last_fed = ? WHERE chat_id = ?",
            (utc_offset, current_time, chat_id)
        )
        conn.commit()
        if skip or utc_offset is None:
            bot.send_message(
                chat_id,
                "Ура, мы создали зайчика! 🎉\nНужно ухаживать за зайчиком, чтобы он не откинул лапки ><",
                reply_markup=get_main_keyboard()
            )
        else:
            bot.send_message(
                chat_id,
                "Ура, мы создали зайчика! 🎉\nНужно ухаживать за зайчиком, чтобы он не откинул лапки ><\n\n"
                "🌙 Ночью с 23:00 до 7:00 по вашему времени зайчик будет спать и не проголодается!",
                reply_markup=get_main_keyboard()
            )

    # 4. Изменение имени через настройки
    elif status == 'changing_name':
        cursor.execute("UPDATE rabbits SET name = ?, status = 'alive' WHERE chat_id = ?", (text, chat_id))
        conn.commit()
        bot.send_message(chat_id, f"Имя успешно изменено на {text}! ✨", reply_markup=get_main_keyboard())

    # 5. Подтверждение полного сброса
    elif status == 'confirm_reset':
        if text == "Да😪":
            current_time = str(time.time())
            cursor.execute(
                "UPDATE rabbits SET status = 'creating_color', name='', color='', satiety=?, lives=0, mood='😃', last_fed=?, utc_offset=NULL WHERE chat_id = ?",
                (MAX_SATIETY, current_time, chat_id)
            )
            conn.commit()
            bot.send_message(chat_id, "Зайчик сброшен... Давай создадим нового 🥺", reply_markup=get_color_keyboard())
        elif text == "Нет😊":
            cursor.execute("UPDATE rabbits SET status = 'alive' WHERE chat_id = ?", (chat_id,))
            conn.commit()
            bot.send_message(chat_id, "Ура! Зайчик остается с тобой!", reply_markup=get_settings_keyboard())
        else:
            bot.send_message(chat_id, "Выбери 'Да😪' или 'Нет😊' на кнопках!", reply_markup=get_reset_confirm_keyboard())

    # 6. Зайчик умер
    elif status == 'dead':
        if text == "❤️ Использовать жизнь":
            if lives > 0:
                current_time = str(time.time())
                cursor.execute(
                    "UPDATE rabbits SET status = 'alive', satiety = ?, lives = ?, last_fed = ? WHERE chat_id = ?",
                    (MAX_SATIETY, lives - 1, current_time, chat_id)
                )
                conn.commit()
                bot.send_message(chat_id, "Жизнь использована! Зайчик спасен!", reply_markup=get_main_keyboard())
            else:
                bot.send_message(chat_id, "У тебя нет жизней! Придется создать нового.", reply_markup=get_revive_keyboard())
        elif text == "👶 Создать нового":
            current_time = str(time.time())
            cursor.execute(
                "UPDATE rabbits SET status = 'creating_color', name='', color='', satiety=?, mood='😃', last_fed=?, utc_offset=NULL WHERE chat_id = ?",
                (MAX_SATIETY, current_time, chat_id)
            )
            conn.commit()
            bot.send_message(chat_id, "Создаем нового зайчика!", reply_markup=get_color_keyboard())

    # 7. Основной игровой процесс (зайчик жив)
    elif status == 'alive':

        if text == "📊 Состояние зайчика":
            carrots, warning = format_satiety(satiety)
            mood_labels = {
                "😍": "Влюблён 😍",
                "😃": "Счастлив 😃",
                "😔": "Грустит 😔",
                "😭": "Плачет 😭",
                "😡": "Злится 😡",
            }
            mood_text = mood_labels.get(mood, mood)
            night_info = ""
            if utc_offset is not None and is_night_for_user(utc_offset):
                night_info = "\n🌙 Сейчас ночь — зайчик спит и не голодает!"
            status_msg = f"Имя: {name}\n\nСытость: {carrots}{warning}\nЖизни: {lives} ❤️\nНастроение: {mood_text}{night_info}"
            bot.send_message(chat_id, status_msg)

        elif text == "😋 Дать вкусняшку":
            bot.send_message(chat_id, "Чем покормим?", reply_markup=get_food_keyboard())

        elif text in ["🍼 Молочко", "🥕 Морковка", "🥬 Капуста", "🍓 Клубника", "🍽 Каша"]:
            if satiety < MAX_SATIETY:
                current_time = str(time.time())
                cursor.execute("UPDATE rabbits SET satiety = ?, last_fed = ? WHERE chat_id = ?", (MAX_SATIETY, current_time, chat_id))
                conn.commit()
                bot.send_message(chat_id, "😋 вкусно, я доел", reply_markup=get_main_keyboard())
            else:
                bot.send_message(chat_id, "😌 спасибо, я не голоден", reply_markup=get_main_keyboard())

        elif text == "🍬 Сладкое":
            cursor.execute("UPDATE rabbits SET mood = '😡' WHERE chat_id = ?", (chat_id,))
            conn.commit()
            bot.send_message(chat_id, "😡 сладкое вредно!! УБЕРИ!!!", reply_markup=get_main_keyboard())

        elif text == "🎉 Поднять настроение":
            bot.send_message(chat_id, "Во что поиграем?", reply_markup=get_game_keyboard())

        elif text in ["🎈 Поиграть с воздушным шариком", "🧩 Собрать пазлы", "🎨 Порисовать", "⚽️ Поиграть в мячик"]:
            if random.choice([True, False]):
                new_mood = random.choice(["😍", "😃"])
                cursor.execute("UPDATE rabbits SET mood = ? WHERE chat_id = ?", (new_mood, chat_id))
                conn.commit()
                bot.send_message(chat_id, f"интересненько😊\nНастроение: {new_mood}", reply_markup=get_main_keyboard())
            else:
                new_mood = random.choice(["😔", "😭", "😡"])
                cursor.execute("UPDATE rabbits SET mood = ? WHERE chat_id = ?", (new_mood, chat_id))
                conn.commit()
                bot.send_message(chat_id, f"не хочу в это! отстань!\nНастроение: {new_mood}", reply_markup=get_main_keyboard())

        elif text == "⚙️ Настройки":
            bot.send_message(chat_id, "Меню настроек зайчика ⚙️", reply_markup=get_settings_keyboard())

        elif text == "Сбросить зайчика😭😭😭":
            cursor.execute("UPDATE rabbits SET status = 'confirm_reset' WHERE chat_id = ?", (chat_id,))
            conn.commit()
            bot.send_message(chat_id, "Вы уверены что хотите бросить зайчика?🥺", reply_markup=get_reset_confirm_keyboard())

        elif text == "Изменить имя":
            cursor.execute("UPDATE rabbits SET status = 'changing_name' WHERE chat_id = ?", (chat_id,))
            conn.commit()
            bot.send_message(chat_id, "Напиши новое имя для зайчика:")

        elif text == "⬅️ В меню":
            bot.send_message(chat_id, "Возвращаемся в главное меню", reply_markup=get_main_keyboard())

        else:
            reply = rabbit_speak(name, mood, satiety)
            bot.send_message(chat_id, reply, reply_markup=get_main_keyboard())

    conn.close()



# --- ТАЙМЕРЫ: голод и жизни ---
def game_clock():
    while True:
        time.sleep(10)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, status, satiety, lives, last_life_gift, last_fed, name, utc_offset FROM rabbits")
        all_rabbits = cursor.fetchall()
        current_time = time.time()

        for rabbit in all_rabbits:
            cid, r_status, r_satiety, r_lives, r_last_gift, r_last_fed, r_name, r_utc_offset = rabbit

            if r_status == 'alive':
                # --- ГОЛОД ---
                try:
                    if r_last_fed and current_time - float(r_last_fed) >= 7200:
                        if is_night_for_user(r_utc_offset):
                            cursor.execute(
                                "UPDATE rabbits SET last_fed = ? WHERE chat_id = ?",
                                (str(current_time), cid)
                            )
                            conn.commit()
                        else:
                            new_satiety = r_satiety - 2
                            if new_satiety <= 0:
                                cursor.execute("UPDATE rabbits SET status = 'dead', satiety = 0 WHERE chat_id = ?", (cid,))
                                conn.commit()
                                try:
                                    bot.send_message(cid, "Ты не кормил меня, эхь", reply_markup=get_revive_keyboard())
                                except Exception:
                                    pass
                            else:
                                cursor.execute(
                                    "UPDATE rabbits SET satiety = ?, last_fed = ? WHERE chat_id = ?",
                                    (new_satiety, str(current_time), cid)
                                )
                                conn.commit()
                                try:
                                    bot.send_message(cid, f"🐰 {r_name} проголодался! Сытость уменьшилась.")
                                except Exception:
                                    pass
                except Exception:
                    pass

                # --- ЖИЗНИ ---
                try:
                    if r_last_gift and current_time - float(r_last_gift) >= 259200:
                        cursor.execute(
                            "UPDATE rabbits SET lives = lives + 1, last_life_gift = ? WHERE chat_id = ?",
                            (str(current_time), cid)
                        )
                        conn.commit()
                        try:
                            bot.send_message(cid, "🎁 Прошло 3 дня! Тебе начислена 1 жизнь для зайчика!")
                        except Exception:
                            pass
                except Exception:
                    pass

        conn.close()

threading.Thread(target=game_clock, daemon=True).start()

print("Бот запущен!")
while True:
    try:
        bot.polling(none_stop=True, interval=2, timeout=30)
    except Exception as e:
        print(f"Polling упал, перезапускаем через 5 сек: {e}")
        time.sleep(5)
