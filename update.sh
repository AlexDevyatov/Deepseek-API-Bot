#!/bin/bash
# Скрипт для обновления бота на сервере

set -e

echo "=========================================="
echo "Обновление AIAdvent Telegram Bot"
echo "=========================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Проверка, что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Ошибка: Скрипт должен быть запущен от root (используйте sudo)${NC}"
    exit 1
fi

# Определяем директорию, где находится скрипт
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Переменные
APP_DIR="$SCRIPT_DIR"
SERVICE_USER="www-data"
SERVICE_NAME="aibot"
REQUIREMENTS_FILE="$APP_DIR/requirements.txt"

echo -e "${BLUE}Директория проекта: $APP_DIR${NC}"
echo ""

# Проверяем, что директория существует
if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}Ошибка: Директория $APP_DIR не найдена${NC}"
    exit 1
fi

# Проверяем статус сервиса перед обновлением
echo -e "${YELLOW}Проверка статуса сервиса...${NC}"
if systemctl is-active --quiet $SERVICE_NAME; then
    SERVICE_WAS_RUNNING=true
    echo -e "${GREEN}Сервис $SERVICE_NAME запущен${NC}"
else
    SERVICE_WAS_RUNNING=false
    echo -e "${YELLOW}Сервис $SERVICE_NAME не запущен${NC}"
fi
echo ""

# Сохраняем хеш requirements.txt для проверки изменений
OLD_REQUIREMENTS_HASH=""
if [ -f "$REQUIREMENTS_FILE" ]; then
    OLD_REQUIREMENTS_HASH=$(md5sum "$REQUIREMENTS_FILE" 2>/dev/null | cut -d' ' -f1 || sha256sum "$REQUIREMENTS_FILE" 2>/dev/null | cut -d' ' -f1 || echo "")
fi

# Останавливаем сервис
if [ "$SERVICE_WAS_RUNNING" = true ]; then
    echo -e "${YELLOW}Остановка сервиса $SERVICE_NAME...${NC}"
    if systemctl stop $SERVICE_NAME; then
        echo -e "${GREEN}Сервис остановлен${NC}"
    else
        echo -e "${RED}Ошибка при остановке сервиса${NC}"
        exit 1
    fi
    echo ""
fi

# Обновление через Git (если это git репозиторий)
if [ -d "$APP_DIR/.git" ]; then
    echo -e "${YELLOW}Обновление кода через Git...${NC}"
    cd "$APP_DIR"
    
    # Исправляем проблему с dubious ownership (если нужно)
    # Git может жаловаться, если владелец репозитория отличается от текущего пользователя
    if ! git config --global --get safe.directory | grep -q "^$APP_DIR$" 2>/dev/null; then
        echo -e "${YELLOW}Добавление директории в safe.directory для Git...${NC}"
        git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
    fi
    
    # Сохраняем текущую ветку
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    echo -e "${BLUE}Текущая ветка: $CURRENT_BRANCH${NC}"
    
    # Получаем изменения
    if git fetch origin 2>/dev/null; then
        # Проверяем, есть ли изменения
        LOCAL=$(git rev-parse @ 2>/dev/null || echo "")
        REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")
        BASE=$(git merge-base @ @{u} 2>/dev/null || echo "")
        
        if [ "$LOCAL" = "$REMOTE" ]; then
            echo -e "${GREEN}Код уже актуален, изменений нет${NC}"
        elif [ "$LOCAL" = "$BASE" ]; then
            echo -e "${YELLOW}Обнаружены новые изменения, выполняю pull...${NC}"
            if git pull origin "$CURRENT_BRANCH"; then
                echo -e "${GREEN}Код успешно обновлен${NC}"
            else
                echo -e "${RED}Ошибка при выполнении git pull${NC}"
                # Пытаемся перезапустить сервис даже при ошибке
                if [ "$SERVICE_WAS_RUNNING" = true ]; then
                    systemctl start $SERVICE_NAME || true
                fi
                exit 1
            fi
        elif [ "$REMOTE" = "$BASE" ]; then
            echo -e "${YELLOW}У вас есть локальные изменения, которые не были отправлены${NC}"
            echo -e "${YELLOW}Выполняю pull с rebase...${NC}"
            if git pull --rebase origin "$CURRENT_BRANCH"; then
                echo -e "${GREEN}Код успешно обновлен${NC}"
            else
                echo -e "${RED}Ошибка при выполнении git pull --rebase${NC}"
                echo -e "${YELLOW}Попробуйте разрешить конфликты вручную${NC}"
                if [ "$SERVICE_WAS_RUNNING" = true ]; then
                    systemctl start $SERVICE_NAME || true
                fi
                exit 1
            fi
        else
            echo -e "${YELLOW}Обнаружены расхождения между локальной и удаленной ветками${NC}"
            echo -e "${YELLOW}Выполняю pull с rebase...${NC}"
            if git pull --rebase origin "$CURRENT_BRANCH"; then
                echo -e "${GREEN}Код успешно обновлен${NC}"
            else
                echo -e "${RED}Ошибка при выполнении git pull --rebase${NC}"
                echo -e "${YELLOW}Попробуйте разрешить конфликты вручную${NC}"
                if [ "$SERVICE_WAS_RUNNING" = true ]; then
                    systemctl start $SERVICE_NAME || true
                fi
                exit 1
            fi
        fi
    else
        echo -e "${YELLOW}Не удалось выполнить git fetch, пропускаем обновление через Git${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}Директория не является Git репозиторием, пропускаем обновление через Git${NC}"
    echo -e "${YELLOW}Для обновления кода скопируйте новые файлы в $APP_DIR${NC}"
    echo ""
fi

# Проверяем, изменился ли requirements.txt
NEW_REQUIREMENTS_HASH=""
if [ -f "$REQUIREMENTS_FILE" ]; then
    NEW_REQUIREMENTS_HASH=$(md5sum "$REQUIREMENTS_FILE" 2>/dev/null | cut -d' ' -f1 || sha256sum "$REQUIREMENTS_FILE" 2>/dev/null | cut -d' ' -f1 || echo "")
fi

# Обновляем зависимости, если requirements.txt изменился или виртуальное окружение не существует
if [ "$OLD_REQUIREMENTS_HASH" != "$NEW_REQUIREMENTS_HASH" ] || [ ! -d "$APP_DIR/.venv" ]; then
    echo -e "${YELLOW}Обновление зависимостей...${NC}"
    
    if [ ! -d "$APP_DIR/.venv" ]; then
        echo -e "${YELLOW}Виртуальное окружение не найдено, создаем...${NC}"
        if ! sudo -u $SERVICE_USER python3 -m venv "$APP_DIR/.venv"; then
            echo -e "${RED}Ошибка при создании виртуального окружения${NC}"
            if [ "$SERVICE_WAS_RUNNING" = true ]; then
                systemctl start $SERVICE_NAME || true
            fi
            exit 1
        fi
        echo -e "${GREEN}Виртуальное окружение создано${NC}"
    fi
    
    if [ ! -f "$APP_DIR/.venv/bin/pip" ]; then
        echo -e "${RED}Ошибка: pip не найден в виртуальном окружении${NC}"
        if [ "$SERVICE_WAS_RUNNING" = true ]; then
            systemctl start $SERVICE_NAME || true
        fi
        exit 1
    fi
    
    echo -e "${YELLOW}Обновление pip...${NC}"
    if ! sudo -u $SERVICE_USER "$APP_DIR/.venv/bin/pip" install --upgrade pip --quiet; then
        echo -e "${RED}Ошибка при обновлении pip${NC}"
        if [ "$SERVICE_WAS_RUNNING" = true ]; then
            systemctl start $SERVICE_NAME || true
        fi
        exit 1
    fi
    
    echo -e "${YELLOW}Установка зависимостей из requirements.txt...${NC}"
    if ! sudo -u $SERVICE_USER "$APP_DIR/.venv/bin/pip" install -r "$REQUIREMENTS_FILE" --quiet 2>/dev/null; then
        echo -e "${YELLOW}Установка зависимостей с выводом прогресса...${NC}"
        if ! sudo -u $SERVICE_USER "$APP_DIR/.venv/bin/pip" install -r "$REQUIREMENTS_FILE"; then
            echo -e "${RED}Ошибка при установке зависимостей${NC}"
            if [ "$SERVICE_WAS_RUNNING" = true ]; then
                systemctl start $SERVICE_NAME || true
            fi
            exit 1
        fi
    fi
    echo -e "${GREEN}Зависимости обновлены${NC}"
    echo ""
else
    echo -e "${GREEN}Зависимости не изменились, пропускаем обновление${NC}"
    echo ""
fi

# Проверяем наличие необходимых файлов
echo -e "${YELLOW}Проверка файлов проекта...${NC}"
REQUIRED_FILES=("bot.py" "requirements.txt")
MISSING_FILES=()

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$APP_DIR/$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -ne 0 ]; then
    echo -e "${RED}Ошибка: Не найдены следующие файлы:${NC}"
    for file in "${MISSING_FILES[@]}"; do
        echo -e "${RED}  - $file${NC}"
    done
    if [ "$SERVICE_WAS_RUNNING" = true ]; then
        systemctl start $SERVICE_NAME || true
    fi
    exit 1
fi
echo -e "${GREEN}Все необходимые файлы на месте${NC}"
echo ""

# Перезагружаем systemd для применения изменений в service файле (если он изменился)
if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    echo -e "${YELLOW}Перезагрузка systemd...${NC}"
    systemctl daemon-reload
    echo -e "${GREEN}Systemd перезагружен${NC}"
    echo ""
fi

# Запускаем сервис после успешного обновления
# Проверяем, существует ли файл сервиса
if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    echo -e "${YELLOW}Запуск сервиса $SERVICE_NAME...${NC}"
    if systemctl start $SERVICE_NAME; then
        echo -e "${GREEN}Сервис запущен${NC}"
    else
        echo -e "${RED}Ошибка при запуске сервиса${NC}"
        echo -e "${YELLOW}Проверьте логи: sudo journalctl -u $SERVICE_NAME -n 50${NC}"
        exit 1
    fi
    echo ""
    
    # Ждем немного и проверяем статус
    sleep 2
    echo -e "${YELLOW}Проверка статуса сервиса...${NC}"
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✓ Сервис $SERVICE_NAME успешно запущен и работает${NC}"
    else
        echo -e "${RED}✗ Сервис $SERVICE_NAME не запущен${NC}"
        echo -e "${YELLOW}Проверьте логи: sudo journalctl -u $SERVICE_NAME -n 50${NC}"
        exit 1
    fi
    echo ""
else
    echo -e "${YELLOW}Файл сервиса /etc/systemd/system/$SERVICE_NAME.service не найден${NC}"
    echo -e "${YELLOW}Сервис не будет запущен автоматически${NC}"
    echo ""
fi

echo -e "${GREEN}=========================================="
echo "Обновление завершено успешно!"
echo "==========================================${NC}"
echo ""
echo "Полезные команды:"
echo "• Статус сервиса: sudo systemctl status $SERVICE_NAME"
echo "• Логи (последние 50 строк): sudo journalctl -u $SERVICE_NAME -n 50"
echo "• Логи в реальном времени: sudo journalctl -u $SERVICE_NAME -f"
echo "• Перезапуск: sudo systemctl restart $SERVICE_NAME"
echo "• Остановка: sudo systemctl stop $SERVICE_NAME"
echo ""

exit 0

