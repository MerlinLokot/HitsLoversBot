import logging
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Получаем токен бота
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: Токен бота не найден!")
    print("📝 Создайте файл .env с содержимым: BOT_TOKEN=ваш_токен")
    exit(1)

# Инициализируем бота с новым синтаксисом aiogram 3.7+
bot = Bot(
    token=TOKEN,
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

users1 = [{'first_name':"Саша", 'username':"MerlinLokot"}]

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Определение состояний
class SendStates(StatesGroup):
    waiting_for_message = State()

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# Сохранение пользователя в БД
def save_user(user_id: int, username: str, first_name: str, last_name: str = None):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

# Поиск пользователей в БД
def search_users(query: str, limit: int = 20):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    search_term = f"%{query}%"
    cursor.execute('''
        SELECT * FROM users 
        WHERE username LIKE ? 
           OR first_name LIKE ? 
           OR last_name LIKE ?
           OR (first_name || ' ' || COALESCE(last_name, '')) LIKE ?
        LIMIT ?
    ''', (search_term, search_term, search_term, search_term, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    users = []
    for row in rows:
        users.append({
            'user_id': row[0],
            'username': row[1],
            'first_name': row[2],
            'last_name': row[3],
        })
    return users

# Получение пользователя по ID
def get_user_by_id(user_id: int):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'user_id': row[0],
            'username': row[1],
            'first_name': row[2],
            'last_name': row[3]
        }
    return None

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Сохраняем пользователя в БД
    save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    
    await message.answer(
        "👋 Привет! Я бот для отправки сообщений.\n\n"
        "📝 Чтобы отправить сообщение:\n"
        "1. В любом чате начните вводить @ваш_бот\n"
        "2. Введите имя пользователя для поиска\n"
        "3. Выберите получателя из списка\n"
        "4. Напишите сообщение\n\n"
        "Или используйте команду /send"
    )

# Обработчик команды /send
@dp.message(Command("send"))
async def cmd_send(message: types.Message, state: FSMContext):
    await message.answer(
        "📨 Для отправки сообщения:\n"
        "1. В любом чате начните вводить @ваш_бот\n"
        "2. Поищите получателя по имени\n"
        "3. Выберите его из списка\n"
        "4. Напишите сообщение\n\n"
        "Или просто ответьте на это сообщение текстом, и я спрошу кому отправить."
    )
    
    # Сохраняем, что пользователь хочет отправить сообщение
    await state.set_state(SendStates.waiting_for_message)

# Обработчик inline запросов (главная фича!)
@dp.inline_query()
async def handle_inline_query(inline_query: InlineQuery):
    query = inline_query.query.strip()
    results = []
    
    # Если запрос пустой - показываем последних пользователей
    if not query:
        users = search_users("", limit=10)
    else:
        # Ищем по запросу
        users = search_users(query, limit=15)
    
    for user in users:
        # Формируем красивое имя для отображения
        display_name = user['first_name']
        if user['last_name']:
            display_name += f" {user['last_name']}"
        
        # Описание с username
        description = f"@{user['username']}" if user['username'] else "Без username"
        
        # Создаем результат inline запроса
        result = InlineQueryResultArticle(
            id=str(user['user_id']),
            title=display_name,
            description=description,
            input_message_content=InputTextMessageContent(
                message_text=f"👤 Выбран: {display_name}\n"
                f"📧 Введите сообщение для этого пользователя:"
            ),
            # Иконка пользователя
            thumbnail_url="https://cdn-icons-png.flaticon.com/512/1077/1077114.png",
            thumbnail_width=48,
            thumbnail_height=48
        )
        results.append(result)
    
    # Если нет результатов
    if not results:
        result = InlineQueryResultArticle(
            id="no_results",
            title="Пользователи не найдены",
            description="Попробуйте другой запрос",
            input_message_content=InputTextMessageContent(
                message_text="По вашему запросу пользователи не найдены."
            )
        )
        results.append(result)
    
    # Отправляем результаты
    await inline_query.answer(results, cache_time=1, is_personal=True)

# Обработчик текстовых сообщений (когда пользователь выбрал получателя и пишет сообщение)
@dp.message(lambda message: message.text and "Выбран:" in message.text)
async def handle_selected_user(message: types.Message, state: FSMContext):
    # Парсим сообщение с выбранным пользователем
    lines = message.text.split('\n')
    if len(lines) < 1:
        return
    
    # Извлекаем имя пользователя из первой строки
    selected_line = lines[0]
    user_display_name = selected_line.replace("Выбран: ", "").strip()
    
    # Сохраняем в состоянии, что пользователь выбрал получателя
    await state.update_data(
        recipient_display_name=user_display_name,
        waiting_for_message_text=True
    )
    
    # Просим ввести сообщение
    await message.answer(
        f"✅ Получатель: {user_display_name}\n"
        f"✏️ Теперь введите текст сообщения:"
    )

# Обработчик ввода сообщения после выбора получателя
@dp.message(lambda message: message.text and not message.text.startswith('/'))
async def handle_message_text(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    # Проверяем, выбрал ли пользователь получателя через inline
    if 'recipient_display_name' in user_data:
        recipient_name = user_data['recipient_display_name']
        
        # Ищем пользователя по отображаемому имени
        users = search_users(recipient_name, limit=1)
        
        if users:
            recipient = users[0]
            
            try:
                # Отправляем сообщение получателю
                await bot.send_message(
                    chat_id=recipient['user_id'],
                    text=f"📬 Новое сообщение!\n\n"
                         f"От: @{message.from_user.username or message.from_user.first_name}\n"
                         f"Текст: {message.text}"
                )
                
                # Подтверждаем отправителю
                await message.answer(
                    f"✅ Сообщение отправлено {recipient_name}!\n"
                    f"ID получателя: {recipient['user_id']}"
                )
                
            except Exception as e:
                logger.error(f"Ошибка отправки: {e}")
                await message.answer(
                    f"❌ Не удалось отправить сообщение.\n"
                    f"Возможно, пользователь заблокировал бота."
                )
        else:
            await message.answer("❌ Получатель не найден. Попробуйте снова.")
        
        # Очищаем состояние
        await state.clear()

# Обработчик всех сообщений для сохранения пользователей
@dp.message()
async def save_user_handler(message: types.Message):
    # Сохраняем всех пользователей, которые пишут боту
    save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )

async def main():
    print("=" * 50)
    print("🤖 Valentine Bot запускается...")
    print("=" * 50)

    init_db()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())