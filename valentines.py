from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, Dict, List
import asyncio
import re

import psycopg
from psycopg.rows import dict_row

class ValentinesManager:
    def __init__(self, bot: Bot, db_connection):
        """
        Инициализация менеджера валентинок
        bot: экземпляр бота для отправки сообщений
        db_connection: экземпляр вашего класса Database
        """
        self.bot = bot
        self.cursor = db_connection.cursor(row_factory=psycopg.rows.dict_row)
    
    async def send_valentine(self, sender_id: int, recipient_username: str, 
                            message_text: str, image_url: Optional[str] = None,
                            is_anonymous: bool = False) -> Dict:
        """
        Отправляет валентинку пользователю по никнейму
        Возвращает словарь с результатом операции
        """
        result = {
            'success': False,
            'error': None,
            'recipient': None,
            'message': None
        }
        
        try:
            # Очищаем username от @
            if recipient_username.startswith('@'):
                clean_username = recipient_username[1:]
            else:
                clean_username = recipient_username
            
            # Проверяем, зарегистрирован ли пользователь в боте
            self.cursor.execute('''
                SELECT id, telegram_id, username, full_name 
                FROM users 
                WHERE username = %s OR username = %s
            ''', (clean_username, f"@{clean_username}"))
            
            recipient = self.cursor.fetchone()
            
            if not recipient:
                result['error'] = 'user_not_found'
                result['message'] = f"❌ Пользователь @{clean_username} не зарегистрирован в боте"
                return result
            
            recipient_id = recipient['telegram_id']
            
            # Формируем сообщение
            if is_anonymous:
                sender_name = "👤 Анонимный отправитель"
            else:
                # Получаем имя отправителя
                self.cursor.execute('''
                    SELECT full_name, username FROM users WHERE telegram_id = %s
                ''', (sender_id,))
                sender = self.cursor.fetchone()
                if sender:
                    sender_name = f"@{sender['username']}"
                else:
                    sender_name = f"Пользователь {sender_id}"
            
            # Создаем красивое оформление валентинки
            valentine_text = (
                f"💌 <i><b>Тебе прислали валентинку!</b></i> 💌\n\n"
                f"<b>От кого:</b> {sender_name}\n"
                f"<b>Сообщение:</b>\n"
                f"«{message_text}»\n\n"
            )
            
            # Отправляем сообщение
            if image_url:
                try:
                    await self.bot.send_photo(
                        chat_id=recipient_id,
                        photo=image_url,
                        caption=valentine_text,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    # Если не получается отправить фото, отправляем текст
                    await self.bot.send_message(
                        chat_id=recipient_id,
                        text=valentine_text,
                        parse_mode='HTML'
                    )
            else:
                await self.bot.send_message(
                    chat_id=recipient_id,
                    text=valentine_text,
                    parse_mode='HTML'
                )
            
            # Отправляем подтверждение отправителю
            confirm_text = (
                f"<i><b>Ваше сообщение доставлено!</b></i> 💝\n\n"
                f"<b>Получатель:</b> @{clean_username}\n"
                f"<b>Анонимно:</b> {'Да' if is_anonymous else 'Нет'}\n\n"
            )
            
            await self.bot.send_message(
                chat_id=sender_id,
                text=confirm_text,
                parse_mode='HTML'
            )
            
            result['success'] = True
            result['recipient'] = {
                'id': recipient_id,
                'username': clean_username,
                'full_name': recipient['full_name']
            }
            result['message'] = confirm_text
            
            print(f"💌 Валентинка отправлена: {sender_id} -> @{clean_username}")
            return result
            
        except Exception as e:
            error_msg = f"❌ Ошибка при отправке валентинки: {str(e)}"
            print(error_msg)
            
            # Уведомляем отправителя об ошибке
            try:
                await self.bot.send_message(
                    chat_id=sender_id,
                    text=error_msg,
                    parse_mode='HTML'
                )
            except:
                pass
            
            result['error'] = 'unknown'
            result['message'] = error_msg
            return result
    
    async def send_valentine_with_photo(self, sender_id: int, recipient_username: str,
                                       message_text: str, photo,
                                       is_anonymous: bool = False) -> Dict:
        """
        Отправляет валентинку с фотографией
        """
        # Получаем file_id фотографии самого высокого качества
        if isinstance(photo, list):
            photo_file_id = photo[-1].file_id
        else:
            photo_file_id = photo.file_id
        
        return await self.send_valentine(
            sender_id=sender_id,
            recipient_username=recipient_username,
            message_text=message_text,
            image_url=photo_file_id,
            is_anonymous=is_anonymous
        )
    
    def validate_username(self, username: str) -> bool:
        """
        Проверяет корректность формата username
        """
        if not username:
            return False
        
        # Убираем @ если есть
        clean_name = username[1:] if username.startswith('@') else username
        
        # Проверяем формат Telegram username
        # Допустимые символы: a-z, 0-9, _, минимум 5 символов
        pattern = r'^[a-zA-Z0-9_]{5,32}$'
        return bool(re.match(pattern, clean_name))
    
    def format_username(self, username: str) -> str:
        """Приводит username к единому формату"""
        clean = username.strip()
        if clean.startswith('@'):
            return clean
        return f"@{clean}"


# ========== КЛАВИАТУРЫ ДЛЯ ВАЛЕНТИНОК ==========

def get_valentine_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для главного меню валентинок"""
    buttons = [
        [
            InlineKeyboardButton(
                text="💌 Отправить", 
                callback_data="send_valentine"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_anonymity_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора анонимности"""
    buttons = [
        [
            InlineKeyboardButton(
                text="👤 Анонимно", 
                callback_data="send_anonymous"
            ),
            InlineKeyboardButton(
                text="🙍‍♂️ Открыто", 
                callback_data="send_open"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Отмена", 
                callback_data="cancel_send"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_photo_choice_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора - добавлять фото или нет"""
    buttons = [
        [
            InlineKeyboardButton(
                text="📸 Добавить фото", 
                callback_data="add_photo"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏩ Пропустить", 
                callback_data="skip_photo"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Отмена", 
                callback_data="cancel_send"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)