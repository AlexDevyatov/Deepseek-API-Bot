# DeepSeek API Bot

Телеграм-бот, использующий DeepSeek API для ответов на вопросы пользователей.

## Описание

Этот проект включает в себя:
- **Telegram бот** (`bot.py`) - интерактивный бот для Telegram, который отвечает на сообщения пользователей используя DeepSeek AI
- **CLI клиент** (`deepseek_client.py`) - простой консольный клиент для работы с DeepSeek API

## Возможности

### Telegram бот
- 💬 Отвечает на сообщения пользователей через DeepSeek AI
- 📝 Поддерживает историю диалога для каждого пользователя
- 🧹 Команда `/clear` для очистки истории диалога
- 📖 Команды `/start` и `/help` для справки

### CLI клиент
- 🖥️ Интерактивный режим для общения с DeepSeek AI
- 📋 Пример использования при запуске

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/AlexDevyatov/Deepseek-API-Bot.git
cd Deepseek-API-Bot
```

2. Создайте виртуальное окружение (рекомендуется):
```bash
python3 -m venv .venv
source .venv/bin/activate  # На Windows: .venv\Scripts\activate
```

3. Установите зависимости:
```bash
pip install openai python-telegram-bot
```

4. Создайте файл `tokens.txt` в корне проекта:
```
DEEPSEEK_API_KEY=your_deepseek_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

### Получение токенов

**DeepSeek API ключ:**
1. Зарегистрируйтесь на [DeepSeek Platform](https://platform.deepseek.com/)
2. Перейдите в раздел [API Keys](https://platform.deepseek.com/api_keys)
3. Создайте новый API ключ

**Telegram Bot Token:**
1. Найдите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен

## Использование

### Запуск Telegram бота

```bash
python bot.py
```

Бот начнет принимать сообщения от пользователей в Telegram.

### Запуск CLI клиента

```bash
python deepseek_client.py
```

После запуска вы сможете вводить сообщения и получать ответы от DeepSeek AI. Для выхода введите `quit`, `exit` или `выход`.

## Структура проекта

```
.
├── bot.py                 # Telegram бот
├── deepseek_client.py     # CLI клиент для DeepSeek API
├── .gitignore            # Игнорируемые файлы
└── README.md             # Документация
```

## Зависимости

- `openai>=1.0.0` - для работы с DeepSeek API (совместим с OpenAI SDK)
- `python-telegram-bot>=20.0` - для работы с Telegram Bot API

## API DeepSeek

Проект использует [DeepSeek API](https://api-docs.deepseek.com/), который совместим с OpenAI API форматом. Используется модель `deepseek-chat` (DeepSeek-V3.2).

## Лицензия

Этот проект создан в образовательных целях.

## Автор

AlexDevyatov

