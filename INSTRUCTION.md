# Инструкция по модификации бота для возврата ответов в формате JSON

## Цепочка рассуждений

### Текущее состояние
1. Бот получает сообщение от пользователя через Telegram
2. Отправляет запрос в DeepSeek API с историей диалога
3. Получает текстовый ответ от API
4. Отправляет ответ пользователю как есть

### Требуемое состояние
1. Бот получает сообщение от пользователя через Telegram
2. Отправляет запрос в DeepSeek API с инструкцией возвращать ответ строго в JSON формате
3. Получает JSON ответ с полями: `title`, `body`, `tags`
4. Валидирует и парсит JSON ответ
5. Форматирует ответ для пользователя в читаемом виде

## План изменений

### Шаг 1: Модификация системного сообщения
**Место:** Функция `get_deepseek_response()` в `bot.py`
- Изменить системное сообщение, чтобы оно инструктировало модель возвращать ответ строго в формате JSON
- Указать структуру: `{"title": "...", "body": "...", "tags": [...]}`

### Шаг 2: Добавление парсинга JSON
**Место:** Функция `get_deepseek_response()` в `bot.py`
- Добавить импорт модуля `json`
- После получения ответа от API попытаться распарсить JSON
- Обработать случаи, когда ответ не является валидным JSON

### Шаг 3: Валидация структуры JSON
**Место:** Новая функция `validate_json_response()` в `bot.py`
- Проверить наличие всех обязательных полей: `title`, `body`, `tags`
- Проверить типы данных:
  - `title` - строка
  - `body` - строка
  - `tags` - массив строк
- Вернуть валидированный словарь или None при ошибке

### Шаг 4: Форматирование ответа для пользователя
**Место:** Новая функция `format_response()` в `bot.py`
- Принять валидированный JSON словарь
- Создать читаемое форматирование:
  ```
  📌 [title]
  
  [body]
  
  🏷️ Теги: tag1, tag2, tag3
  ```
- Вернуть отформатированную строку

### Шаг 5: Обработка ошибок
**Место:** Функция `get_deepseek_response()` в `bot.py`
- Если JSON невалиден - попытаться извлечь JSON из ответа (если он обернут в markdown код)
- Если не удалось распарсить - вернуть сообщение об ошибке
- Если структура невалидна - вернуть сообщение об ошибке

## Детальная реализация

### Изменения в коде:

1. **Импорты:**
   ```python
   import json
   import re
   ```

2. **Новое системное сообщение:**
   ```python
   system_message = """Ты помощник, который всегда отвечает строго в формате JSON.
   Структура ответа должна быть следующей:
   {
       "title": "краткий заголовок ответа",
       "body": "основной текст ответа",
       "tags": ["тег1", "тег2", "тег3"]
   }
   
   Важно:
   - Ответ должен быть ВАЛИДНЫМ JSON
   - Не добавляй никакого текста до или после JSON
   - Поле "title" - краткий заголовок (до 100 символов)
   - Поле "body" - развернутый ответ на вопрос пользователя
   - Поле "tags" - массив строк с релевантными тегами (3-7 тегов)
   """
   ```

3. **Функция валидации:**
   ```python
   def validate_json_response(json_data: dict) -> dict | None:
       """Валидирует структуру JSON ответа"""
       required_fields = ['title', 'body', 'tags']
       
       for field in required_fields:
           if field not in json_data:
               logger.warning(f"Отсутствует обязательное поле: {field}")
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
   ```

4. **Функция извлечения JSON:**
   ```python
   def extract_json_from_response(response_text: str) -> dict | None:
       """Извлекает JSON из ответа, даже если он обернут в markdown"""
       # Пытаемся найти JSON в markdown блоке кода
       json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
       if json_match:
           try:
               return json.loads(json_match.group(1))
           except json.JSONDecodeError:
               pass
       
       # Пытаемся найти JSON напрямую
       json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
       if json_match:
           try:
               return json.loads(json_match.group(0))
           except json.JSONDecodeError:
               pass
       
       # Пытаемся распарсить весь ответ как JSON
       try:
           return json.loads(response_text.strip())
       except json.JSONDecodeError:
           return None
   ```

5. **Функция форматирования:**
   ```python
   def format_response(json_data: dict) -> str:
       """Форматирует JSON ответ для отправки пользователю"""
       title = json_data.get('title', 'Без заголовка')
       body = json_data.get('body', '')
       tags = json_data.get('tags', [])
       
       formatted = f"📌 {title}\n\n{body}"
       
       if tags:
           tags_str = ', '.join(tags)
           formatted += f"\n\n🏷️ Теги: {tags_str}"
       
       return formatted
   ```

6. **Модификация функции get_deepseek_response:**
   - Изменить системное сообщение
   - После получения ответа вызвать `extract_json_from_response()`
   - Валидировать через `validate_json_response()`
   - Отформатировать через `format_response()`
   - Обработать ошибки парсинга

## Ожидаемый результат

После изменений бот будет:
1. ✅ Всегда запрашивать ответ в формате JSON
2. ✅ Парсить и валидировать JSON ответ
3. ✅ Форматировать ответ в читаемый вид для пользователя
4. ✅ Обрабатывать ошибки парсинга gracefully

## Пример работы

**Входное сообщение пользователя:**
```
Что такое Python?
```

**Ответ от DeepSeek API (JSON):**
```json
{
    "title": "Python - язык программирования",
    "body": "Python - это высокоуровневый язык программирования...",
    "tags": ["python", "программирование", "язык"]
}
```

**Отформатированный ответ пользователю:**
```
📌 Python - язык программирования

Python - это высокоуровневый язык программирования...

🏷️ Теги: python, программирование, язык
```

