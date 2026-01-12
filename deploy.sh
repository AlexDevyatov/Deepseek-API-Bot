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

# Создаем директорию приложения
echo -e "${YELLOW}Создание директории приложения...${NC}"
mkdir -p $APP_DIR

# Копируем файлы проекта
echo -e "${YELLOW}Копирование файлов проекта...${NC}"
cp "$SCRIPT_DIR/bot.py" "$SCRIPT_DIR/deepseek_client.py" "$SCRIPT_DIR/requirements.txt" $APP_DIR/
chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR

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
cd $APP_DIR
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Виртуальное окружение уже существует, пропускаем создание...${NC}"
else
    sudo -u $SERVICE_USER python3 -m venv .venv
fi

# Устанавливаем зависимости
echo -e "${YELLOW}Установка зависимостей...${NC}"
sudo -u $SERVICE_USER $APP_DIR/.venv/bin/pip install --upgrade pip --quiet
sudo -u $SERVICE_USER $APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt --quiet

# Копируем и настраиваем systemd service
echo -e "${YELLOW}Настройка systemd service...${NC}"
cp "$SCRIPT_DIR/$SERVICE_FILE" /etc/systemd/system/
systemctl daemon-reload
systemctl enable $SERVICE_NAME

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

