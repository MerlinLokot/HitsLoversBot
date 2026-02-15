import asyncio
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from database import Database
from questions import TestEngine
from valentines import (
    ValentinesManager, 
    get_valentine_menu_keyboard,
    get_anonymity_keyboard,
    get_photo_choice_keyboard
)

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: Токен бота не найден!")
    print("📝 Создайте файл .env с содержимым: BOT_TOKEN=ваш_токен")
    exit(1)

db = Database()
test_engine = TestEngine()

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class TestStates(StatesGroup):
    not_waiting = State()
    waiting_for_single_answer = State()
    waiting_for_multi_answer = State()


valentines_manager = ValentinesManager(bot, db.conn)

class ValentineStates(StatesGroup):
    waiting_for_recipient = State()
    waiting_for_message = State()
    waiting_for_photo = State()
    waiting_for_anonymity = State()

class CompatibilityStates(StatesGroup):
    waiting_for_username = State()

def create_options_keyboard(question_data, question_index):
    question_type = question_data['type']
    options = question_data['options']
    
    if question_type == 'single':
        buttons = [[KeyboardButton(text=f"{i+1}. {option}")] for i, option in enumerate(options)]
    else:
        buttons = []
        for i, option in enumerate(options):
            buttons.append([KeyboardButton(text=f"{i+1}. {option}")])
        buttons.append([KeyboardButton(text="✅ Далее")])

    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    return keyboard

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    #await broadcast_message()

    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    db.register_user(user_id, username, full_name)

    welcome_text = (
        f"👋 Привет, {full_name}!\n\n"
        f"Добро пожаловать в <b>HitsLoversBot</b>!\n\n"
        f"🎯 <b>Как это работает:</b>\n\n"
        f"📝 Здесь ты можешь пройти тест из {len(test_engine.questions)} вопросов, чтобы 14 февраля Бот мог определить совместимых с тобой людей!\n\n"
        f"💌 Кроме этого, уже сейчас ты можешь отправить праздничные валентинки людям, которые тоже активировали бота!\n\n"
        f"🔧 Техподдержка: @MerlinLokot"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "📝 Пройти тест")
async def start_test(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    db.register_user(user_id, username, full_name)
    
    await state.update_data(
        current_question=0,
        answers={}
    )

    question_data = test_engine.get_question(0)
    if not question_data:
        await message.answer("Ошибка загрузки вопросов.")
        return

    if question_data['type'] == 'single':
        await state.set_state(TestStates.waiting_for_single_answer)
    else:
        await state.set_state(TestStates.waiting_for_multi_answer)

    question_text = f"<b>Вопрос 1/{len(test_engine.questions)}</b>\n\n{question_data['text']}"
    keyboard = create_options_keyboard(question_data, 0)
    
    await message.answer(question_text, reply_markup=keyboard)

@dp.message(TestStates.waiting_for_single_answer)
async def process_single_answer(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    data = await state.get_data()
    current_q = data.get('current_question', 0)
    answers = data.get('answers', {})

    question_data = test_engine.get_question(current_q)
    if not question_data:
        await message.answer("Ошибка: вопрос не найден.")
        await state.clear()
        return

    answer_text = message.text.strip()
    
    try:
        if answer_text[0].isdigit():
            option_num = int(answer_text.split('.')[0]) - 1
        else:
            await message.answer("Пожалуйста, выберите вариант из списка.")
            return
    except (ValueError, IndexError):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return

    if option_num < 0 or option_num >= len(question_data['options']):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return

    answers[current_q] = [option_num]
    
    await state.update_data(answers=answers)

    await go_to_next_question(message, state, current_q, answers)

@dp.message(TestStates.waiting_for_multi_answer)
async def process_multi_answer(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    data = await state.get_data()
    current_q = data.get('current_question', 0)
    answers = data.get('answers', {})

    question_data = test_engine.get_question(current_q)

    answer_text = message.text.strip()

    if answer_text == "✅ Далее":
        if current_q not in answers or not answers[current_q]:
            await message.answer("Пожалуйста, выберите хотя бы один вариант перед тем как продолжить.")
            return

        await go_to_next_question(message, state, current_q, answers)
        return

    try:
        if answer_text[0].isdigit():
            option_num = int(answer_text.split('.')[0]) - 1
        else:
            await message.answer("Пожалуйста, выберите вариант из списка.")
            return
    except (ValueError, IndexError):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return

    if option_num < 0 or option_num >= len(question_data['options']):
        await message.answer("Пожалуйста, выберите вариант из списка.")
        return
    
    if current_q not in answers:
        answers[current_q] = []

    if option_num in answers[current_q]:
        answers[current_q].remove(option_num)
        action = "удалён"
    else:
        answers[current_q].append(option_num)
        action = "добавлен"

    await state.update_data(answers=answers)

    selected = answers.get(current_q, [])
    if selected:
        selected_text = ", ".join([f"{i+1}" for i in sorted(selected)])
        await message.answer(f"✅ Выбраны ответы с номерами: <b>{selected_text}</b>\n\n"
                           f"Вы можете выбрать ещё варианты или нажать '✅ Далее' чтобы продолжить")
    else:
        await message.answer("Вы пока не выбрали ни одного варианта\n"
                           f"Выберите ответы или нажмите '✅ Далее' чтобы пропустить вопрос")

async def go_to_next_question(message: types.Message, state: FSMContext, current_q, answers):
    user_id = message.from_user.id

    next_q = current_q + 1
    
    if next_q < len(test_engine.questions):
        await state.update_data(current_question=next_q)
        
        question_data = test_engine.get_question(next_q)
        if not question_data:
            await message.answer("Ошибка загрузки вопроса.")
            await state.clear()
            return

        if question_data['type'] == 'single':
            await state.set_state(TestStates.waiting_for_single_answer)
        else:
            await state.set_state(TestStates.waiting_for_multi_answer)

        question_text = f"<b>Вопрос {next_q+1}/{len(test_engine.questions)}</b>\n\n{question_data['text']}"
        if question_data['type'] == 'multi':
            question_text += " \n\n<b>(несколько вариантов ответа)</b>"
        
        keyboard = create_options_keyboard(question_data, next_q)
        
        await message.answer(question_text, reply_markup=keyboard)
    else:
        answers_json = test_engine.serialize_answers(answers)
        db.save_user_answers(user_id, answers_json)
        
        await state.clear()

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
    user_id = message.from_user.id
    
    answers_json = db.get_user_answers(user_id)
    
    if not answers_json:
        await message.answer(
            "Вы ещё не проходили тест. Нажмите '📝 Пройти тест' чтобы начать!",
            reply_markup=get_main_keyboard()
        )
        return

    answers_dict = test_engine.deserialize_answers(answers_json)

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

    
    await message.answer(text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "✨ Совместимость")
async def find_matches_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Получаем ответы пользователя
    answers_json = db.get_user_answers(user_id)
    
    if not answers_json:
        await message.answer(
            "Сначала пройдите тест, чтобы найти совместимых людей\n\n"
            "⚠️ Если же вы уже проходили тест, к сожалению, Бот не смог сохранить ваши ответы 😞 Но всё в порядке! Просто пройдите тест заново, и в этот раз результаты точно не пропадут!",
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

    user_answers = test_engine.deserialize_answers(answers_json)

    # Рассчитываем совместимость
    matches = []
    for other_user in all_users:
        if other_user['telegram_id'] == user_id:
            continue
        
        other_answers = test_engine.deserialize_answers(other_user['answers_json'])
        similarity = test_engine.calculate_similarity(user_answers, other_answers)
        
        matches.append({
            'telegram_id': other_user['telegram_id'],
            'username': other_user['username'],
            'full_name': other_user['full_name'],
            'similarity': similarity
        })

    # Сортируем по убыванию совместимости
    matches.sort(key=lambda x: x['similarity'], reverse=True)
    
    # Сохраняем в состояние для дальнейшего использования
    await state.update_data(matches_list=matches)

    if matches:
        # Создаём клавиатуру с двумя вариантами
        buttons = [
            [InlineKeyboardButton(text="🌟 ТОП совместимых", callback_data="show_top_matches")],
            [InlineKeyboardButton(text="🔮 Проверить совместимость с..", callback_data="check_specific_person")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        text = (
            "✨ <b>Отлично! Результаты тестов на совместимость проанализированы!</b>\n\n"
            "Выберите, что хотите сделать:"
        )
        
        await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(
            "😔 Пока не найдено пользователей для сравнения.\n\n"
            "Пригласите друзей пройти тест!",
            reply_markup=get_main_keyboard()
        )

@dp.callback_query(lambda c: c.data == "show_top_matches")
async def show_top_matches(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    data = await state.get_data()
    matches = data.get('matches_list', [])
    
    if not matches:
        await callback.message.edit_text(
            "❌ Данные не найдены. Попробуйте снова.",
            reply_markup=None
        )
        return
    
    text = "⚡ <b>Вау! Вот с какими людьми у тебя наибольшая совместимость! </b>\n\n"
    
    for i, match in enumerate(matches[:5], 1):
        percent = int(match['similarity'] * 100)
        
        # Визуальный прогресс-бар
        filled = "🟩" * (percent // 10)
        empty = "🟦" * (10 - (percent // 10))
        progress = f"{filled}{empty}"
        
        # Формируем имя
        if match.get('full_name'):
            name = match['full_name']
            if match.get('username'):
                name += f" (@{match['username']})"
        elif match.get('username'):
            name = f"@{match['username']}"
        else:
            name = f"Пользователь {match['telegram_id']}"
        
        # Медаль за место
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = "🌟"
        
        text += f"{medal} <b>{i}. {name}</b>\n"
        text += f"   <code>{progress}</code> <b>{percent}%</b>\n\n"
    
    text += "\n💫 Как здорово, когда есть люди, с которыми ты на одной волне!"
    
    # Кнопка для возврата
    buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_compatibility_menu")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text)

@dp.callback_query(lambda c: c.data == "check_specific_person")
async def ask_for_username(callback: CallbackQuery, state: FSMContext):
    """Запрашивает username для проверки совместимости"""
    await callback.answer()
    
    await state.set_state(CompatibilityStates.waiting_for_username)
    
    text = (
        "🔍 <b>Проверка совместимости</b>\n\n"
        "Введите <b>никнейм</b> получателя в Telegram:\n"
        "🚪 Отправьте /cancel чтобы отменить"
    )
    
    await callback.message.edit_text(text, reply_markup=None)

@dp.message(CompatibilityStates.waiting_for_username)
async def check_specific_person(message: types.Message, state: FSMContext):
    """Проверяет совместимость с конкретным пользователем"""
    username = message.text.strip()
    
    # Очищаем username
    clean_username = username[1:] if username.startswith('@') else username
    
    # Получаем данные пользователя
    target_user = db.get_user_by_username(clean_username)
    
    if not target_user:
        await message.answer(
            f"❌ Пользователь @{clean_username} не найден в базе.\n\n"
            "Убедитесь, что он зарегистрирован в боте и прошел тест.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        return
    
    # Получаем ответы текущего пользователя
    current_user_id = message.from_user.id
    current_answers_json = db.get_user_answers(current_user_id)
    
    if not current_answers_json:
        await message.answer(
            "❌ Сначала пройдите тест!",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        return
    
    # Получаем ответы целевого пользователя
    target_answers_json = db.get_user_answers(target_user['telegram_id'])
    
    if not target_answers_json:
        await message.answer(
            f"❌ Пользователь @{clean_username} ещё не прошел тест.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        return
    
    # Рассчитываем совместимость
    current_answers = test_engine.deserialize_answers(current_answers_json)
    target_answers = test_engine.deserialize_answers(target_answers_json)
    
    similarity = test_engine.calculate_similarity(current_answers, target_answers)
    percent = int(similarity * 100)
    
    # Визуальный прогресс-бар
    filled = "🟩" * (percent // 10)
    empty = "🟦" * (10 - (percent // 10))
    progress = f"{filled}{empty}"
    
    # Формируем имя
    if target_user.get('full_name'):
        name = target_user['full_name']
        if target_user.get('username'):
            name += f" (@{target_user['username']})"
    else:
        name = f"@{target_user['username']}"
    
    text = (
        f"<b>Результат совместимости!</b>\n\n"
        f"🌟 {name}\n\n"
        f"  <code>{progress}</code> <b>{percent}%</b>\n\n"
    )
    
    # Кнопки для действий
    buttons = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data="show_top_matches")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(text)
    await state.clear()

@dp.callback_query(lambda c: c.data == "back_to_compatibility_menu")
async def back_to_compatibility_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в меню совместимости"""
    await callback.answer()
    await state.clear()
    
    # Вызываем заново обработчик совместимости
    message = callback.message
    message.text = "✨ Совместимость"
    await find_matches_handler(message, state)

def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="📝 Пройти тест"), KeyboardButton(text="📊 Мои ответы")],
        [KeyboardButton(text="💌 Валентинки"), KeyboardButton(text="✨ Совместимость")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@dp.message(lambda message: message.text == "💌 Валентинки")
async def valentines_menu(message: types.Message):
    text = (
        "💝 <b>Отправка валентинок</b>\n\n"
        "Здесь ты можешь отправить анонимное или открытое "
        "поздравление пользователю, зарегистрированному в боте!\n\n"
        "✨ <b>Как это работает:</b>\n"
        "1️⃣ Введи никнейм получателя\n"
        "2️⃣ Напиши текст валентинки\n"
        "3️⃣ Добавь фото (по желанию)\n"
        "4️⃣ Выбери: анонимно или открыто\n\n"
    )

    buttons = [
        [InlineKeyboardButton(text="💌 Отправить валентинку", callback_data="send_valentine")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "back_to_valentines")
async def back_to_valentines(callback: CallbackQuery):
    await callback.answer()
    await valentines_menu(callback.message)

@dp.callback_query(lambda c: c.data == "send_valentine")
async def start_send_valentine(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ValentineStates.waiting_for_recipient)
    
    text = (
        "✏️ <b>Отправка валентинки - Шаг 1/4</b>\n\n"
        "Введите <b>никнейм</b> получателя в Telegram:\n"
        "⚠️ Получатель должен быть зарегистрирован в боте\n\n"
        "🚪 Отправьте /cancel чтобы отменить"
    )
    
    await callback.message.answer(text)

@dp.message(ValentineStates.waiting_for_recipient)
async def process_recipient(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "❌ Отправка отменена", 
            reply_markup=get_main_keyboard()
        )
        return
    
    username = message.text.strip()

    if not valentines_manager.validate_username(username):
        await message.answer(
            "❌ <b>Некорректный формат никнейма!</b>\n\n"
        )
        return
    
    if not db.is_registered(username):
        await message.answer(
            f"❌ Пользователь {username} не зарегистрирован в боте\n\n"
        )
        return

    await state.update_data(recipient_username=username)
    await state.set_state(ValentineStates.waiting_for_message)
    
    formatted_username = valentines_manager.format_username(username)
    await message.answer(
        f"✅ Получатель: <b>{formatted_username}</b>\n\n"
        f"📝 <b>Шаг 2/4</b> - Введите текст валентинки:"
    )

@dp.message(ValentineStates.waiting_for_message)
async def process_message_text(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отправка отменена", reply_markup=get_main_keyboard())
        return
    
    text = message.text.strip()
    
    if len(text) > 500:
        await message.answer("❌ Текст слишком длинный (максимум 500 символов). Сократите сообщение!")
        return

    await state.update_data(message_text=text)
    await state.set_state(ValentineStates.waiting_for_photo)
    
    buttons = [
        [InlineKeyboardButton(text="📸 Добавить фото", callback_data="add_photo")],
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="skip_photo")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        "📸 <b>Шаг 3/4</b> - Хотите добавить фото?\n\n"
        "Вы можете прикрепить изображение к валентинке!",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "add_photo")
async def add_photo(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ValentineStates.waiting_for_photo)
    await callback.message.answer(
        "📸 Отправьте фото, которое хотите прикрепить к валентинке, "
        "или нажмите 'Пропустить'"
    )

@dp.callback_query(lambda c: c.data == "skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(photo=None)
    await state.set_state(ValentineStates.waiting_for_anonymity)
    
    buttons = [
        [
            InlineKeyboardButton(text="🕵️ Анонимно", callback_data="send_anonymous"),
            InlineKeyboardButton(text="👤 Открыто", callback_data="send_open")
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_send")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.answer(
        "🕵️ <b>Шаг 4/4</b> - Выберите режим отправки:\n\n"
        "• <b>Анонимно</b> - получатель не узнает, кто отправитель\n"
        "• <b>Открыто</b> - получатель увидит ваше имя",
        reply_markup=keyboard
    )

@dp.message(ValentineStates.waiting_for_photo)
async def process_photo(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == "пропустить":
        await state.update_data(photo=None)
        await state.set_state(ValentineStates.waiting_for_anonymity)
        
        buttons = [
            [
                InlineKeyboardButton(text="🕵️ Анонимно", callback_data="send_anonymous"),
                InlineKeyboardButton(text="👤 Открыто", callback_data="send_open")
            ],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_send")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(
            "🕵️ <b>Шаг 4/4</b> - Выберите режим отправки:",
            reply_markup=keyboard
        )
        return
    
    if message.photo:
        await state.update_data(photo=message.photo)
        await state.set_state(ValentineStates.waiting_for_anonymity)
        
        buttons = [
            [
                InlineKeyboardButton(text="🕵️ Анонимно", callback_data="send_anonymous"),
                InlineKeyboardButton(text="👤 Открыто", callback_data="send_open")
            ],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_send")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(
            "✅ Фото добавлено!\n\n"
            "🕵️ <b>Шаг 4/4</b> - Выберите режим отправки:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            "❌ Пожалуйста, отправьте фото или нажмите 'Пропустить'"
        )

@dp.callback_query(lambda c: c.data == "send_anonymous")
async def send_anonymous_valentine(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_valentine(callback, state, is_anonymous=True)

@dp.callback_query(lambda c: c.data == "send_open")
async def send_open_valentine(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_valentine(callback, state, is_anonymous=False)

@dp.callback_query(lambda c: c.data == "cancel_send")
async def cancel_send_valentine(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "❌ Отправка валентинки отменена",
        reply_markup=None
    )

async def send_valentine(callback: CallbackQuery, state: FSMContext, is_anonymous: bool):
    try:
        data = await state.get_data()
        recipient_username = data.get('recipient_username')
        message_text = data.get('message_text')
        photo = data.get('photo')

        if photo:
            result = await valentines_manager.send_valentine_with_photo(
                sender_id=callback.from_user.id,
                recipient_username=recipient_username,
                message_text=message_text,
                photo=photo,
                is_anonymous=is_anonymous
            )
        else:
            result = await valentines_manager.send_valentine(
                sender_id=callback.from_user.id,
                recipient_username=recipient_username,
                message_text=message_text,
                is_anonymous=is_anonymous
            )
        
        await callback.message.edit_text(
            result['message'],
            reply_markup=None
        )

        if not result['success']:
            error_text = result['message']

            buttons = [
                [InlineKeyboardButton(text="💌 Попробовать снова", callback_data="send_valentine")]
            ]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(error_text, reply_markup=keyboard)
            return

        await state.clear()
    except Exception as e:
        await state.clear()
        await callback.message.edit_text(
            f"❌ Произошла ошибка при отправке: {str(e)}",
            reply_markup=None
        )

@dp.message(Command("broadcast"))
async def broadcast_message(message: types.Message):
    BATCH_SIZE = 20  # чуть меньше максимума для надежности
    DELAY = 1.1  # чуть больше секунды

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✍️ Пройти', url='https://docs.google.com/forms/d/e/1FAIpQLSf8Dzs-02Ke0USpKO6V1blKrJV7FGFjhzl9Q0gARa_DKL9L1g/viewform?usp=dialog')]
        ]
    )

    MESSAGE = (
        "🌟 Всем привет! "
        "Нам очень важно собрать вашу обратную связь по боту, "
        "поэтому можете, пожалуйста, пройти форму (она анонимна)"
    )

    users = await db.get_all_user_ids()
    
    print(f"Начинаю рассылку для {len(users)} пользователей")
    
    for i, user_id in enumerate(users, 1):
        try:
            await bot.send_message(user_id, MESSAGE, reply_markup=keyboard)
            print(f"✓ {i}/{len(users)}", end='\r')
            
            if i % BATCH_SIZE == 0:
                await asyncio.sleep(DELAY)
                
        except Exception as e:
            error_msg = f"Ошибка для {user_id}: {e}"
            print(f"\n{error_msg}")
    
    print(f"\n✅ Рассылка завершена!")

@dp.message()
async def handle_everything_else(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    if message.text and (
        message.text.startswith('/') or 
        message.text in ["📝 Пройти тест", "📊 Мои ответы", "💌 Валентинки", "✨ Совместимость"]
    ):
        return

    if not message.text:
        return
    
    await message.answer(
        "❌ Некорректный запрос.\n"
        "Пожалуйста, используйте кнопки меню или команду /start",
        reply_markup=get_main_keyboard()
    )


async def main():
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\nБот останавливается...")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())