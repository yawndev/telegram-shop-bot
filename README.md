# Telegram Shop Bot (Pro Edition)

Полноценный Telegram-магазин на **aiogram 3** + **MySQL** с оплатой через **Telegram Stars**.

Коммерческая реализация с корзиной, автодоставкой контента, рассылками, реферальной программой и возвратами средств.

## Возможности

- 🛍 **Каталог товаров** — в БД, с активными и скрытыми позициями
- 🧺 **Корзина** — множественные товары, количества, оформление одним платежом
- 💳 **Оплата Telegram Stars** — без внешних платёжных шлюзов и API-ключей
- 📦 **Автодоставка** — после оплаты бот сам шлёт покупателю текст или файл (`delivery_type = text / file / none`)
- 📣 **Рассылка** — broadcast всем пользователям через админ-панель, с анти-флудом (≤20 msg/sec)
- 👥 **Реферальная программа** — персональные deep-ссылки (`?start=ref_<id>`), автоматическое начисление бонуса 10% с оплат рефералов
- ↩️ **Возврат средств** — `bot.refund_star_payment()` прямо из админки
- 🛠 **Админ-CRUD товаров** — добавление, редактирование, скрытие из продажи через FSM-диалог в самом боте
- 📊 **Статистика** — пользователи, заказы, выручка, возвраты
- 🧾 **Журнал заказов** — для админа и пользователя

## Стек технологий

- **Python 3.11+**
- **aiogram 3.13** — фреймворк Telegram Bot API
- **aiomysql** — асинхронный драйвер MySQL
- **aiogram.fsm.MemoryStorage** — машина состояний для диалогов с админом
- **MySQL 8+** — реляционная БД с 5 таблицами
- **python-dotenv** — конфигурация через `.env`

## Архитектура

```
telegram-shop-bot/
├── bot.py                  # Точка входа, Dispatcher, MemoryStorage
├── config.py               # Загрузка .env
├── database.py             # Асинхронный слой MySQL (pool)
├── states.py               # FSM-группы состояний
├── schema.sql              # DDL + демо-данные (fresh install)
├── schema_v2_migration.sql # Миграция с предыдущей версии
├── handlers/
│   ├── user.py             # /start, меню, рефералы, приём платежа, авто-доставка
│   ├── cart.py             # Управление корзиной + оформление
│   └── admin.py            # Панель, CRUD товаров, рассылка, refund
├── keyboards/
│   ├── user_kb.py
│   └── admin_kb.py
├── utils/
│   └── notifier.py         # Уведомления админу о заказах
├── requirements.txt
├── .env.example
└── .gitignore
```

## Схема базы данных

```
users        id, username, full_name, referrer_id, referral_bonus_stars, created_at
products     id, title, description, price_stars, is_active,
             delivery_type (none|text|file), delivery_text, delivery_file_id
orders       id, user_id, amount_stars, status (pending|paid|cancelled|refunded),
             telegram_payment_charge_id, delivered, created_at, paid_at, refunded_at
order_items  id, order_id, product_id, product_title, price_stars, quantity
cart_items   id, user_id, product_id, quantity, added_at
```

## Поток оплаты

```
Каталог → Добавить в корзину → Корзина → «Оформить»
     ↓
create_order_from_cart() → INSERT orders + order_items (snapshot)
     ↓
send_invoice (XTR, без provider_token)
     ↓
pre_checkout_query → answer(ok=True)
     ↓
successful_payment →
    • orders.status = 'paid'
    • cart_items очищается
    • автодоставка (text / file) по каждому order_item
    • orders.delivered = TRUE
    • начисление реферального бонуса
    • уведомление админу
```

## Установка

```bash
git clone https://github.com/YOUR_USERNAME/telegram-shop-bot.git
cd telegram-shop-bot

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Заполнить BOT_TOKEN, ADMIN_ID, параметры MySQL

mysql -u root -p < schema.sql

python bot.py
```

**Для Windows (PowerShell):** запускать `schema.sql` через MySQL CLI:

```sql
-- внутри mysql>
source C:/path/to/schema.sql
```

## Получить токены

- **BOT_TOKEN** — [@BotFather](https://t.me/BotFather), `/newbot`
- **ADMIN_ID** — [@userinfobot](https://t.me/userinfobot)

## Команды бота

| Команда | Кто может | Действие |
|---------|-----------|----------|
| `/start` | Все | Приветствие, главное меню |
| `/start ref_<user_id>` | Все | Переход по реферальной ссылке |
| `/admin` | Только `ADMIN_ID` | Открыть админ-панель |

## Админ-панель

- 📊 Статистика — пользователи / заказы / выручка
- 🧾 Последние 10 заказов
- 📦 Товары — CRUD через FSM (добавить / изменить поля / скрыть)
- 📣 Рассылка — broadcast всем с подтверждением и прогрессом
- ↩️ Возврат средств — по номеру заказа, через Telegram Stars API

## Реферальная программа

Каждый пользователь получает deep-link `t.me/<bot>?start=ref_<id>`. Когда новый пользователь переходит по ней и впервые нажимает /start — его `referrer_id` сохраняется в `users`. При любой его оплате 10% от суммы (настраиваемо в `handlers/user.py::REFERRAL_PERCENT`) начисляется рефереру в `referral_bonus_stars`. Реферер получает моментальное уведомление в Telegram.

## Автодоставка

У каждого товара есть `delivery_type`:
- `none` — только уведомление об оплате
- `text` — после оплаты бот отправит текст из `delivery_text`
- `file` — бот отправит файл/фото по сохранённому `file_id`

`file_id` сохраняется автоматически когда админ пришлёт файл боту при создании товара. Это значит — никакие файлы не хранятся на диске сервера, всё живёт на стороне Telegram.

## Безопасность

- Секреты только в `.env` (добавлен в `.gitignore`)
- Проверка `user_id == ADMIN_ID` на каждом админ-хендлере
- Параметризованные SQL-запросы → защита от инъекций
- Платёжные данные не проходят через код — всё на стороне Telegram
- Соблюдение rate-limit Telegram при рассылках (20 msg/sec)

## Деплой на VPS (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv mysql-server
git clone https://github.com/YOUR_USERNAME/telegram-shop-bot.git /opt/shop-bot
cd /opt/shop-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo mysql < schema.sql
cp .env.example .env && nano .env
```

`/etc/systemd/system/shop-bot.service`:

```ini
[Unit]
Description=Telegram Shop Bot
After=network.target mysql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/shop-bot
ExecStart=/opt/shop-bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shop-bot
```

## Автор

Telegram-боты под заказ: магазины, оплаты, уведомления, интеграции.

- Telegram: @yaroslav_blog1

## Лицензия

MIT
