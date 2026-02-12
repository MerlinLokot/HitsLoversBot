import asyncio
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Импортируем модули
from database import Database
from questions import TestEngine

# Загружаем переменные окружения
load_dotenv()

# Получаем токен бота
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: Токен бота не найден!")
    print("📝 Создайте файл .env с содержимым: BOT_TOKEN=ваш_токен")
    exit(1)

# Инициализируем базу данных и движок теста
db = Database()
test_engine = TestEngine()

# Инициализируем бота
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== СОСТОЯНИЯ (FSM) ==========
class TestStates(StatesGroup):
    waiting_for_single_answer = State()  # Для вопросов с одним ответом
    waiting_for_multi_answer = State()   # Для вопросов с несколькими ответами

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    """Основная клавиатура после регистрации"""
    buttons = [
        [KeyboardButton(text="📝 Пройти тест")],
        [KeyboardButton(text="📊 Мои ответы")] #KeyboardButton(text="🔍 Найти пару")],
        #[KeyboardButton(text="❓ Инфо")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def create_options_keyboard(question_data, question_index):
    """Создаем клавиатуру с вариантами ответов"""
    question_type = question_data['type']
    options = question_data['options']
    
    if question_type == 'single':
        # Для одиночного выбора - одна кнопка на каждый вариант
        buttons = [[KeyboardButton(text=f"{i+1}. {option}")] for i, option in enumerate(options)]
    else:  # 'multi'
        # Для множественного выбора - кнопки плюс "Далее"
        buttons = []
        for i, option in enumerate(options):
            buttons.append([KeyboardButton(text=f"{i+1}. {option}")])
        buttons.append([KeyboardButton(text="✅ Далее")])
    
    # Добавляем номер вопроса в заголовок
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    return keyboard

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # Регистрируем пользователя
    db.register_user(user_id, username, full_name)
    
    # Приветственное сообщение
    welcome_text = (
        f"👋 Привет, {full_name}!\n\n"
        f"Добро пожаловать в <b>тест на совместимость</b>!\n\n"
        f"🎯 <b>Как это работает:</b>\n"
        f"Пройди тест из {len(test_engine.questions)} вопросов, чтобы Бот мог определить совместимых с тобой людей 14 февраля!\n\n"
        f"📝 <b>Инструкция:</b>\n"
        f"• Выбирай варианты, которые тебе подходят\n"
        f"• Для вопросов с несколькими вариантами можно указать несколько, последовательно выбрав их, после чего нажать '✅ Далее', чтобы перейти к следующему вопросу\n\n"
        f"Готов начать? Нажми '📝 Пройти тест'!"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "📝 Пройти тест")
async def start_test(message: types.Message, state: FSMContext):
    """Начало теста"""
    user_id = message.from_user.id
    
    # Проверяем, не начат ли уже тест
    current_state = await state.get_state()
    if current_state:
        await message.answer("Тест уже начат. Продолжайте отвечать на вопросы.")
        return
    
    # Начинаем с первого вопроса
    await state.update_data(
        current_question=0,
        answers={}
    )
    
    # Получаем первый вопрос
    question_data = test_engine.get_question(0)
    if not question_data:
        await message.answer("Ошибка загрузки вопросов.")
        return
    
    # Устанавливаем состояние в зависимости от типа вопроса
    if question_data['type'] == 'single':
        await state.set_state(TestStates.waiting_for_single_answer)
    else:
        await state.set_state(TestStates.waiting_for_multi_answer)
    
    # Отправляем первый вопрос
    question_text = f"<b>Вопрос 1/{len(test_engine.questions)}</b>\n\n{question_data['text']}"
    keyboard = create_options_keyboard(question_data, 0)
    
    await message.answer(question_text, reply_markup=keyboard)

@dp.message(TestStates.waiting_for_single_answer)
async def process_single_answer(message: types.Message, state: FSMContext):
    """Обработка ответа на вопрос с одним вариантом"""
    user_id = message.from_user.id
    
    # Получаем текущие данные
    data = await state.get_data()
    current_q = data.get('current_question', 0)
    answers = data.get('answers', {})
    
    # Проверяем ответ
    question_data = test_engine.get_question(current_q)
    if not question_data:
        await message.answer("Ошибка: вопрос не найден.")
        await state.clear()
        return
    
    # Парсим ответ (пользователь выбрал "1. Вариант" или просто "1")
    answer_text = message.text.strip()
    
    # Извлекаем номер варианта
    try:
        if answer_text[0].isdigit():
            option_num = int(answer_text.split('.')[0]) - 1
        else:
            await message.answer("Пожалуйста, выберите вариант из списка.")
            return
    except (ValueError, IndexError):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return
    
    # Проверяем валидность номера
    if option_num < 0 or option_num >= len(question_data['options']):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return
    
    # Сохраняем ответ
    answers[current_q] = [option_num]
    
    # Обновляем состояние
    await state.update_data(answers=answers)
    
    # Переходим к следующему вопросу или завершаем
    await go_to_next_question(message, state, current_q, answers)

@dp.message(TestStates.waiting_for_multi_answer)
async def process_multi_answer(message: types.Message, state: FSMContext):
    """Обработка ответа на вопрос с несколькими вариантами"""
    user_id = message.from_user.id
    
    # Получаем текущие данные
    data = await state.get_data()
    current_q = data.get('current_question', 0)
    answers = data.get('answers', {})
    
    # Получаем вопрос
    question_data = test_engine.get_question(current_q)
    if not question_data:
        await message.answer("Ошибка: вопрос не найден.")
        await state.clear()
        return
    
    answer_text = message.text.strip()
    
    # Если пользователь нажал "Далее"
    if answer_text == "✅ Далее":
        # Проверяем, что выбрал хотя бы один вариант
        if current_q not in answers or not answers[current_q]:
            await message.answer("Пожалуйста, выберите хотя бы один вариант перед тем как продолжить.")
            return
        
        # Переходим к следующему вопросу
        await go_to_next_question(message, state, current_q, answers)
        return
    
    # Парсим выбранный вариант
    try:
        if answer_text[0].isdigit():
            option_num = int(answer_text.split('.')[0]) - 1
        else:
            await message.answer("Пожалуйста, выберите вариант из списка.")
            return
    except (ValueError, IndexError):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return
    
    # Проверяем валидность
    if option_num < 0 or option_num >= len(question_data['options']):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return
    
    # Инициализируем список ответов для этого вопроса, если нужно
    if current_q not in answers:
        answers[current_q] = []
    
    # Добавляем или удаляем вариант (переключение)
    if option_num in answers[current_q]:
        answers[current_q].remove(option_num)
        action = "удалён"
    else:
        answers[current_q].append(option_num)
        action = "добавлен"
    
    # Сохраняем обновленные ответы
    await state.update_data(answers=answers)
    
    # Показываем текущий выбор
    selected = answers.get(current_q, [])
    if selected:
        selected_text = ", ".join([f"{i+1}" for i in sorted(selected)])
        await message.answer(f"✅ Выбраны ответы с номерами: <b>{selected_text}</b>\n\n"
                           f"Вы можете выбрать ещё варианты или нажать '✅ Далее' чтобы продолжить")
    else:
        await message.answer("Вы пока не выбрали ни одного варианта\n"
                           f"Выберите ответы или нажмите '✅ Далее' чтобы пропустить вопрос")

async def go_to_next_question(message: types.Message, state: FSMContext, current_q, answers):
    """Переход к следующему вопросу или завершение теста"""
    user_id = message.from_user.id
    
    # Проверяем, есть ли ещё вопросы
    next_q = current_q + 1
    
    if next_q < len(test_engine.questions):
        # Переходим к следующему вопросу
        await state.update_data(current_question=next_q)
        
        question_data = test_engine.get_question(next_q)
        if not question_data:
            await message.answer("Ошибка загрузки вопроса.")
            await state.clear()
            return
        
        # Устанавливаем состояние в зависимости от типа вопроса
        if question_data['type'] == 'single':
            await state.set_state(TestStates.waiting_for_single_answer)
        else:
            await state.set_state(TestStates.waiting_for_multi_answer)
        
        # Отправляем следующий вопрос
        question_text = f"<b>Вопрос {next_q+1}/{len(test_engine.questions)}</b>\n\n{question_data['text']}"
        if question_data['type'] == 'multi':
            question_text += " \n\n<b>(несколько вариантов ответа)</b>"
        
        keyboard = create_options_keyboard(question_data, next_q)
        
        await message.answer(question_text, reply_markup=keyboard)
    else:
        # Тест завершён
        # Сохраняем ответы в базу данных
        answers_json = test_engine.serialize_answers(answers)
        db.save_user_answers(user_id, answers_json)
        
        await state.clear()
        
        # Поздравляем с завершением
        congrats_text = (
            "🎉 <b>Поздравляю! Ты завершил тест!</b>\n\n"
            f"Твои ответы сохранены и могут быть использованы для анализа совместимости\n\n"
            f"Теперь ты можешь:\n"
            f"• 📊 Посмотреть свои ответы\n"
            f"• 📝 Перепройти тест\n"
            f"• 💝 Ждать подбора совместимых людей 14 февраля!\n\n"
        )
        
        await message.answer(congrats_text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "📊 Мои ответы")
async def show_my_answers(message: types.Message):
    """Показываем ответы пользователя"""
    user_id = message.from_user.id
    
    answers_json = db.get_user_answers(user_id)
    
    if not answers_json:
        await message.answer(
            "Вы ещё не проходили тест. Нажмите '📝 Пройти тест' чтобы начать!",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Десериализуем ответы
    answers_dict = test_engine.deserialize_answers(answers_json)
    
    # Формируем текст с ответами
    text = "📋 <b>Ваши ответы:</b>\n\n"
    
    for q_index, q_data in enumerate(test_engine.questions):
        selected = answers_dict.get(q_index, [])
        text += f"<b>{q_index+1}. {q_data['text']}</b>\n"
        
        if selected:
            options_text = []
            for opt_idx in selected:
                if opt_idx < len(q_data['options']):
                    options_text.append(q_data['options'][opt_idx])
            
            if q_data['type'] == 'single':
                text += f"✅ {options_text[0]}\n\n"
            else:
                text += f"✅ {', '.join(options_text)}\n\n"
        else:
            text += "❌ Нет ответа\n\n"
    
    #text += f"📊 <b>Всего вопросов:</b> {len(test_engine.questions)}\n"
    #text += f"✅ <b>Отвечено:</b> {len(answers_dict)}"
    
    await message.answer(text, reply_markup=get_main_keyboard())

#@dp.message(lambda message: message.text == "🔍 Найти пару")
async def find_matches_handler(message: types.Message):
    """Поиск похожих пользователей"""
    user_id = message.from_user.id
    
    # Получаем ответы текущего пользователя
    answers_json = db.get_user_answers(user_id)
    
    if not answers_json:
        await message.answer(
            "Сначала пройдите тест, чтобы найти похожих людей!",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Получаем всех пользователей с ответами
    all_users = db.get_all_users_with_answers()
    
    if len(all_users) < 2:
        await message.answer(
            "Пока недостаточно пользователей для поиска совпадений.\n"
            "Пригласи друзей пройти тест!",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Десериализуем ответы текущего пользователя
    user_answers = test_engine.deserialize_answers(answers_json)
    
    # Ищем совпадения
    matches = []
    for other_user in all_users:
        if other_user['telegram_id'] == user_id:
            continue  # Пропускаем себя
        
        other_answers = test_engine.deserialize_answers(other_user['answers_json'])
        similarity = test_engine.calculate_similarity(user_answers, other_answers)
        
        matches.append({
            'telegram_id': other_user['telegram_id'],
            'username': other_user['username'],
            'full_name': other_user['full_name'],
            'similarity': similarity
        })
    
    # Сортируем по схожести
    matches.sort(key=lambda x: x['similarity'], reverse=True)
    
    # Формируем результат
    if matches:
        text = "👥 <b>Найденные совпадения:</b>\n\n"
        
        for i, match in enumerate(matches[:5]):  # Показываем топ-5
            percent = int(match['similarity'] * 100)
            name = match['full_name'] or match['username'] or f"Пользователь {match['telegram_id']}"
            text += f"{i+1}. <b>{name}</b> - {percent}% совпадения\n"
        
        text += f"\n📊 <b>Всего найдено:</b> {len(matches)} человек"
        text += f"\n\n💡 <i>Совпадение считается от 60% и выше</i>"
    else:
        text = "😔 Пока не найдено пользователей с высокой схожестью.\n\n"
        text += "Попробуйте позже или пригласите больше друзей пройти тест!"
    
    await message.answer(text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "❓ Инфо")
async def cmd_help(message: types.Message):
    """Команда помощи"""
    help_text = (
        "📝 <b>Пройти тест</b> - начать тест на совместимость\n"
        "📊 <b>Мои ответы</b> - посмотреть список ваших последниъ ответов\n"
        "❓ <b>Как проходить тест:</b>\n"
        "• Для вопросов с одним вариантом ответа - выберите только один из них\n"
        "• Для вопросов с несколькими вариантами - можно выбрать несколько\n"
        "• В вопросах с несколькими вариантами нажмите '✅ Далее' чтобы продолжить\n\n"
        "🎯 <b>День X</b>\n"
        "14 февраля вы сможете найти людей, совместимых с вами\n"
        "по результатам теста \n"
    )
    await message.answer(help_text, reply_markup=get_main_keyboard())

# ========== ЗАПУСК БОТА ==========
async def main():
    print("=" * 50)
    print("🧠 Психологический тест бот запускается...")
    print("=" * 50)
    
    # Показываем статистику
    user_count = db.count_users()
    print(f"👥 Зарегистрировано пользователей: {user_count}")
    print(f"📝 Вопросов в тесте: {len(test_engine.questions)}")
    print("✅ Бот готов к работе!")
    print("⏳ Ожидаю сообщений...")
    print("=" * 50)
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот останавливается...")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    finally:
        db.close()
        print("✅ Соединение с базой данных закрыто")

if __name__ == "__main__":
    asyncio.run(main())