#!/usr/bin/env python3
"""
Телеграм-бот, использующий DeepSeek API для ответов
"""

import os
import logging
from openai import OpenAI
from telegram import Update
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

# Создаем клиент DeepSeek
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# Хранилище истории диалогов для каждого пользователя
user_conversations = {}


def get_deepseek_response(user_id: int, user_message: str, system_message: str = "You are a helpful assistant."):
    """
    Отправляет сообщение в DeepSeek API и возвращает ответ
    Поддерживает историю диалога для каждого пользователя
    
    Args:
        user_id: ID пользователя Telegram
        user_message: Сообщение пользователя
        system_message: Системное сообщение
    
    Returns:
        Ответ от API
    """
    try:
        # Получаем историю диалога для пользователя
        if user_id not in user_conversations:
            user_conversations[user_id] = [
                {"role": "system", "content": system_message}
            ]
        
        # Добавляем сообщение пользователя в историю
        user_conversations[user_id].append({"role": "user", "content": user_message})
        
        # Отправляем запрос с историей
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=user_conversations[user_id],
            stream=False
        )
        
        assistant_message = response.choices[0].message.content
        
        # Добавляем ответ ассистента в историю
        user_conversations[user_id].append({"role": "assistant", "content": assistant_message})
        
        # Ограничиваем историю последними 20 сообщениями (чтобы не превышать лимиты токенов)
        if len(user_conversations[user_id]) > 20:
            # Оставляем системное сообщение и последние 19 сообщений
            user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-19:]
        
        return assistant_message
    
    except Exception as e:
        logger.error(f"Ошибка при обращении к DeepSeek API: {str(e)}")
        return f"Извините, произошла ошибка при обработке запроса: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_message = (
        "👋 Привет! Я бот, использующий DeepSeek API для ответов.\n\n"
        "Просто отправь мне сообщение, и я отвечу!\n\n"
        "Доступные команды:\n"
        "/start - показать это сообщение\n"
        "/clear - очистить историю диалога\n"
        "/help - показать справку"
    )
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_message = (
        "📖 Справка по боту:\n\n"
        "Я использую DeepSeek AI для ответов на ваши вопросы.\n"
        "Просто напишите мне любое сообщение, и я постараюсь помочь!\n\n"
        "Команды:\n"
        "/start - начать работу с ботом\n"
        "/clear - очистить историю нашего диалога\n"
        "/help - показать эту справку"
    )
    await update.message.reply_text(help_message)


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /clear - очищает историю диалога"""
    user_id = update.effective_user.id
    if user_id in user_conversations:
        del user_conversations[user_id]
        await update.message.reply_text("✅ История диалога очищена!")
    else:
        await update.message.reply_text("История диалога уже пуста.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    logger.info(f"Получено сообщение от пользователя {user_id}: {user_message}")
    
    # Отправляем индикатор "печатает..."
    await update.message.reply_chat_action(action="typing")
    
    # Получаем ответ от DeepSeek
    response = get_deepseek_response(user_id, user_message)
    
    # Отправляем ответ пользователю
    await update.message.reply_text(response)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.message:
        await update.message.reply_text(
            "Извините, произошла ошибка. Попробуйте еще раз."
        )


def main():
    """Основная функция для запуска бота"""
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
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

