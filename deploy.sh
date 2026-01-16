#!/bin/bash
# Скрипт для развертывания бота на VPS сервере

set -e

echo "=========================================="
echo "Развертывание AIAdvent Telegram Bot"
echo "=========================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка, что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Ошибка: Скрипт должен быть запущен от root (используйте sudo)${NC}"
    exit 1
fi

# Определяем директорию, где находится скрипт
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Переменные
APP_DIR="/opt/aibot"
SERVICE_USER="www-data"
SERVICE_NAME="aibot"
SERVICE_FILE="aibot.service"

# Проверяем наличие необходимых файлов
echo -e "${YELLOW}Проверка наличия файлов проекта...${NC}"
REQUIRED_FILES=("bot.py" "deepseek_client.py" "requirements.txt" "aibot.service")
MISSING_FILES=()

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$SCRIPT_DIR/$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -ne 0 ]; then
    echo -e "${RED}Ошибка: Не найдены следующие файлы:${NC}"
    for file in "${MISSING_FILES[@]}"; do
        echo -e "${RED}  - $file${NC}"
    done
    echo -e "${YELLOW}Убедитесь, что вы запускаете скрипт из директории проекта.${NC}"
    exit 1
fi

# Используем директорию проекта как рабочую директорию
APP_DIR="$SCRIPT_DIR"
echo -e "${YELLOW}Использование директории проекта: $APP_DIR${NC}"

# Проверяем существование пользователя
echo -e "${YELLOW}Проверка пользователя $SERVICE_USER...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    echo -e "${YELLOW}Пользователь $SERVICE_USER не найден, создаем...${NC}"
    if [ -f /etc/debian_version ]; then
        # Для Debian/Ubuntu
        if ! useradd -r -s /bin/false $SERVICE_USER 2>/dev/null; then
            echo -e "${RED}Не удалось создать пользователя $SERVICE_USER${NC}"
            echo -e "${YELLOW}Попробуйте создать его вручную или измените SERVICE_USER в скрипте${NC}"
            exit 1
        fi
    elif [ -f /etc/redhat-release ]; then
        # Для CentOS/RHEL
        if ! useradd -r -s /sbin/nologin $SERVICE_USER 2>/dev/null; then
            echo -e "${RED}Не удалось создать пользователя $SERVICE_USER${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Не удалось определить дистрибутив для создания пользователя${NC}"
        echo -e "${YELLOW}Создайте пользователя $SERVICE_USER вручную или измените SERVICE_USER в скрипте${NC}"
        exit 1
    fi
    echo -e "${GREEN}Пользователь $SERVICE_USER создан${NC}"
fi

# Устанавливаем права доступа
echo -e "${YELLOW}Установка прав доступа...${NC}"
if ! chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR; then
    echo -e "${RED}Ошибка при изменении владельца файлов${NC}"
    echo -e "${YELLOW}Проверьте права доступа к директории $APP_DIR${NC}"
    ls -la $(dirname $APP_DIR) | grep $(basename $APP_DIR) || echo "Директория не найдена в списке"
    exit 1
fi
echo -e "${GREEN}Права доступа установлены${NC}"

# Проверяем наличие tokens.txt
if [ ! -f "$APP_DIR/tokens.txt" ]; then
    echo -e "${YELLOW}Создание файла tokens.txt...${NC}"
    touch $APP_DIR/tokens.txt
    chown $SERVICE_USER:$SERVICE_USER $APP_DIR/tokens.txt
    chmod 600 $APP_DIR/tokens.txt
    echo -e "${RED}ВАЖНО: Не забудьте добавить токены в $APP_DIR/tokens.txt${NC}"
    echo "Формат:"
    echo "DEEPSEEK_API_KEY=your_key_here"
    echo "TELEGRAM_BOT_TOKEN=your_token_here"
fi

# Устанавливаем Python и зависимости
echo -e "${YELLOW}Проверка Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Установка Python 3...${NC}"
    if [ -f /etc/debian_version ]; then
        apt-get update
        apt-get install -y python3 python3-pip python3-venv
    elif [ -f /etc/redhat-release ]; then
        yum install -y python3 python3-pip
    else
        echo -e "${RED}Не удалось определить дистрибутив. Установите Python 3 вручную.${NC}"
        exit 1
    fi
fi

# Создаем виртуальное окружение
echo -e "${YELLOW}Создание виртуального окружения...${NC}"
cd $APP_DIR || exit 1
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Виртуальное окружение уже существует, пропускаем создание...${NC}"
else
    echo -e "${YELLOW}Создание нового виртуального окружения...${NC}"
    if ! sudo -u $SERVICE_USER python3 -m venv .venv; then
        echo -e "${RED}Ошибка при создании виртуального окружения${NC}"
        exit 1
    fi
    echo -e "${GREEN}Виртуальное окружение создано успешно${NC}"
fi

# Устанавливаем зависимости
echo -e "${YELLOW}Установка зависимостей...${NC}"
if [ ! -f "$APP_DIR/.venv/bin/pip" ]; then
    echo -e "${RED}Ошибка: pip не найден в виртуальном окружении${NC}"
    exit 1
fi

if ! sudo -u $SERVICE_USER $APP_DIR/.venv/bin/pip install --upgrade pip --quiet; then
    echo -e "${RED}Ошибка при обновлении pip${NC}"
    exit 1
fi

if ! sudo -u $SERVICE_USER $APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt --quiet 2>/dev/null; then
    echo -e "${YELLOW}Установка зависимостей с выводом прогресса...${NC}"
    if ! sudo -u $SERVICE_USER $APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt; then
        echo -e "${RED}Ошибка при установке зависимостей${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}Зависимости установлены успешно${NC}"

# Копируем и настраиваем systemd service
echo -e "${YELLOW}Настройка systemd service...${NC}"
if [ ! -f "$SCRIPT_DIR/$SERVICE_FILE" ]; then
    echo -e "${RED}Ошибка: файл $SERVICE_FILE не найден${NC}"
    exit 1
fi

# Создаем временный service файл с правильными путями
TEMP_SERVICE="/tmp/${SERVICE_FILE}.tmp"
sed "s|/opt/aibot|$APP_DIR|g" "$SCRIPT_DIR/$SERVICE_FILE" > "$TEMP_SERVICE"

if ! cp "$TEMP_SERVICE" /etc/systemd/system/$SERVICE_FILE; then
    echo -e "${RED}Ошибка при копировании service файла${NC}"
    rm -f "$TEMP_SERVICE"
    exit 1
fi

rm -f "$TEMP_SERVICE"
echo -e "${GREEN}Service файл настроен с путем: $APP_DIR${NC}"

if ! systemctl daemon-reload; then
    echo -e "${RED}Ошибка при перезагрузке systemd${NC}"
    exit 1
fi

if ! systemctl enable $SERVICE_NAME; then
    echo -e "${RED}Ошибка при включении автозапуска сервиса${NC}"
    exit 1
fi

echo -e "${GREEN}=========================================="
echo "Развертывание завершено!"
echo "==========================================${NC}"
echo ""
echo "Следующие шаги:"
echo "1. Отредактируйте файл $APP_DIR/tokens.txt и добавьте ваши токены"
echo "2. Запустите бота командой: sudo systemctl start aibot"
echo "3. Проверьте статус: sudo systemctl status aibot"
echo "4. Просмотр логов: sudo journalctl -u aibot -f"
echo ""

# Проверяем, что все файлы на месте
echo -e "${YELLOW}Проверка установленных файлов...${NC}"
if [ -f "$APP_DIR/bot.py" ] && [ -f "$APP_DIR/requirements.txt" ] && [ -d "$APP_DIR/.venv" ]; then
    echo -e "${GREEN}✓ Все файлы на месте${NC}"
else
    echo -e "${RED}⚠ Некоторые файлы отсутствуют${NC}"
fi

exit 0

