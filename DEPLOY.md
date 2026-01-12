# Развертывание на VPS сервере

Это руководство поможет вам развернуть AIAdvent Telegram Bot на VPS сервере с использованием systemd для автозапуска.

## Требования

- VPS сервер с Ubuntu/Debian или другим Linux дистрибутивом
- Доступ по SSH с правами root или sudo
- Python 3.8 или выше
- Интернет-соединение

## Способ 1: Автоматическое развертывание (рекомендуется)

### Шаг 1: Подключитесь к серверу

```bash
ssh root@your_server_ip
# или
ssh user@your_server_ip
```

### Шаг 2: Загрузите проект на сервер

Вы можете использовать один из следующих способов:

**Вариант A: Клонирование из Git (если проект в репозитории)**
```bash
cd /opt
git clone https://github.com/AlexDevyatov/Deepseek-API-Bot.git aibot
cd aibot
```

**Вариант B: Загрузка файлов через SCP**
```bash
# На вашем локальном компьютере:
scp -r bot.py deepseek_client.py requirements.txt aibot.service deploy.sh root@your_server_ip:/opt/aibot/
```

**Вариант C: Создание файлов вручную**
Скопируйте содержимое файлов проекта на сервер.

### Шаг 3: Запустите скрипт развертывания

```bash
cd /opt/aibot
chmod +x deploy.sh
sudo ./deploy.sh
```

### Шаг 4: Настройте токены

Отредактируйте файл `tokens.txt`:

```bash
sudo nano /opt/aibot/tokens.txt
```

Добавьте ваши токены:
```
DEEPSEEK_API_KEY=your_deepseek_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

Сохраните файл (Ctrl+O, Enter, Ctrl+X в nano).

### Шаг 5: Запустите бота

```bash
sudo systemctl start aibot
sudo systemctl status aibot
```

Если все настроено правильно, вы увидите статус `active (running)`.

## Способ 2: Ручное развертывание

### Шаг 1: Установите зависимости

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv
```

### Шаг 2: Создайте директорию и скопируйте файлы

```bash
sudo mkdir -p /opt/aibot
sudo cp bot.py deepseek_client.py requirements.txt /opt/aibot/
sudo chown -R www-data:www-data /opt/aibot
```

### Шаг 3: Создайте виртуальное окружение

```bash
cd /opt/aibot
sudo -u www-data python3 -m venv .venv
sudo -u www-data /opt/aibot/.venv/bin/pip install --upgrade pip
sudo -u www-data /opt/aibot/.venv/bin/pip install -r requirements.txt
```

### Шаг 4: Создайте файл tokens.txt

```bash
sudo nano /opt/aibot/tokens.txt
```

Добавьте токены:
```
DEEPSEEK_API_KEY=your_deepseek_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

Установите правильные права:
```bash
sudo chown www-data:www-data /opt/aibot/tokens.txt
sudo chmod 600 /opt/aibot/tokens.txt
```

### Шаг 5: Настройте systemd service

Скопируйте файл `aibot.service` в `/etc/systemd/system/`:

```bash
sudo cp aibot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aibot
sudo systemctl start aibot
```

## Управление ботом

### Проверка статуса
```bash
sudo systemctl status aibot
```

### Просмотр логов
```bash
# Все логи
sudo journalctl -u aibot

# Последние логи с отслеживанием в реальном времени
sudo journalctl -u aibot -f

# Логи за последний час
sudo journalctl -u aibot --since "1 hour ago"
```

### Остановка бота
```bash
sudo systemctl stop aibot
```

### Перезапуск бота
```bash
sudo systemctl restart aibot
```

### Отключение автозапуска
```bash
sudo systemctl disable aibot
```

## Обновление бота

Когда нужно обновить код бота:

```bash
# Остановите бота
sudo systemctl stop aibot

# Обновите файлы (скопируйте новые версии bot.py и других файлов)
sudo cp bot.py /opt/aibot/

# Перезапустите бота
sudo systemctl start aibot
```

## Устранение неполадок

### Бот не запускается

1. Проверьте логи:
   ```bash
   sudo journalctl -u aibot -n 50
   ```

2. Проверьте, что файл `tokens.txt` существует и содержит правильные токены:
   ```bash
   sudo cat /opt/aibot/tokens.txt
   ```

3. Проверьте права доступа:
   ```bash
   ls -la /opt/aibot/
   ```

4. Попробуйте запустить бота вручную для диагностики:
   ```bash
   cd /opt/aibot
   sudo -u www-data /opt/aibot/.venv/bin/python3 bot.py
   ```

### Бот запускается, но не отвечает

1. Проверьте, что токены правильные
2. Проверьте интернет-соединение сервера
3. Проверьте логи на наличие ошибок API

### Изменение пользователя systemd

По умолчанию используется пользователь `www-data`. Чтобы изменить:

1. Отредактируйте файл `/etc/systemd/system/aibot.service`:
   ```bash
   sudo nano /etc/systemd/system/aibot.service
   ```

2. Измените строку `User=www-data` на нужного пользователя

3. Измените владельца файлов:
   ```bash
   sudo chown -R your_user:your_user /opt/aibot
   ```

4. Перезагрузите systemd и перезапустите сервис:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart aibot
   ```

## Безопасность

1. **Не коммитьте tokens.txt в Git** - файл уже должен быть в `.gitignore`
2. **Ограничьте права доступа** к файлу tokens.txt (chmod 600)
3. **Используйте firewall** для ограничения доступа к серверу
4. **Регулярно обновляйте** систему и зависимости

## Альтернативные методы развертывания

### Docker (опционально)

Если вы предпочитаете использовать Docker, можно создать `Dockerfile` и `docker-compose.yml`. Пример:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py deepseek_client.py .

CMD ["python", "bot.py"]
```

Затем запуск:
```bash
docker build -t aibot .
docker run -d --name aibot --restart unless-stopped -v $(pwd)/tokens.txt:/app/tokens.txt aibot
```

## Поддержка

Если возникли проблемы, проверьте:
- Логи systemd: `sudo journalctl -u aibot -f`
- Статус сервиса: `sudo systemctl status aibot`
- Конфигурацию: `/etc/systemd/system/aibot.service`

