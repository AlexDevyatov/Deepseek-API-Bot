#!/usr/bin/env python3
"""
Телеграм-бот для эксперимента "День 4. Разные способы рассуждения"
Сравнивает разные подходы к решению задач с помощью DeepSeek API
"""

import os
import logging
import traceback
import time
import json
import re
import requests
import io
from typing import Optional, Dict, List, Tuple
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

# Создаем клиент DeepSeek
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# Хранилище активных экспериментов для каждого пользователя
user_experiments = {}


def call_deepseek_api(messages: List[Dict], max_retries: int = 3, temperature: float = 0.7) -> Optional[str]:
    """
    Вызывает DeepSeek API с обработкой ошибок
    
    Args:
        messages: Список сообщений для API
        max_retries: Максимальное количество попыток
        temperature: Температура для генерации
    
    Returns:
        Ответ от API или None при ошибке
    """
    for attempt in range(max_retries):
        try:
            response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                stream=False,
                temperature=temperature,
                timeout=120.0  # Увеличено до 120 секунд для сложных задач
            )
            return response.choices[0].message.content
        except RateLimitError as e:
            logger.warning(f"Rate limit ошибка (попытка {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                time.sleep(wait_time)
                continue
            return None
        except (APITimeoutError, APIConnectionError) as e:
            logger.warning(f"Ошибка подключения (попытка {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                time.sleep(wait_time)
                continue
            return None
        except APIError as e:
            logger.error(f"Ошибка API: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {str(e)}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            return None
    
    return None


def render_latex_to_image(latex_formula: str) -> Optional[io.BytesIO]:
    """
    Конвертирует LaTeX формулу в изображение
    
    Args:
        latex_formula: LaTeX формула (без $ или $$)
    
    Returns:
        BytesIO объект с изображением или None при ошибке
    """
    try:
        # Убираем лишние пробелы и экранируем специальные символы
        formula = latex_formula.strip()
        if not formula:
            logger.warning("Пустая формула")
            return None
        
        logger.debug(f"Рендеринг LaTeX формулы: {formula[:50]}...")
        
        # Вариант 1: CodeCogs API (самый надежный)
        formula_encoded = requests.utils.quote(formula)
        
        # Пробуем разные варианты CodeCogs
        codecogs_urls = [
            f"https://latex.codecogs.com/svg.latex?{formula_encoded}",  # SVG (лучшее качество)
            f"https://latex.codecogs.com/png.latex?\\dpi{{300}}\\bg{{white}} {formula_encoded}",  # PNG с параметрами
            f"https://latex.codecogs.com/png.latex?{formula_encoded}",  # Простой PNG
        ]
        
        for url in codecogs_urls:
            try:
                img_response = requests.get(url, timeout=20, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                if img_response.status_code == 200:
                    content = img_response.content
                    # Проверяем, что получили изображение (не HTML страницу с ошибкой)
                    if len(content) > 100 and not content.startswith(b'<'):
                        logger.debug(f"Успешно получено изображение с {url[:50]}...")
                        return io.BytesIO(content)
            except Exception as e:
                logger.debug(f"Ошибка при запросе {url[:50]}...: {str(e)}")
                continue
        
        # Вариант 2: QuickLaTeX API
        try:
            url = "https://quicklatex.com/latex3.f"
            data = {
                'formula': formula,
                'fsize': '20px',
                'fcolor': '000000',
                'mode': '0',
                'out': '1',
                'remhost': 'quicklatex.com'
            }
            
            response = requests.post(url, data=data, timeout=20, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                if len(lines) >= 2 and lines[0] == '0':  # 0 означает успех
                    image_url = lines[1]
                    img_response = requests.get(image_url, timeout=20)
                    if img_response.status_code == 200 and len(img_response.content) > 100:
                        logger.debug("Успешно получено изображение с QuickLaTeX")
                        return io.BytesIO(img_response.content)
        except Exception as e:
            logger.debug(f"Ошибка QuickLaTeX: {str(e)}")
        
        # Вариант 3: iTeX2MML через MathJax API (если доступен)
        try:
            # Используем MathJax Node API через публичный сервис
            mathjax_url = f"https://api.mathml.cloud/api/v1/formula?formula={formula_encoded}"
            img_response = requests.get(mathjax_url, timeout=20)
            if img_response.status_code == 200 and len(img_response.content) > 100:
                logger.debug("Успешно получено изображение с MathML API")
                return io.BytesIO(img_response.content)
        except Exception as e:
            logger.debug(f"Ошибка MathML API: {str(e)}")
        
        logger.warning(f"Не удалось отрендерить LaTeX формулу: {formula[:100]}")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка при рендеринге LaTeX: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None


def find_latex_formulas(text: str) -> List[Tuple[str, int, int]]:
    """
    Находит LaTeX формулы в тексте
    
    Args:
        text: Текст для поиска формул
    
    Returns:
        Список кортежей (formula, start_pos, end_pos) для каждой найденной формулы
    """
    formulas = []
    used_positions = set()  # Отслеживаем уже использованные позиции
    
    # Ищем формулы в формате $$...$$ (блочные формулы)
    pattern_block_dollar = r'\$\$([^$]+)\$\$'
    for match in re.finditer(pattern_block_dollar, text, re.DOTALL):
        start, end = match.start(), match.end()
        if start not in used_positions:
            formulas.append((match.group(1).strip(), start, end))
            used_positions.update(range(start, end))
    
    # Ищем формулы в формате \[...\] (блочные формулы LaTeX)
    pattern_block_bracket = r'\\\[([^\]]+?)\\\]'
    for match in re.finditer(pattern_block_bracket, text, re.DOTALL):
        start, end = match.start(), match.end()
        if not any(start <= pos < end for pos in used_positions):
            formulas.append((match.group(1).strip(), start, end))
            used_positions.update(range(start, end))
    
    # Ищем формулы в формате $...$ (инлайн формулы)
    pattern_inline_dollar = r'\$([^$\n]+?)\$'
    for match in re.finditer(pattern_inline_dollar, text):
        start, end = match.start(), match.end()
        # Проверяем, что это не часть блочной формулы
        if not any(start <= pos < end for pos in used_positions):
            formulas.append((match.group(1).strip(), start, end))
            used_positions.update(range(start, end))
    
    # Ищем формулы в формате \(...\) (инлайн формулы LaTeX)
    pattern_inline_paren = r'\\\(([^\)]+?)\\\)'
    for match in re.finditer(pattern_inline_paren, text):
        start, end = match.start(), match.end()
        if not any(start <= pos < end for pos in used_positions):
            formulas.append((match.group(1).strip(), start, end))
            used_positions.update(range(start, end))
    
    # Сортируем по позиции начала
    formulas.sort(key=lambda x: x[1])
    
    logger.debug(f"Найдено формул в тексте: {len(formulas)}")
    return formulas


async def send_message_with_latex(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """
    Отправляет сообщение с поддержкой LaTeX формул
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота
        text: Текст сообщения с возможными LaTeX формулами
    """
    formulas = find_latex_formulas(text)
    
    if not formulas:
        # Нет формул, отправляем обычный текст
        max_length = 4000
        if len(text) <= max_length:
            await update.message.reply_text(text)
        else:
            parts = []
            current_part = ""
            for line in text.split('\n'):
                if len(current_part) + len(line) + 1 > max_length:
                    if current_part:
                        parts.append(current_part)
                    current_part = line + '\n'
                else:
                    current_part += line + '\n'
            if current_part:
                parts.append(current_part)
            
            for part in parts:
                await update.message.reply_text(part)
                time.sleep(0.3)
        return
    
    # Есть формулы, обрабатываем их
    logger.info(f"Найдено формул: {len(formulas)}")
    last_pos = 0
    parts = []
    
    for formula, start, end in formulas:
        # Добавляем текст до формулы
        if start > last_pos:
            parts.append(('text', text[last_pos:start]))
        
        # Рендерим формулу
        logger.debug(f"Попытка отрендерить формулу: {formula[:50]}...")
        image = render_latex_to_image(formula)
        if image:
            logger.info(f"Формула успешно отрендерена: {formula[:50]}...")
            parts.append(('image', (image, formula)))
        else:
            # Если не удалось отрендерить, отправляем как текст с пометкой
            logger.warning(f"Не удалось отрендерить формулу, отправляем как текст: {formula[:50]}...")
            # Отправляем формулу в читаемом виде
            parts.append(('text', f"\\[{formula}\\]"))
        
        last_pos = end
    
    # Добавляем оставшийся текст
    if last_pos < len(text):
        parts.append(('text', text[last_pos:]))
    
    # Отправляем части
    current_text = ""
    for part_type, content in parts:
        if part_type == 'text':
            if content.strip():
                current_text += content
        elif part_type == 'image':
            # Отправляем накопленный текст, если есть
            if current_text.strip():
                if len(current_text) > 4000:
                    text_lines = current_text.split('\n')
                    for line in text_lines:
                        if len(line) > 4000:
                            chunks = [line[i:i+4000] for i in range(0, len(line), 4000)]
                            for chunk in chunks:
                                await update.message.reply_text(chunk)
                                time.sleep(0.3)
                        elif line.strip():
                            await update.message.reply_text(line)
                            time.sleep(0.3)
                else:
                    await update.message.reply_text(current_text)
                    time.sleep(0.3)
                current_text = ""
            
            # Отправляем изображение формулы
            image_io, formula_text = content
            try:
                image_io.seek(0)
                # Проверяем, что это действительно изображение
                image_data = image_io.read()
                if len(image_data) < 100:
                    raise ValueError("Изображение слишком маленькое")
                image_io.seek(0)
                await update.message.reply_photo(photo=image_io)
                logger.info(f"Изображение формулы успешно отправлено: {formula_text[:50]}...")
            except Exception as e:
                logger.error(f"Ошибка при отправке изображения LaTeX: {str(e)}")
                logger.error(f"Трассировка: {traceback.format_exc()}")
                # Отправляем формулу как текст с правильным форматированием
                try:
                    await update.message.reply_text(f"\\[{formula_text}\\]", parse_mode='MarkdownV2')
                except:
                    # Если MarkdownV2 не работает, отправляем как обычный текст
                    await update.message.reply_text(f"Формула: {formula_text}")
            time.sleep(0.3)
    
    # Отправляем оставшийся текст
    if current_text.strip():
        if len(current_text) > 4000:
            chunks = [current_text[i:i+4000] for i in range(0, len(current_text), 4000)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
                time.sleep(0.3)
        else:
            await update.message.reply_text(current_text)


def method1_direct_answer(task: str) -> Dict[str, str]:
    """
    Метод 1: Прямой ответ модели
    
    Args:
        task: Текст задачи
    
    Returns:
        Словарь с результатом метода
    """
    messages = [
        {
            "role": "system",
            "content": "Ты опытный решатель задач. Дай прямой и четкий ответ на задачу."
        },
        {
            "role": "user",
            "content": f"Реши следующую задачу:\n\n{task}"
        }
    ]
    
    response = call_deepseek_api(messages, temperature=0.7)
    
    return {
        "method": "Прямой ответ",
        "description": "Модель дает ответ напрямую без дополнительных инструкций",
        "response": response or "Ошибка при получении ответа"
    }


def method2_step_by_step(task: str) -> Dict[str, str]:
    """
    Метод 2: Пошаговое решение
    
    Args:
        task: Текст задачи
    
    Returns:
        Словарь с результатом метода
    """
    messages = [
        {
            "role": "system",
            "content": "Ты опытный решатель задач. Решай задачи пошагово, объясняя каждый шаг."
        },
        {
            "role": "user",
            "content": f"Реши следующую задачу пошагово:\n\n{task}\n\nРешай пошагово."
        }
    ]
    
    response = call_deepseek_api(messages, temperature=0.7)
    
    return {
        "method": "Пошаговое решение",
        "description": "Модель решает задачу пошагово с инструкцией 'решай пошагово'",
        "response": response or "Ошибка при получении ответа"
    }


def method3_ai_prompt(task: str) -> Dict[str, str]:
    """
    Метод 3: Промпт от другого ИИ
    
    Args:
        task: Текст задачи
    
    Returns:
        Словарь с результатом метода
    """
    # Сначала просим другой ИИ составить промпт
    prompt_creation_messages = [
        {
            "role": "system",
            "content": "Ты эксперт по созданию эффективных промптов для решения задач. Создай оптимальный промпт для решения задачи."
        },
        {
            "role": "user",
            "content": f"Создай эффективный промпт для решения следующей задачи:\n\n{task}\n\nПромпт должен быть четким и направлять на правильное решение."
        }
    ]
    
    prompt_response = call_deepseek_api(prompt_creation_messages, temperature=0.8)
    
    if not prompt_response:
        return {
            "method": "Промпт от другого ИИ",
            "description": "Другой ИИ создает промпт для решения задачи",
            "prompt_created": "Ошибка при создании промпта",
            "response": "Не удалось создать промпт"
        }
    
    # Теперь используем созданный промпт для решения задачи
    solution_messages = [
        {
            "role": "system",
            "content": "Ты опытный решатель задач. Следуй инструкциям в промпте."
        },
        {
            "role": "user",
            "content": f"{prompt_response}\n\nТеперь реши задачу:\n\n{task}"
        }
    ]
    
    solution_response = call_deepseek_api(solution_messages, temperature=0.7)
    
    return {
        "method": "Промпт от другого ИИ",
        "description": "Другой ИИ создает промпт для решения задачи",
        "prompt_created": prompt_response,
        "response": solution_response or "Ошибка при получении ответа"
    }


def method4_expert_panel(task: str) -> Dict[str, str]:
    """
    Метод 4: Группа экспертов
    
    Args:
        task: Текст задачи
    
    Returns:
        Словарь с результатом метода
    """
    experts = [
        {
            "name": "Логик",
            "role": "Эксперт по логическому мышлению и дедукции",
            "approach": "анализирует задачу с точки зрения логики и дедуктивного рассуждения"
        },
        {
            "name": "Математик",
            "role": "Эксперт по математике и численным методам",
            "approach": "применяет математические методы и численные вычисления"
        },
        {
            "name": "Аналитик",
            "role": "Эксперт по анализу и структурированию информации",
            "approach": "разбивает задачу на части и анализирует каждую деталь"
        }
    ]
    
    expert_responses = []
    
    for expert in experts:
        messages = [
            {
                "role": "system",
                "content": f"Ты {expert['role']}. Ты {expert['approach']}. Дай свое решение задачи."
            },
            {
                "role": "user",
                "content": f"Реши следующую задачу как {expert['name']}:\n\n{task}"
            }
        ]
        
        response = call_deepseek_api(messages, temperature=0.8)
        expert_responses.append({
            "expert": expert['name'],
            "response": response or "Ошибка при получении ответа"
        })
    
    # Теперь просим синтезировать ответы экспертов
    synthesis_messages = [
        {
            "role": "system",
            "content": "Ты модератор группы экспертов. Проанализируй ответы экспертов и создай финальное решение."
        },
        {
            "role": "user",
            "content": f"Задача:\n\n{task}\n\nОтветы экспертов:\n\n" + 
                      "\n\n".join([f"{exp['expert']}:\n{exp['response']}" for exp in expert_responses]) +
                      "\n\nПроанализируй ответы экспертов и создай финальное решение задачи."
        }
    ]
    
    final_response = call_deepseek_api(synthesis_messages, temperature=0.7)
    
    return {
        "method": "Группа экспертов",
        "description": "Группа экспертов решает задачу, затем их ответы синтезируются",
        "expert_responses": expert_responses,
        "final_response": final_response or "Ошибка при синтезе ответов"
    }


def compare_results(task: str, results: List[Dict[str, str]]) -> str:
    """
    Сравнивает результаты разных методов и определяет лучший
    
    Args:
        task: Текст задачи
        results: Список результатов методов
    
    Returns:
        Текст сравнения и анализа
    """
    # Формируем запрос для сравнения
    comparison_text = f"Задача:\n\n{task}\n\n"
    comparison_text += "Решения разными методами:\n\n"
    
    for i, result in enumerate(results, 1):
        comparison_text += f"Метод {i}: {result['method']}\n"
        if result['method'] == "Промпт от другого ИИ":
            comparison_text += f"Созданный промпт: {result.get('prompt_created', 'N/A')}\n"
            comparison_text += f"Ответ: {result['response']}\n\n"
        elif result['method'] == "Группа экспертов":
            comparison_text += "Ответы экспертов:\n"
            for exp in result.get('expert_responses', []):
                comparison_text += f"- {exp['expert']}: {exp['response'][:200]}...\n"
            comparison_text += f"Финальный ответ: {result.get('final_response', 'N/A')}\n\n"
        else:
            comparison_text += f"Ответ: {result['response']}\n\n"
    
    comparison_messages = [
        {
            "role": "system",
            "content": "Ты эксперт по анализу решений задач. Сравни разные подходы и определи, какой метод дал наиболее правильный и полный ответ."
        },
        {
            "role": "user",
            "content": comparison_text + "\n\nСравни эти решения и ответь:\n"
                       "1. Какие различия между подходами?\n"
                       "2. Какой метод дал наиболее правильный ответ?\n"
                       "3. Какие преимущества и недостатки каждого метода?\n"
                       "4. Какой метод лучше всего подходит для такого типа задач?"
        }
    ]
    
    comparison_response = call_deepseek_api(comparison_messages, temperature=0.7)
    
    return comparison_response or "Ошибка при сравнении результатов"


async def run_experiment(update: Update, context: ContextTypes.DEFAULT_TYPE, task: str):
    """
    Запускает эксперимент с разными способами рассуждения
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота
        task: Текст задачи для решения
    """
    user_id = update.effective_user.id
    
    # Отправляем сообщение о начале эксперимента
    status_message = await update.message.reply_text(
        "🔬 Начинаю эксперимент с разными способами рассуждения...\n\n"
        "Это может занять некоторое время. Пожалуйста, подождите."
    )
    
    results = []
    
    try:
        # Метод 1: Прямой ответ
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id,
                text="🔬 Эксперимент в процессе...\n\n"
                     "⏳ Метод 1: Прямой ответ - выполняется...\n"
                     "⏳ Метод 2: Пошаговое решение - ожидание\n"
                     "⏳ Метод 3: Промпт от другого ИИ - ожидание\n"
                     "⏳ Метод 4: Группа экспертов - ожидание"
            )
            result1 = method1_direct_answer(task)
            results.append(result1)
        except Exception as e:
            logger.error(f"Ошибка в методе 1: {str(e)}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            results.append({
                "method": "Прямой ответ",
                "description": "Модель дает ответ напрямую без дополнительных инструкций",
                "response": f"❌ Ошибка при выполнении метода: {str(e)}"
            })
        
        # Метод 2: Пошаговое решение
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id,
                text="🔬 Эксперимент в процессе...\n\n"
                     "✅ Метод 1: Прямой ответ - выполнен\n"
                     "⏳ Метод 2: Пошаговое решение - выполняется...\n"
                     "⏳ Метод 3: Промпт от другого ИИ - ожидание\n"
                     "⏳ Метод 4: Группа экспертов - ожидание"
            )
            result2 = method2_step_by_step(task)
            results.append(result2)
        except Exception as e:
            logger.error(f"Ошибка в методе 2: {str(e)}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            results.append({
                "method": "Пошаговое решение",
                "description": "Модель решает задачу пошагово, объясняя каждый шаг",
                "response": f"❌ Ошибка при выполнении метода: {str(e)}"
            })
        
        # Метод 3: Промпт от другого ИИ
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id,
                text="🔬 Эксперимент в процессе...\n\n"
                     "✅ Метод 1: Прямой ответ - выполнен\n"
                     "✅ Метод 2: Пошаговое решение - выполнен\n"
                     "⏳ Метод 3: Промпт от другого ИИ - выполняется...\n"
                     "⏳ Метод 4: Группа экспертов - ожидание"
            )
            result3 = method3_ai_prompt(task)
            results.append(result3)
        except Exception as e:
            logger.error(f"Ошибка в методе 3: {str(e)}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            results.append({
                "method": "Промпт от другого ИИ",
                "description": "Другой ИИ создает промпт, затем основной ИИ решает задачу",
                "response": f"❌ Ошибка при выполнении метода: {str(e)}",
                "prompt_created": "N/A"
            })
        
        # Метод 4: Группа экспертов
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id,
                text="🔬 Эксперимент в процессе...\n\n"
                     "✅ Метод 1: Прямой ответ - выполнен\n"
                     "✅ Метод 2: Пошаговое решение - выполнен\n"
                     "✅ Метод 3: Промпт от другого ИИ - выполнен\n"
                     "⏳ Метод 4: Группа экспертов - выполняется..."
            )
            result4 = method4_expert_panel(task)
            results.append(result4)
        except Exception as e:
            logger.error(f"Ошибка в методе 4: {str(e)}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            results.append({
                "method": "Группа экспертов",
                "description": "Группа экспертов решает задачу, затем их ответы синтезируются",
                "response": f"❌ Ошибка при выполнении метода: {str(e)}",
                "expert_responses": [],
                "final_response": "N/A"
            })
        
        # Сравнение результатов
        try:
            comparison = compare_results(task, results)
            if not comparison or comparison == "Ошибка при сравнении результатов":
                comparison = "Не удалось выполнить сравнение результатов из-за ошибки API."
        except Exception as e:
            logger.error(f"Ошибка при сравнении результатов: {str(e)}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            comparison = f"❌ Ошибка при сравнении результатов: {str(e)}"
        
        # Формируем финальный отчет
        report = "=" * 60 + "\n"
        report += "📊 РЕЗУЛЬТАТЫ ЭКСПЕРИМЕНТА\n"
        report += "=" * 60 + "\n\n"
        report += f"📝 Задача:\n{task}\n\n"
        report += "=" * 60 + "\n\n"
        
        for i, result in enumerate(results, 1):
            report += f"🔹 МЕТОД {i}: {result['method']}\n"
            report += f"Описание: {result['description']}\n\n"
            
            if result['method'] == "Промпт от другого ИИ":
                report += f"📋 Созданный промпт:\n{result.get('prompt_created', 'N/A')}\n\n"
                report += f"💡 Ответ:\n{result['response']}\n\n"
            elif result['method'] == "Группа экспертов":
                report += "👥 Ответы экспертов:\n"
                for exp in result.get('expert_responses', []):
                    report += f"\n• {exp['expert']}:\n{exp['response']}\n"
                report += f"\n🎯 Финальный синтезированный ответ:\n{result.get('final_response', 'N/A')}\n\n"
            else:
                report += f"💡 Ответ:\n{result['response']}\n\n"
            
            report += "-" * 60 + "\n\n"
        
        report += "=" * 60 + "\n"
        report += "📈 СРАВНЕНИЕ И АНАЛИЗ\n"
        report += "=" * 60 + "\n\n"
        report += comparison
        
        # Удаляем статусное сообщение
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id
            )
        except:
            pass
        
        # Отправляем отчет с поддержкой LaTeX
        await send_message_with_latex(update, context, report)
        
    except Exception as e:
        logger.error(f"Критическая ошибка в эксперименте: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        try:
            error_msg = (
                "❌ Произошла критическая ошибка при выполнении эксперимента.\n\n"
                f"Ошибка: {str(e)}\n\n"
                "Пожалуйста, попробуйте:\n"
                "• Проверить подключение к интернету\n"
                "• Попробовать еще раз через несколько секунд\n"
                "• Отправить задачу заново"
            )
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id,
                text=error_msg
            )
        except Exception as edit_error:
            logger.error(f"Не удалось отредактировать сообщение об ошибке: {str(edit_error)}")
            try:
                await update.message.reply_text(
                    "❌ Произошла критическая ошибка при выполнении эксперимента. "
                    "Пожалуйста, попробуйте позже или отправьте задачу заново."
                )
            except:
                pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_message = (
        "👋 Привет! Я бот для эксперимента \"День 4. Разные способы рассуждения\"\n\n"
        "Я сравниваю разные подходы к решению задач:\n"
        "1️⃣ Прямой ответ модели\n"
        "2️⃣ Пошаговое решение (с инструкцией \"решай пошагово\")\n"
        "3️⃣ Промпт от другого ИИ\n"
        "4️⃣ Группа экспертов\n\n"
        "📝 Просто отправь мне задачу (логическую или сложную), и я проведу эксперимент!\n\n"
        "Команды:\n"
        "/start - показать это сообщение\n"
        "/help - справка\n"
        "/example - пример задачи для эксперимента"
    )
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_message = (
        "📖 Справка по боту:\n\n"
        "Этот бот проводит эксперимент по сравнению разных способов рассуждения ИИ.\n\n"
        "Как использовать:\n"
        "1. Отправь боту задачу (логическую или сложную)\n"
        "2. Бот выполнит 4 разных метода решения:\n"
        "   • Прямой ответ\n"
        "   • Пошаговое решение\n"
        "   • Промпт от другого ИИ\n"
        "   • Группа экспертов\n"
        "3. Бот сравнит результаты и покажет анализ\n\n"
        "Команды:\n"
        "/start - начать работу\n"
        "/help - эта справка\n"
        "/example - пример задачи"
    )
    await update.message.reply_text(help_message)


async def example_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /example - показывает пример задачи"""
    example_task = (
        "Задача: В комнате находятся 3 лампы и 3 выключателя. "
        "Каждый выключатель управляет одной лампой. "
        "Ты находишься в другой комнате и можешь только один раз войти в комнату с лампами. "
        "Как определить, какой выключатель управляет какой лампой?"
    )
    
    message = (
        "📝 Пример задачи для эксперимента:\n\n"
        f"{example_task}\n\n"
        "Хочешь запустить эксперимент с этой задачей? Просто отправь её мне!"
    )
    await update.message.reply_text(message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user_message = update.message.text
        
        if not user_message or len(user_message.strip()) < 10:
            await update.message.reply_text(
                "⚠️ Пожалуйста, отправь задачу для решения. "
                "Задача должна содержать хотя бы несколько слов.\n\n"
                "Используй /example чтобы увидеть пример задачи."
            )
            return
        
        # Запускаем эксперимент
        await run_experiment(update, context, user_message.strip())
        
    except Exception as e:
        logger.error(f"Ошибка в handle_message: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        try:
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке сообщения. Пожалуйста, попробуйте позже."
            )
        except:
            pass


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    error = context.error
    
    logger.error("=" * 60)
    logger.error(f"Ошибка в обработчике: {type(error).__name__}")
    logger.error(f"Сообщение об ошибке: {str(error)}")
    logger.error(f"Трассировка: {traceback.format_exc()}")
    logger.error("=" * 60)
    
    if update and update.message:
        try:
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз."
            )
        except:
            pass


def main():
    """Основная функция для запуска бота"""
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("example", example_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен и готов к работе!")
    print("\n" + "="*60)
    print("🤖 Телеграм-бот для эксперимента запущен!")
    print("="*60)
    print("Нажмите Ctrl+C для остановки\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
