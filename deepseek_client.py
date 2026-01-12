#!/usr/bin/env python3
"""
Простой скрипт для отправки запросов в DeepSeek API
"""

import os
from openai import OpenAI

# API ключ
API_KEY = "sk-ca44e59da3804de68a0435bb15e57631"
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

