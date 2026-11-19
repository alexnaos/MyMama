# Настройка HTTPS для eg.sloboda43.netcraze.pro

## Вариант 1: С помощью Nginx (рекомендуется для production)

### Шаг 1: Установка и настройка Nginx на сервере

```bash
# На Ubuntu/Debian
sudo apt update
sudo apt install nginx

# На CentOS/RHEL
sudo yum install nginx
```

### Шаг 2: Получение SSL сертификатов

#### Вариант A: Бесплатные сертификаты Let's Encrypt
```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d eg.sloboda43.netcraze.pro

# Автообновление
sudo certbot renew --dry-run
```

#### Вариант B: Самоподписанный сертификат (для тестирования)
```bash
# Создание сертификата
openssl req -x509 -newkey rsa:4096 \
  -keyout /etc/ssl/private/eg_sloboda43.key \
  -out /etc/ssl/certs/eg_sloboda43.crt \
  -days 365 -nodes \
  -subj "/C=RU/ST=Moscow/L=Moscow/O=Company/CN=eg.sloboda43.netcraze.pro"
```

### Шаг 3: Настройка Nginx

1. Скопируйте файл `nginx-config.conf` в `/etc/nginx/sites-available/eg_sloboda43`
2. Замените пути к сертификатам на реальные:
   - `ssl_certificate` → путь к CRT файлу
   - `ssl_certificate_key` → путь к KEY файлу

3. Активируйте конфигурацию:
```bash
sudo ln -s /etc/nginx/sites-available/eg_sloboda43 /etc/nginx/sites-enabled/
sudo nginx -t  # Проверка синтаксиса
sudo systemctl reload nginx
```

### Шаг 4: Настройка firewall
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

## Вариант 2: Прямой HTTPS в Flask (для тестирования)

### Запуск с самоподписанным сертификатом:
```bash
cd /path/to/MyMama
python app.py https
```

**Внимание**: Браузер будет показывать предупреждение о небезопасном соединении!

## Вариант 3: Использование Cloudflare (самый простой)

1. Зарегистрируйтесь на [Cloudflare.com](https://cloudflare.com)
2. Добавьте домен `sloboda43.netcraze.pro`
3. Настройте DNS записи:
   ```
   Type    Name                  Content
   A       eg                    1.2.3.4 (ваш IP)
   CNAME   www.sloboda43.netcraze.pro   sloboda43.netcraze.pro
   ```
4. Включите "SSL/TLS" → режим "Flexible" или "Full"
5. Включите "Always Use HTTPS"

## Проверка конфигурации

После настройки проверьте:
1. `https://eg.sloboda43.netcraze.pro` открывается без ошибок
2. Редирект с HTTP на HTTPS работает
3. Web Share API теперь доступен

## Для вашего случая (роутер)

Если у вас в роутере уже настроен HTTPS, но сайт не открывается:

### Проблема: В роутере настроен HTTPS на порту 443, но Flask слушает порт 5001

### Решение 1: Изменить порт Flask на 443 (требует прав root)
```python
# В app.py изменить
app.run(host='0.0.0.0', port=443, debug=False)  # порт 443
```

### Решение 2: Проброс портов в роутере
Настройте в роутере:
- Внешний порт 443 → Внутренний порт 5001 на IP вашего сервера

### Решение 3: Самый правильный - использовать Nginx как прокси
1. Nginx слушает порт 443 с SSL
2. Nginx проксирует запросы на Flask (127.0.0.1:5001)
3. В роутере только порт 443 пробрасывается на сервер с Nginx

## Рекомендация

Используйте **Вариант 3 (Cloudflare)** - это самый простой способ получить HTTPS без настройки сертификатов на сервере. Cloudflare также:
- Кэширует статические файлы
- Защищает от DDoS
- Ускоряет загрузку
- Предоставляет бесплатный SSL