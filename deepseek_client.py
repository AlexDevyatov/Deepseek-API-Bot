#!/usr/bin/env python3
"""
Простой скрипт для отправки запросов в DeepSeek API
"""

import os
from openai import OpenAI


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
            f"DEEPSEEK_API_KEY=your_deepseek_api_key"
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
    API_KEY = tokens.get('DEEPSEEK_API_KEY')
    
    if not API_KEY:
        raise ValueError("DEEPSEEK_API_KEY не найден в tokens.txt")
except (FileNotFoundError, ValueError) as e:
    print(f"Ошибка: {e}")
    raise

BASE_URL = "https://api.deepseek.com"

# Создаем клиент
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def send_message(user_message: str, system_message: str = "You are a helpful assistant."):
    """
    Отправляет сообщение в DeepSeek API и возвращает ответ
    
    Args:
        user_message: Сообщение пользователя
        system_message: Системное сообщение (по умолчанию)
    
    Returns:
        Ответ от API
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            stream=False
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        return f"Ошибка при отправке запроса: {str(e)}"


def main():
    """Основная функция для интерактивного использования"""
    print("=" * 50)
    print("DeepSeek API Client")
    print("=" * 50)
    print("Введите 'quit' или 'exit' для выхода\n")
    
    while True:
        user_input = input("Вы: ")
        
        if user_input.lower() in ['quit', 'exit', 'выход']:
            print("До свидания!")
            break
        
        if not user_input.strip():
            continue
        
        print("\nDeepSeek: ", end="", flush=True)
        response = send_message(user_input)
        print(response)
        print()


if __name__ == "__main__":
    # Пример использования
    print("Пример запроса:")
    print("-" * 50)
    response = send_message("Привет! Расскажи о себе кратко.")
    print(f"Вопрос: Привет! Расскажи о себе кратко.")
    print(f"Ответ: {response}")
    print("-" * 50)
    print()
    
    # Запуск интерактивного режима
    main()

