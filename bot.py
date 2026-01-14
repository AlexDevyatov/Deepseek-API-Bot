#!/usr/bin/env python3
"""
Телеграм-бот, использующий DeepSeek API для ответов
"""

import os
import logging
import traceback
import time
import json
import re
from typing import Optional
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError
from telegram import Update
from telegram.error import TelegramError, NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def load_tokens():
    """
    Загружает токены из файла tokens.txt
    
    Returns:
        dict: Словарь с токенами
    """
    tokens = {}
    tokens_file = "tokens.txt"
    
    if not os.path.exists(tokens_file):
        raise FileNotFoundError(
            f"Файл {tokens_file} не найден! "
            f"Создайте файл {tokens_file} с содержимым:\n"
            f"DEEPSEEK_API_KEY=your_deepseek_api_key\n"
            f"TELEGRAM_BOT_TOKEN=your_telegram_bot_token"
        )
    
    with open(tokens_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                tokens[key.strip()] = value.strip()
    
    return tokens


# Загружаем токены
try:
    tokens = load_tokens()
    DEEPSEEK_API_KEY = tokens.get('DEEPSEEK_API_KEY')
    TELEGRAM_BOT_TOKEN = tokens.get('TELEGRAM_BOT_TOKEN')
    
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY не найден в tokens.txt")
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не найден в tokens.txt")
except (FileNotFoundError, ValueError) as e:
    logger.error(str(e))
    raise

# Конфигурация
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Системное сообщение по умолчанию для модели
DEFAULT_SYSTEM_MESSAGE = """Ты помощник, который собирает информацию в процессе диалога и выдает финальный результат.

ТВОЯ ЗАДАЧА:
1. В процессе общения с пользователем собирай информацию и требования
2. Задавай уточняющие вопросы, если информации недостаточно
3. Когда у тебя будет достаточно информации для формирования финального результата - САМОСТОЯТЕЛЬНО выдай финальный результат
4. Финальный результат должен быть полным и структурированным (например, ТЗ, план проекта, анализ и т.д.)

ФОРМАТ ОТВЕТА (всегда строго JSON):
{
    "is_final": true или false,
    "title": "краткий заголовок ответа",
    "body": "основной текст ответа",
    "tags": ["тег1", "тег2", "тег3"]
}

ПРАВИЛА:
- "is_final": 
  * false - если это промежуточный ответ, уточняющий вопрос или сбор информации
  * true - если это ФИНАЛЬНЫЙ результат (например, готовое ТЗ, план, анализ)
  * ТЫ САМ определяешь, когда достаточно информации для финального результата
  * Когда выдаешь финальный результат (is_final: true), в "body" помести ПОЛНЫЙ структурированный результат

- "title": краткий заголовок (до 100 символов)
- "body": 
  * Если is_final=false: ответ на вопрос, уточнение или запрос дополнительной информации
  * Если is_final=true: ПОЛНЫЙ финальный результат (например, готовое ТЗ со всеми разделами)
- "tags": массив строк с релевантными тегами (3-7 тегов)

ВАЖНО:
- Ответ должен быть ВАЛИДНЫМ JSON
- Не добавляй никакого текста до или после JSON
- САМОСТОЯТЕЛЬНО определяй момент, когда можно выдать финальный результат
- Финальный результат должен быть полным и готовым к использованию
"""

# Создаем клиент DeepSeek
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# Хранилище истории диалогов для каждого пользователя
user_conversations = {}

# Хранилище ID сообщений бота для каждого пользователя (для возможности удаления)
user_bot_messages = {}


def extract_json_from_response(response_text: str) -> Optional[dict]:
    """
    Извлекает JSON из ответа, даже если он обернут в markdown
    
    Args:
        response_text: Текст ответа от API
    
    Returns:
        Словарь с данными или None при ошибке парсинга
    """
    # Пытаемся найти JSON в markdown блоке кода
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            logger.debug(f"Не удалось распарсить JSON из markdown блока: {e}")
    
    # Пытаемся найти JSON напрямую (первое вхождение {...})
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            logger.debug(f"Не удалось распарсить найденный JSON: {e}")
    
    # Пытаемся распарсить весь ответ как JSON
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError as e:
        logger.debug(f"Не удалось распарсить весь ответ как JSON: {e}")
        return None


def validate_json_response(json_data: dict) -> Optional[dict]:
    """
    Валидирует структуру JSON ответа
    
    Args:
        json_data: Словарь с данными JSON
    
    Returns:
        Валидированный словарь или None при ошибке валидации
    """
    required_fields = ['is_final', 'title', 'body', 'tags']
    
    for field in required_fields:
        if field not in json_data:
            logger.warning(f"Отсутствует обязательное поле: {field}")
            return None
    
    if not isinstance(json_data['is_final'], bool):
        logger.warning("Поле 'is_final' должно быть булевым значением")
        return None
    
    if not isinstance(json_data['title'], str):
        logger.warning("Поле 'title' должно быть строкой")
        return None
    
    if not isinstance(json_data['body'], str):
        logger.warning("Поле 'body' должно быть строкой")
        return None
    
    if not isinstance(json_data['tags'], list):
        logger.warning("Поле 'tags' должно быть массивом")
        return None
    
    if not all(isinstance(tag, str) for tag in json_data['tags']):
        logger.warning("Все элементы 'tags' должны быть строками")
        return None
    
    return json_data


def format_response(json_data: dict) -> str:
    """
    Форматирует JSON ответ для отправки пользователю
    
    Args:
        json_data: Валидированный словарь с данными
    
    Returns:
        Отформатированная строка для отправки пользователю
    """
    is_final = json_data.get('is_final', False)
    title = json_data.get('title', 'Без заголовка')
    body = json_data.get('body', '')
    tags = json_data.get('tags', [])
    
    # Если это финальный результат, добавляем специальную пометку
    if is_final:
        formatted = f"✅ ФИНАЛЬНЫЙ РЕЗУЛЬТАТ\n\n📌 {title}\n\n{body}"
    else:
        formatted = f"📌 {title}\n\n{body}"
    
    if tags:
        tags_str = ', '.join(tags)
        formatted += f"\n\n🏷️ Теги: {tags_str}"
    
    return formatted


def get_deepseek_response(user_id: int, user_message: str, system_message: str = None, max_retries: int = 3):
    """
    Отправляет сообщение в DeepSeek API и возвращает ответ в формате JSON
    Поддерживает историю диалога для каждого пользователя
    
    Args:
        user_id: ID пользователя Telegram
        user_message: Сообщение пользователя
        system_message: Системное сообщение (если None, используется стандартное)
        max_retries: Максимальное количество попыток при временных ошибках
    
    Returns:
        tuple: (json_string, formatted_response, is_final) при успехе, где:
            - json_string: JSON строка с данными ответа
            - formatted_response: Отформатированный ответ для пользователя
            - is_final: Булево значение, указывающее является ли ответ финальным результатом
        str: Сообщение об ошибке при неудаче
    """
    # Используем стандартное системное сообщение, если не указано другое
    if system_message is None:
        system_message = DEFAULT_SYSTEM_MESSAGE
    
    # Получаем историю диалога для пользователя
    if user_id not in user_conversations:
        user_conversations[user_id] = [
            {"role": "system", "content": system_message}
        ]
    
    # Добавляем сообщение пользователя в историю
    user_conversations[user_id].append({"role": "user", "content": user_message})
    
    for attempt in range(max_retries):
        try:
            # Отправляем запрос с историей
            response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=user_conversations[user_id],
                stream=False,
                temperature=0.1,  # Температура 0.1 для детерминированных ответов
                timeout=30.0  # Таймаут 30 секунд
            )
            
            assistant_message = response.choices[0].message.content
            
            # Пытаемся извлечь и валидировать JSON из ответа
            json_data = extract_json_from_response(assistant_message)
            
            if json_data is None:
                logger.warning(f"Не удалось извлечь JSON из ответа. Ответ: {assistant_message[:200]}...")
                # Сохраняем оригинальный ответ в историю для контекста
                user_conversations[user_id].append({"role": "assistant", "content": assistant_message})
                return "⚠️ Ошибка: ответ от AI не является валидным JSON. Попробуйте переформулировать запрос."
            
            # Валидируем структуру JSON
            validated_data = validate_json_response(json_data)
            
            if validated_data is None:
                logger.warning(f"JSON не прошел валидацию. Данные: {json_data}")
                # Сохраняем оригинальный ответ в историю для контекста
                user_conversations[user_id].append({"role": "assistant", "content": assistant_message})
                return "⚠️ Ошибка: ответ от AI не соответствует требуемой структуре. Попробуйте переформулировать запрос."
            
            # Форматируем ответ для пользователя
            formatted_response = format_response(validated_data)
            
            # Логируем финальный результат
            if validated_data.get('is_final', False):
                logger.info(f"Пользователь {user_id} получил финальный результат: {validated_data.get('title', 'Без заголовка')}")
            
            # Сохраняем оригинальный JSON ответ в историю для контекста
            user_conversations[user_id].append({"role": "assistant", "content": assistant_message})
            
            # Ограничиваем историю последними 20 сообщениями (чтобы не превышать лимиты токенов)
            if len(user_conversations[user_id]) > 20:
                # Оставляем системное сообщение и последние 19 сообщений
                user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-19:]
            
            # Возвращаем кортеж: (JSON строка, отформатированный ответ, is_final)
            json_string = json.dumps(validated_data, ensure_ascii=False, indent=2)
            return (json_string, formatted_response, validated_data.get('is_final', False))
        
        except RateLimitError as e:
            logger.warning(f"Rate limit ошибка (попытка {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Экспоненциальная задержка
                logger.info(f"Ожидание {wait_time} секунд перед повтором...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Превышен лимит запросов после {max_retries} попыток")
                # Удаляем последнее сообщение пользователя из истории, так как оно не было обработано
                if user_conversations[user_id] and user_conversations[user_id][-1]["role"] == "user":
                    user_conversations[user_id].pop()
                return "⚠️ Превышен лимит запросов к API. Пожалуйста, подождите немного и попробуйте снова."
        
        except APITimeoutError as e:
            logger.warning(f"Таймаут API (попытка {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"Ожидание {wait_time} секунд перед повтором...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Таймаут после {max_retries} попыток")
                if user_conversations[user_id] and user_conversations[user_id][-1]["role"] == "user":
                    user_conversations[user_id].pop()
                return "⏱️ Превышено время ожидания ответа от API. Пожалуйста, попробуйте еще раз."
        
        except APIConnectionError as e:
            logger.warning(f"Ошибка подключения к API (попытка {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"Ожидание {wait_time} секунд перед повтором...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Ошибка подключения после {max_retries} попыток")
                if user_conversations[user_id] and user_conversations[user_id][-1]["role"] == "user":
                    user_conversations[user_id].pop()
                return "🔌 Ошибка подключения к API. Проверьте интернет-соединение и попробуйте снова."
        
        except APIError as e:
            logger.error(f"Ошибка API DeepSeek: {str(e)}")
            if user_conversations[user_id] and user_conversations[user_id][-1]["role"] == "user":
                user_conversations[user_id].pop()
            error_code = getattr(e, 'status_code', None)
            if error_code == 401:
                return "🔑 Ошибка аутентификации API. Проверьте правильность API ключа."
            elif error_code == 429:
                return "⚠️ Превышен лимит запросов. Пожалуйста, подождите немного."
            elif error_code == 500:
                return "🔧 Временная ошибка сервера API. Попробуйте позже."
            else:
                return f"❌ Ошибка API (код {error_code}): {str(e)}"
        
        except Exception as e:
            logger.error(f"Неожиданная ошибка при обращении к DeepSeek API: {str(e)}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            if user_conversations[user_id] and user_conversations[user_id][-1]["role"] == "user":
                user_conversations[user_id].pop()
            return f"❌ Произошла неожиданная ошибка: {str(e)}"
    
    # Если все попытки исчерпаны
    if user_conversations[user_id] and user_conversations[user_id][-1]["role"] == "user":
        user_conversations[user_id].pop()
    return "❌ Не удалось обработать запрос после нескольких попыток. Пожалуйста, попробуйте позже."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    welcome_message = (
        "👋 Привет! Я бот, использующий DeepSeek API для ответов.\n\n"
        "Просто отправь мне сообщение, и я отвечу!\n\n"
        "Доступные команды:\n"
        "/start - показать это сообщение\n"
        "/clear - очистить историю диалога\n"
        "/delete_all - удалить все мои сообщения\n"
        "/help - показать справку"
    )
    sent_message = await update.message.reply_text(welcome_message)
    
    # Сохраняем ID сообщения бота
    if user_id not in user_bot_messages:
        user_bot_messages[user_id] = []
    user_bot_messages[user_id].append(sent_message.message_id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    user_id = update.effective_user.id
    help_message = (
        "📖 Справка по боту:\n\n"
        "Я использую DeepSeek AI для ответов на ваши вопросы.\n"
        "Просто напишите мне любое сообщение, и я постараюсь помочь!\n\n"
        "Команды:\n"
        "/start - начать работу с ботом\n"
        "/clear - очистить историю нашего диалога\n"
        "/delete_all - удалить все мои сообщения из чата\n"
        "/help - показать эту справку"
    )
    sent_message = await update.message.reply_text(help_message)
    
    # Сохраняем ID сообщения бота
    if user_id not in user_bot_messages:
        user_bot_messages[user_id] = []
    user_bot_messages[user_id].append(sent_message.message_id)


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /clear - очищает историю диалога"""
    user_id = update.effective_user.id
    if user_id in user_conversations:
        del user_conversations[user_id]
        sent_message = await update.message.reply_text("✅ История диалога очищена!")
    else:
        sent_message = await update.message.reply_text("История диалога уже пуста.")
    
    # Сохраняем ID сообщения бота
    if user_id not in user_bot_messages:
        user_bot_messages[user_id] = []
    user_bot_messages[user_id].append(sent_message.message_id)


async def delete_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /delete_all - удаляет все сообщения бота"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id not in user_bot_messages or not user_bot_messages[user_id]:
        await update.message.reply_text("Нет сообщений для удаления.")
        return
    
    deleted_count = 0
    failed_count = 0
    
    # Удаляем все сохраненные сообщения бота
    for message_id in user_bot_messages[user_id]:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            deleted_count += 1
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {message_id}: {str(e)}")
            failed_count += 1
    
    # Очищаем список сообщений
    user_bot_messages[user_id] = []
    
    # Отправляем сообщение о результате (которое тоже будет сохранено)
    result_message = await update.message.reply_text(
        f"✅ Удалено сообщений: {deleted_count}"
        + (f"\n⚠️ Не удалось удалить: {failed_count}" if failed_count > 0 else "")
    )
    
    # Сохраняем ID этого сообщения
    user_bot_messages[user_id].append(result_message.message_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user_id = update.effective_user.id
        user_message = update.message.text
        
        logger.info(f"Получено сообщение от пользователя {user_id}: {user_message}")
        
        # Отправляем индикатор "печатает..."
        try:
            await update.message.reply_chat_action(action="typing")
        except (TelegramError, NetworkError, TimedOut) as e:
            logger.warning(f"Не удалось отправить chat_action: {str(e)}")
            # Продолжаем выполнение, это не критично
        
        # Получаем ответ от DeepSeek
        response = get_deepseek_response(user_id, user_message)
        
        # Отправляем ответ пользователю
        try:
            # Проверяем, является ли ответ кортежем (успешный ответ) или строкой (ошибка)
            if isinstance(response, tuple):
                # Поддерживаем как старый формат (2 элемента), так и новый (3 элемента)
                if len(response) == 3:
                    json_string, formatted_response, is_final = response
                else:
                    json_string, formatted_response = response
                    is_final = False
                
                # Сначала отправляем JSON
                json_message = await update.message.reply_text(f"```json\n{json_string}\n```", parse_mode='Markdown')
                
                # Сохраняем ID сообщения с JSON
                if user_id not in user_bot_messages:
                    user_bot_messages[user_id] = []
                user_bot_messages[user_id].append(json_message.message_id)
                
                # Затем отправляем отформатированный ответ
                formatted_message = await update.message.reply_text(formatted_response)
                
                # Сохраняем ID сообщения с отформатированным ответом
                user_bot_messages[user_id].append(formatted_message.message_id)
                
                # Если это финальный результат, можно предложить очистить историю
                if is_final:
                    logger.info(f"Финальный результат отправлен пользователю {user_id}")
            else:
                # Это сообщение об ошибке (строка)
                sent_message = await update.message.reply_text(response)
                
                # Сохраняем ID сообщения бота
                if user_id not in user_bot_messages:
                    user_bot_messages[user_id] = []
                user_bot_messages[user_id].append(sent_message.message_id)
        except (TelegramError, NetworkError, TimedOut) as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {str(e)}")
            # Пытаемся отправить сообщение об ошибке
            try:
                await update.message.reply_text(
                    "❌ Не удалось отправить ответ. Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                logger.error("Не удалось отправить даже сообщение об ошибке")
    
    except Exception as e:
        logger.error(f"Критическая ошибка в handle_message: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        if update and update.message:
            try:
                await update.message.reply_text(
                    "❌ Произошла критическая ошибка при обработке сообщения. Пожалуйста, попробуйте позже."
                )
            except Exception:
                logger.error("Не удалось отправить сообщение об ошибке")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    error = context.error
    
    # Логируем детали ошибки
    logger.error("=" * 60)
    logger.error(f"Ошибка в обработчике: {type(error).__name__}")
    logger.error(f"Сообщение об ошибке: {str(error)}")
    logger.error(f"Трассировка: {traceback.format_exc()}")
    
    if update:
        logger.error(f"Update ID: {update.update_id}")
        if update.effective_user:
            logger.error(f"User ID: {update.effective_user.id}")
        if update.effective_chat:
            logger.error(f"Chat ID: {update.effective_chat.id}")
        if update.message:
            logger.error(f"Message text: {update.message.text}")
    logger.error("=" * 60)
    
    # Обработка специфических ошибок Telegram
    if isinstance(error, TimedOut):
        logger.warning("Таймаут при работе с Telegram API")
        if update and update.message:
            try:
                await update.message.reply_text(
                    "⏱️ Превышено время ожидания. Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                logger.error("Не удалось отправить сообщение об ошибке таймаута")
        return
    
    if isinstance(error, NetworkError):
        logger.warning("Ошибка сети при работе с Telegram API")
        if update and update.message:
            try:
                await update.message.reply_text(
                    "🔌 Ошибка сети. Пожалуйста, проверьте соединение и попробуйте снова."
                )
            except Exception:
                logger.error("Не удалось отправить сообщение об ошибке сети")
        return
    
    if isinstance(error, TelegramError):
        logger.error(f"Ошибка Telegram API: {str(error)}")
        if update and update.message:
            try:
                await update.message.reply_text(
                    "⚠️ Ошибка при работе с Telegram. Пожалуйста, попробуйте позже."
                )
            except Exception:
                logger.error("Не удалось отправить сообщение об ошибке Telegram")
        return
    
    # Общая обработка ошибок
    if update and update.message:
        try:
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз."
            )
        except Exception:
            logger.error("Не удалось отправить сообщение об общей ошибке")


def main():
    """Основная функция для запуска бота"""
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("delete_all", delete_all_messages))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен и готов к работе!")
    print("\n" + "="*60)
    print("🤖 Телеграм-бот запущен!")
    print("="*60)
    print("Нажмите Ctrl+C для остановки\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

