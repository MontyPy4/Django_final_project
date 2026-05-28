# Rental Project — Django REST Framework

Backend для платформы краткосрочной аренды жилья в Германии (регион Нижняя Саксония, Ганновер).
Реализует регистрацию пользователей, выставление объявлений, бронирование, отзывы, систему ролей,
JWT-аутентификацию через httpOnly cookies и удалённое логирование в MongoDB.

Развёртывание — **docker compose** с отдельными сервисами nginx (SSL + статика), gunicorn,
MySQL и Redis. Для локальной разработки можно запускать без Docker (на SQLite или удалённой MySQL).

## Содержание

- [Стек](#стек)
- [Архитектура](#архитектура)
- [Структура проекта](#структура-проекта)
- [Запуск через Docker](#запуск-через-docker)
- [Запуск без Docker (dev)](#запуск-без-docker-dev)
- [Переменные окружения](#переменные-окружения)
- [Модели данных](#модели-данных)
- [API эндпоинты](#api-эндпоинты)
- [Аутентификация и роли](#аутентификация-и-роли)
- [Безопасность](#безопасность)
- [Логирование](#логирование)
- [Админка](#админка)
- [Миграции](#миграции)
- [Тестирование](#тестирование)
- [Деплой в продакшен](#деплой-в-продакшен)
- [Решение типовых проблем](#решение-типовых-проблем)

---

## Стек

| Слой | Технология |
|---|---|
| Язык / runtime | Python 3.13 |
| Web-фреймворк | Django 4.2 (LTS, ≥4.2.16) |
| REST | Django REST Framework 3.17 |
| Аутентификация | djangorestframework-simplejwt 5.5 + кастомный `CookieJWTAuthentication` |
| Фильтрация | django-filter 25 |
| Документация API | drf-yasg (Swagger / ReDoc) — только в DEBUG |
| CORS | django-cors-headers |
| База данных | MySQL 8 (Docker) / shared MySQL / SQLite (dev) |
| Драйвер MySQL | mysqlclient (C-ext, на Alpine собирается из исходников) |
| Кеш + throttle | Redis 7 (через django-redis) |
| Логирование событий | MongoDB через pymongo (кастомный `MongoLogHandler`) |
| WSGI | gunicorn (3 воркера в Docker) |
| Reverse proxy | nginx 1.27 на Alpine, SSL (self-signed для dev) |
| Контейнеризация | Docker multi-stage build на `python:3.13-alpine` |
| Конфигурация | python-dotenv |
| Изображения | Pillow (зарезервировано) |

---

## Архитектура

```
                       порт 80/443
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│ docker network: rental_net                              │
│                                                         │
│  ┌────────────────┐                                     │
│  │ nginx          │ ← отдаёт /static/, /media/          │
│  │ Alpine         │   из shared-volume                  │
│  │ HTTPS:443      │ ← терминация SSL                    │
│  │ HTTP:80 → 443  │                                     │
│  └────────┬───────┘                                     │
│           │ proxy_pass http://web:8000                  │
│           ▼                                             │
│  ┌────────────────┐   ┌────────────┐   ┌────────────┐  │
│  │ web (gunicorn) │──▶│ db (MySQL) │   │ redis      │  │
│  │ Alpine         │◀──│  utf8mb4   │   │  кеш/throt │  │
│  │ только internal│   └────────────┘   └────────────┘  │
│  └────────────────┘                                     │
│           │ внешний коннект → MongoDB                   │
│           ▼                                             │
└───────── к учебному / Atlas MongoDB ────────────────────┘
```

- `nginx` — единственный сервис, доступный снаружи.
- `web` живёт во внутренней сети, gunicorn принимает HTTP от nginx.
- `db` (MySQL) хранит бизнес-данные на именованном volume `mysql_data`.
- `redis` — кеш и общий счётчик throttle между gunicorn-воркерами.
- `MongoDB` подключается по `MONGO_URI` (учебный сервер или Atlas) для записи логов.

---

## Структура проекта

```
Django_final_project/
├── rental_project/              # Django project
│   ├── settings.py              # все настройки
│   ├── urls.py                  # корневые маршруты + swagger (только в DEBUG)
│   ├── log_handlers.py          # MongoLogHandler
│   ├── asgi.py / wsgi.py
│
├── users/                       # аутентификация + админ-API
│   ├── models.py                # User(AbstractUser): role, phone, first/last_name
│   ├── serializers.py           # Register / Login / User / AdminUser
│   ├── views.py                 # Register/Login/Logout/Refresh + UserAdminViewSet
│   ├── authentication.py        # CookieJWTAuthentication
│   ├── permissions.py           # IsTenant / IsLandlord / IsAdmin
│   ├── throttles.py             # LoginRateThrottle
│   ├── admin.py                 # ModelAdmin для User
│   └── urls.py
│
├── listings/                    # объявления + адреса + история
│   ├── models.py                # Listing, Address, SearchHistory, ViewHistory
│   ├── serializers.py           # ListingSerializer + Short + AddressSerializer
│   ├── views.py                 # CRUD + toggle_status + my_listings + popular_searches
│   ├── filters.py               # ListingFilter (price/region/city/district/rooms/type)
│   ├── permissions.py           # IsOwnerOrReadOnly
│   ├── admin.py                 # Listing + Address в админке
│   └── urls.py
│
├── bookings/                    # бронирование
│   ├── models.py                # Booking (pending/confirmed/cancelled)
│   ├── serializers.py           # с валидацией overlap, листинг must be active
│   ├── views.py                 # CRUD + cancel(24h-rule) + confirm/reject + active/history
│   └── urls.py
│
├── reviews/                     # отзывы
│   ├── models.py                # Review (rating 1-5, unique_together [listing, author])
│   ├── serializers.py           # с проверкой is_active
│   ├── views.py                 # Create только после прожитой брони
│   └── urls.py
│
├── nginx/                       # reverse proxy + SSL
│   ├── Dockerfile               # nginx:1.27-alpine + self-signed cert
│   └── default.conf             # HTTPS → 443, HTTP → 301, /static/ alias
│
├── logs/                        # локальные файловые логи (создаётся автоматически)
│   ├── http_logs.log            # django.request с ротацией
│   └── db_logs.log              # django.db.backends (только в DEBUG)
│
├── Dockerfile                   # multi-stage build для web (Alpine)
├── docker_entrypoint.py         # ждёт БД, migrate, collectstatic, exec CMD
├── docker-compose.yml           # nginx + web + db + redis
├── .dockerignore
├── manage.py
├── requirements.txt
├── .env                         # секреты, gitignored
├── .gitignore
└── README.md
```

---

## Запуск через Docker

### Необходимо
- Docker Desktop (Windows / macOS) или Docker Engine + Docker Compose (Linux)
- Файл `.env` в корне проекта (см. раздел [Переменные окружения](#переменные-окружения))

### Первый запуск
```powershell
cd D:\Django_final_project
docker compose up --build
```
Что происходит:
1. Параллельно собираются образы `rental_web` (Python+Alpine, multi-stage) и `rental_nginx` (Alpine+SSL).
2. Стартуют `db` (MySQL) и `redis`.
3. `web` ждёт пока `db` пройдёт healthcheck, запускается `docker_entrypoint.py`:
   - ждёт TCP-доступности `db:3306`
   - `manage.py migrate`
   - `manage.py collectstatic`
   - `gunicorn` на `:8000`
4. `nginx` поднимается и проксирует к `web:8000`.

### В фоне
```powershell
docker compose up -d --build
docker compose logs -f web nginx
```

### Доступ
- **https://localhost/** — основной (self-signed cert, браузер предупредит → Advanced → Proceed)
- http://localhost/ → автоматический 301 на HTTPS
- API: https://localhost/api/listings/
- Swagger (только в DEBUG): https://localhost/swagger/
- Admin: https://localhost/admin/

### Создать суперюзера
```powershell
docker compose exec web python manage.py createsuperuser
```

### Зайти в shell контейнера
```powershell
docker compose exec web sh
docker compose exec db mysql -u root -p
docker compose exec redis redis-cli
```

### Остановить
```powershell
docker compose down            # контейнеры остановлены, volumes сохранены
docker compose down -v         # ОПАСНО: удалит mysql_data, logs, static
```

---

## Запуск без Docker (dev)

### 1. Виртуальное окружение
```powershell
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

### 2. `.env` для локального dev
```env
SECRET_KEY=django-insecure-change-me-in-prod
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
USE_SQLITE=True
```
SQLite-режим: не нужна MySQL, миграции пойдут в `db.sqlite3`.

### 3. Миграции и запуск
```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Доступ:
- API: http://127.0.0.1:8000/api/
- Swagger: http://127.0.0.1:8000/swagger/
- Admin: http://127.0.0.1:8000/admin/

### Подключение к удалённой MySQL без Docker
В `.env`:
```env
USE_SQLITE=False
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=3306
```

---

## Переменные окружения

Полный `.env` в корне проекта:

```env
# Django core
SECRET_KEY=сгенерируй_длинный_случайный_ключ
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database switch
USE_SQLITE=False

# MySQL (compose автоматически использует эти значения для контейнера db)
DB_NAME=rental_db
DB_USER=rental_user
DB_PASSWORD=rental_password
DB_ROOT_PASSWORD=root_password_change_me
DB_HOST=ich-edit.edu.itcareerhub.de   # игнорируется в Docker (compose ставит DB_HOST=db)
DB_PORT=3306

# Redis (только если запускаешь web НЕ в Docker и хочешь Redis-кеш локально)
# REDIS_URL=redis://localhost:6379/1

# MongoDB для логов
MONGO_URI=mongodb://ich_editor:verystrongpassword@mongo.itcareerhub.de/?authSource=ich_edit
MONGO_DB=ich_edit
MONGO_COLLECTION=rental_app_logs

# CORS для production
CORS_ALLOWED_ORIGINS=https://your-frontend.example.com
```

**Замечание:** в Docker значения `DB_HOST`, `DB_PORT`, `USE_SQLITE`, `REDIS_URL`, `ALLOWED_HOSTS`
переопределяются compose'ом (см. `docker-compose.yml`).

Сгенерировать `SECRET_KEY`:
```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Модели данных

### `users.User` (AbstractUser)
| Поле | Тип | Описание |
|---|---|---|
| username | CharField (unique) | Логин |
| email | EmailField (unique, iexact) | Email для логина (по нему ищем при `POST /auth/login/`) |
| first_name, last_name | CharField | Обязательны при регистрации |
| password | hashed | PBKDF2 через `set_password()` |
| role | TextChoices | `tenant` или `landlord` |
| phone | CharField (blank) | Опционально |
| is_active, is_staff, is_superuser | Bool | Стандартные флаги Django |

### `listings.Address`
| Поле | Тип |
|---|---|
| region | CharField (100) |
| city | CharField (100) |
| district | CharField (100, blank) |

Уникальный индекс на `(region, city, district)`. При создании listing'а адрес создаётся через `get_or_create` — дубликаты не плодятся.

### `listings.Listing`
| Поле | Тип |
|---|---|
| title | CharField (200) |
| description | TextField |
| address | FK → Address (PROTECT) |
| price | Decimal(10, 2) |
| rooms | PositiveIntegerField |
| housing_type | choices: `apartment`, `house`, `studio`, `room` |
| is_active | Bool, default True |
| owner | FK → User (CASCADE) |
| views_count | PositiveIntegerField, default 0 — инкрементируется атомарно через `F()` |
| created_at, updated_at | DateTime |

### `listings.SearchHistory`
| Поле | Тип |
|---|---|
| user | FK → User (CASCADE) |
| keyword | CharField (200) |
| searched_at | DateTime |

### `listings.ViewHistory`
| Поле | Тип |
|---|---|
| user | FK → User (SET_NULL, nullable) |
| listing | FK → Listing (CASCADE) |
| visitor_key | CharField (64, indexed) — SHA-256 от IP+UA для антинакрутки |
| viewed_at | DateTime |

Композитный индекс `(listing, visitor_key, viewed_at)` для быстрого dedup-чека за 24ч.

### `bookings.Booking`
| Поле | Тип |
|---|---|
| listing | FK → Listing |
| tenant | FK → User |
| date_from, date_to | DateField |
| status | choices: `pending`, `confirmed`, `cancelled` |
| created_at | DateTime |

### `reviews.Review`
| Поле | Тип |
|---|---|
| listing | FK → Listing |
| author | FK → User |
| rating | PositiveInteger choices 1..5 |
| text | TextField |
| created_at | DateTime |

`unique_together = ['listing', 'author']` — один отзыв на объявление от пользователя.

---

## API эндпоинты

Базовый URL: `https://localhost/api/` (Docker) или `http://127.0.0.1:8000/api/` (dev).

### Аутентификация (`/api/auth/`)

| Метод | URL | Кто | Описание |
|---|---|---|---|
| POST | `/auth/register/` | anon | Регистрация (username, first_name, last_name, email, password, password_confirm, role) |
| POST | `/auth/login/` | anon | Логин **по email**. Возвращает JWT в body + httpOnly cookies. Throttle: 5/min |
| POST | `/auth/logout/` | auth | Блэклист refresh, очистка cookies |
| POST | `/auth/token/refresh/` | anon | Обмен refresh на новый access (с ротацией) |

### Админ (`/api/auth/users/`) — только `is_staff`

| Метод | URL |
|---|---|
| GET | `/auth/users/` |
| GET | `/auth/users/{id}/` |
| POST | `/auth/users/{id}/activate/` |
| POST | `/auth/users/{id}/deactivate/` (нельзя себя) |
| POST | `/auth/users/{id}/promote/` |

### Объявления (`/api/listings/`)

| Метод | URL | Кто | Действие |
|---|---|---|---|
| GET | `/listings/` | anon | Список (только `is_active=True`), пагинация по 10 |
| POST | `/listings/` | landlord | Создать; owner ставится автоматически |
| GET | `/listings/{id}/` | anon | Детали (+инкремент views_count с cooldown 24ч) |
| PUT/PATCH | `/listings/{id}/` | owner | Обновить |
| DELETE | `/listings/{id}/` | owner | Удалить |
| PATCH | `/listings/{id}/toggle_status/` | owner | Переключить is_active |
| GET | `/listings/my_listings/` | auth | Свои объявления (включая неактивные) |
| GET | `/listings/popular_searches/` | anon | Топ-10 ключевых слов поиска |

**Search:** `?search=keyword` — по полям `title`, `description` (icontains).

**Filters:**
- `price_min`, `price_max`
- `rooms_min`, `rooms_max`
- `region`, `city`, `district` (icontains)
- `housing_type` (apartment / house / studio / room)
- `is_active`

**Ordering** (`?ordering=`): `price`, `created_at`, `views_count`, **`reviews_count`** (по количеству отзывов), `rooms`. Префикс `-` для убывания.

**Пример полного запроса:**
```
GET /api/listings/?search=studio&city=Hannover&price_max=1500&ordering=-reviews_count
```

### Бронирование (`/api/bookings/`)

| Метод | URL | Кто | Действие |
|---|---|---|---|
| POST | `/bookings/` | tenant | Создать бронь (`listing`, `date_from`, `date_to`) |
| GET | `/bookings/` | auth | Свои брони (как tenant и как landlord) |
| GET | `/bookings/{id}/` | auth | Детали |
| GET | `/bookings/active/` | auth | Только pending+confirmed |
| GET | `/bookings/history/` | auth | Cancelled или с прошедшим date_to |
| POST | `/bookings/{id}/confirm/` | landlord | Подтвердить бронь |
| POST | `/bookings/{id}/reject/` | landlord | Отклонить бронь |
| POST | `/bookings/{id}/cancel/` | tenant | Отменить (**≥24ч до date_from**, только pending) |

**Валидация при создании:**
- `date_from >= today`
- `date_to > date_from`
- Объявление активно
- Не своё объявление
- Нет пересечения с pending/confirmed бронями

### Отзывы (`/api/reviews/`)

| Метод | URL | Кто | Действие |
|---|---|---|---|
| GET | `/reviews/` | auth | Список (опционально `?listing={id}`) |
| GET | `/reviews/{id}/` | auth | Детали |
| POST | `/reviews/` | tenant | Создать отзыв (rating 1–5, text) |
| GET | `/reviews/listing_reviews/?listing={id}` | auth | Отзывы по объявлению |

**Валидация при создании:**
- Только роль `tenant`
- Есть подтверждённая бронь с `date_to < today` (фактически прожил)
- Отзыв на это объявление от этого юзера ещё не оставлен (`unique_together`)

---

## Аутентификация и роли

### JWT через httpOnly cookies

Логин выставляет два cookie:
- `access_token` — `Path=/`, `HttpOnly`, `Secure` (в проде), `SameSite=Lax`, TTL 2 часа
- `refresh_token` — `Path=/api/auth/`, `HttpOnly`, `Secure`, TTL 7 дней

Кастомный `CookieJWTAuthentication` (`users/authentication.py`):
- Сначала проверяет заголовок `Authorization: Bearer <token>` (для Postman / Swagger)
- Если заголовка нет — берёт access из cookie

Это даёт XSS-защиту для браузеров и совместимость с не-браузерными клиентами.

### Роли

| Роль | Может |
|---|---|
| anonymous | Смотреть листинги (`list`/`retrieve`), `popular_searches` |
| `tenant` | Создавать брони, оставлять отзывы (после прожитой брони), отменять брони |
| `landlord` | Создавать / редактировать / удалять свои объявления, подтверждать / отклонять брони |
| `is_staff` / `is_superuser` | Управление пользователями (activate/deactivate/promote), Django admin |

Все владелец-проверки (`owner == request.user`) применяются на уровне permission-классов
`IsOwnerOrReadOnly`, `IsLandlord`, `IsTenant`, `IsAdmin`.

---

## Безопасность

### Пароли
- Хеширование: PBKDF2 через `User.objects.create_user()`
- Валидаторы (`AUTH_PASSWORD_VALIDATORS`):
  - `MinimumLengthValidator(min_length=8)`
  - `CommonPasswordValidator` (~20 000 запрещённых паролей)
  - `NumericPasswordValidator`
  - `UserAttributeSimilarityValidator`

### Throttling (через Redis в Docker)
| Scope | Лимит |
|---|---|
| `anon` | 20 req/min |
| `user` | 120 req/min |
| `login` | 5/min per IP (через `LoginRateThrottle`) |

Без Redis (например, локальный `runserver` без `REDIS_URL`) каждый процесс держит свой in-memory счётчик. С Redis — общий между всеми gunicorn-воркерами.

### Защита от user enumeration
`LoginView` возвращает **одинаковое сообщение** для всех 401-сценариев:
`{"error": "Неверные учётные данные"}` — независимо от того, нет такого email, неверный пароль, или аккаунт заблокирован. Реальная причина пишется только в логи.

### Защита от накрутки просмотров
- Cooldown 24 часа на пару `(visitor_key, listing)`
- `visitor_key = SHA-256(IP + User-Agent)` — выживает пересоздание аккаунта
- Владелец не считается просмотрщиком своего объявления

### CORS
- В dev (`DEBUG=True`) — `CORS_ALLOW_ALL_ORIGINS = True`
- В prod (`DEBUG=False`) — список из `CORS_ALLOWED_ORIGINS` env

### HTTPS (через nginx)
- nginx терминирует SSL на 443
- HTTP:80 редиректит на HTTPS
- Для dev — self-signed cert генерируется при `docker build`
- Для prod — заменить на Let's Encrypt (см. [Деплой](#деплой-в-продакшен))
- nginx передаёт `X-Forwarded-Proto` → Django через `SECURE_PROXY_SSL_HEADER` понимает HTTPS

### Прочие prod-настройки (при `DEBUG=False`)
- `SECURE_SSL_REDIRECT = True` (страховка на случай прямого hit web-контейнера)
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`
- `SECURE_HSTS_SECONDS = 31536000`, `INCLUDE_SUBDOMAINS`, `PRELOAD`
- `X_FRAME_OPTIONS = 'DENY'`
- `SECURE_CONTENT_TYPE_NOSNIFF = True`

### Token rotation
`SIMPLE_JWT.ROTATE_REFRESH_TOKENS = True` + `BLACKLIST_AFTER_ROTATION = True`. После каждого refresh старый refresh попадает в blacklist.

### Swagger в проде закрыт
В `rental_project/urls.py`:
```python
if settings.DEBUG:
    urlpatterns += [path('swagger/', ...), path('redoc/', ...)]
```
При `DEBUG=False` эти URL'ы вообще не регистрируются — атакующий не получит schema-разведку.

---

## Логирование

| Логгер | Куда | Уровень |
|---|---|---|
| `django.server` (runserver-вывод) | console | INFO |
| `django.request` (4xx/5xx) | `logs/http_logs.log` + console + **MongoDB** | INFO |
| `django.db.backends` (SQL) | `logs/db_logs.log` | DEBUG (только при `DEBUG=True`) |
| `users`, `listings`, `bookings`, `reviews` (бизнес-события) | console + **MongoDB** | INFO |

### Файловые логи
`RotatingFileHandler`: 5 MB на файл, 5 backup'ов. Папка `logs/` создаётся автоматически при старте.
В Docker — на volume `logs` (переживает перезапуски контейнера).

### MongoDB
Кастомный `MongoLogHandler` (`rental_project/log_handlers.py`) пишет в коллекцию документы вида:
```json
{
  "timestamp": "ISODate(...)",
  "level": "WARNING",
  "logger": "django.request",
  "message": "Unauthorized: /api/bookings/",
  "module": "log",
  "func": "log_response",
  "line": 224,
  "process": 12345,
  "thread": 67890
}
```

Handler устойчив к падению Mongo — при недоступности back-off 30 секунд, приложение не блокируется.

---

## Админка

Доступна по `/admin/`. Зарегистрированы:
- `User` — кастомный `UserAdmin` с фильтрами по `role`, `is_active`, `is_staff`
- `Address`
- `Listing`

Создать суперюзера:
```powershell
# В Docker
docker compose exec web python manage.py createsuperuser

# Без Docker
python manage.py createsuperuser
```

---

## Миграции

В Docker миграции запускаются автоматически из `docker_entrypoint.py` при каждом старте web-контейнера.

Вручную:
```powershell
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# Без Docker
python manage.py makemigrations
python manage.py migrate
```

Текущие миграции:
```
users/migrations/0001_initial.py
listings/migrations/0001_initial.py
listings/migrations/0002_viewhistory_visitor_key_alter_viewhistory_user_and_more.py
listings/migrations/0003_address_remove_listing_location_and_more.py
bookings/migrations/0001_initial.py
reviews/migrations/0001_initial.py
```

---

## Тестирование

### Через Swagger (только DEBUG)
1. Открыть `https://localhost/swagger/`
2. Нажать **Authorize**
3. Ввести `Bearer <access_token>` (получить через `POST /api/auth/login/`)
4. Все эндпоинты доступны для проб

### Через Postman
1. Создать переменные коллекции: `base_url`, `access`, `refresh`, `listing_id`, `booking_id`
2. В Tests-табе у login-запроса:
   ```javascript
   const data = pm.response.json();
   pm.collectionVariables.set('access', data.access);
   pm.collectionVariables.set('refresh', data.refresh);
   ```
3. Сценарий: register → login → CRUD объявлений → создание брони → confirm/cancel → отзыв (после прошедшей брони)

### Через curl
```powershell
# Регистрация
curl -k -X POST https://localhost/api/auth/register/ `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"alice\",\"first_name\":\"Alice\",\"last_name\":\"Smith\",\"email\":\"a@example.com\",\"password\":\"StrongPass123\",\"password_confirm\":\"StrongPass123\",\"role\":\"tenant\"}'

# Логин с сохранением cookies
curl -k -X POST https://localhost/api/auth/login/ `
  -H "Content-Type: application/json" `
  -c cookies.txt `
  -d '{\"email\":\"a@example.com\",\"password\":\"StrongPass123\"}'

# Запрос с cookie
curl -k -X GET https://localhost/api/bookings/ -b cookies.txt
```

`-k` = не верифицировать self-signed cert.

---

## Деплой в продакшен

### Чек-лист
- [ ] `DEBUG=False` в `.env`
- [ ] Сгенерировать новый `SECRET_KEY`
- [ ] `ALLOWED_HOSTS` — список реальных доменов, без `*`
- [ ] `CORS_ALLOWED_ORIGINS` — список доменов фронта
- [ ] Заменить self-signed сертификат на Let's Encrypt:
  - Поставить certbot контейнер
  - Использовать webroot challenge (location `/.well-known/acme-challenge/` уже подготовлен в `nginx/default.conf`)
  - Подменить `ssl_certificate` пути на `/etc/letsencrypt/live/...`
- [ ] Не пробрасывать MySQL `3307` наружу (убрать `ports:` у `db` в compose)
- [ ] Закрыть `/admin/` через nginx `allow`/`deny` по IP или basic-auth
- [ ] Бекапы MySQL (`mysqldump` через cron)
- [ ] Ротация и алертинг по MongoDB-логам
- [ ] Включить `HEALTHCHECK` для web (в Dockerfile)
- [ ] Поднять количество gunicorn-воркеров до `2 * CPU_count + 1`

### `manage.py check --deploy`
Перед выкаткой:
```powershell
docker compose run --rm -e DEBUG=False -e ALLOWED_HOSTS=yourdomain.com web python manage.py check --deploy
```
Должно остаться 0 ошибок (только W009 про SECRET_KEY, если ключ всё ещё с префиксом `django-insecure-`).

---

## Решение типовых проблем

### `AUTH_USER_MODEL refers to model 'users.User' that has not been installed`
Перед первой миграцией убедитесь, что модель `users.User` создана в `users/models.py` и приложение `users` есть в `INSTALLED_APPS`.

### `(1049, "Unknown database '...'")` при подключении к MySQL
В Docker — `mysql:8.0` сам создаст БД из `MYSQL_DATABASE` env. Проверить что в `.env` есть `DB_NAME`.
На удалённой БД — создать вручную:
```sql
CREATE DATABASE ich1_rental_final CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Браузер не открывает `https://localhost/` — `ERR_CERT_AUTHORITY_INVALID`
Это ожидаемо для self-signed cert. Нажать **Advanced → Proceed to localhost (unsafe)**.
Chrome иногда не показывает кнопку — введи в адресной строке `thisisunsafe` (фокус на странице).

### `nginx[1]: ... bind() to 0.0.0.0:80 failed (98: Address already in use)`
Порт 80 занят (например, IIS или Skype). Поменять в `docker-compose.yml`:
```yaml
ports:
  - "8080:80"
  - "8443:443"
```
Доступ через `https://localhost:8443/`.

### MongoDB не отвечает
Handler не падает, просто пропускает запись с back-off 30 секунд. Проверьте:
- `MONGO_URI` правильный
- IP в Atlas Network Access (если используется Atlas)
- Из контейнера: `docker compose exec web python -c "from pymongo import MongoClient; import os; print(MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=5000).admin.command('ping'))"`

### `mysql.W002` Strict mode not set
Это warning, не ошибка. В Docker mysql:8.0 строгий режим включён по умолчанию. На shared учебном сервере не выключить.

### Throttle не срабатывает на login
Убедитесь, что в `LoginView` есть `throttle_scope = 'login'`.
Без Redis throttle работает per-process — для 3 воркеров фактический лимит будет 15/min вместо 5/min.

### Сборка Docker падает на `mysqlclient`
На Alpine драйвер собирается из исходников. Проверь что `apk add mariadb-connector-c-dev pkgconf build-base` есть в builder-стадии Dockerfile (уже есть).

### Статика не отдаётся через nginx
- Проверь что `STATIC_ROOT = BASE_DIR / 'staticfiles'` в settings
- `docker compose exec web python manage.py collectstatic --noinput` (entrypoint делает это сам)
- `docker compose exec nginx ls /app/staticfiles/` должно показать собранные файлы

### `docker compose up` не находит `.env`
Compose читает `.env` из текущей директории. Запускай из корня проекта.

---

## Лицензия

Учебный проект, лицензия не определена.

## Авторство

Создан в рамках финального проекта курса.
