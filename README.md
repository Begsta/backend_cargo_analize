# Веб-сервис грузов WOLFF

Лабораторная 3: REST-веб-сервис бэкенда для SPA. Данные читаются и меняются через ORM (SQLAlchemy), файлы изображения и видео складываются в MinIO. Авторизация не реализуется: во всех методах груза текущий пользователь задан константой в функции-singleton.

Страницы предыдущих лабораторных (каталог, лента, добавление) по-прежнему открываются с того же процесса. Новый контракт для SPA — адреса с префиксом `/api`.

## Запуск

```bash
cd backend_cargo_analize
cp .env.example .env
docker compose up -d
pip install -r requirements.txt
alembic upgrade head
docker compose exec -T postgres psql -U cargo -d cargo_db < db/seed.sql
python3 main.py
```

- Приложение и API: http://127.0.0.1:8000
- OpenAPI: http://127.0.0.1:8000/docs
- Adminer: http://localhost:8080 — сервер `postgres`, логин и пароль `cargo`, база `cargo_db`
- Postgres с хоста: порт `5433`
- MinIO API: http://localhost:9100 , консоль: http://localhost:9101 (`root` / `rootpassword`). Порты 9000–9004 на этой машине заняты, поэтому наружу MinIO выведен на 9100 и 9101.
- Коллекция запросов: `postman/lab3-web-service.postman_collection.json` (импорт в Insomnia или Postman)

Пользователь singleton — строка `users.user_id = 1`. Если её ещё нет, `db/seed.sql` создаёт логин `wolff`.

## Текущий пользователь

Файл `core/current_user.py`, функция `get_current_user_id`. Константа `1` записывается один раз и дальше возвращается тот же идентификатор. Её вызывают методы домена груза: список (`is_creator`), черновик, создание, публикация, удаление и лайк. Клиент не передаёт создателя.

## HTTP-методы

Системные поля клиент на запись не передаёт: `cargo_id`, `publication_status`, `creator_user_id`, `created_at`, `formed_at`. Их выставляет сервер. Если прислать их в форме создания груза, ответ `422`. Во входных JSON-схемах лишние поля тоже запрещены (`extra=forbid`): `user_id` в регистрации и лайке даёт `422`. Удалённые грузы (`deleted`) ни один GET не возвращает.

### Домен груза

| Метод | URL | Назначение |
|---|---|---|
| GET | `/api/cargos?cargo_mass=` | Список только опубликованных. Фильтр как в лабораторной 1: масса в тоннах и больше. `0` или пустой параметр — все опубликованные. `is_creator`: `1`, если создатель совпадает с singleton, иначе `0` |
| GET | `/api/cargos/feed` | Лента без идентификатора: первый опубликованный груз |
| GET | `/api/cargos/feed/{cargo_id}?next=true` | Лента по идентификатору. `next=true` — следующий опубликованный, после последнего снова первый. Без `next` — сам груз, если он опубликован |
| GET | `/api/cargos/draft` | Черновик текущего пользователя. Идентификатор в адресе не указывается, черновик не больше одного |
| POST | `/api/cargos` | Добавление черновика. Поля формы: `cargo_name`, `cargo_description`, `cargo_mass`, `cargo_volume`, файлы `image` и `video`. В `image_url` и `video_url` пишутся латинские имена, байты — в бакет MinIO `cargo-media` |
| PUT | `/api/cargos/{cargo_id}` | Публикация: единственный переход `draft` → `published`. Тело не принимается. Чужой груз — 403, уже опубликованный — 409 |
| DELETE | `/api/cargos/{cargo_id}` | Мягкое удаление своего груза: статус `deleted`, строка остаётся. Ответ `204`, тело не отдаётся |
| POST | `/api/cargos/{cargo_id}/likes` | Отметка интереса текущего пользователя. JSON `{"interest": 0}` снимает, `{"interest": 1}` ставит. Только у опубликованного груза |

### Домен пользователя

| Метод | URL | Назначение |
|---|---|---|
| POST | `/api/users` | Регистрация. JSON: `user_login`, `user_name`. `user_id` назначает база |
| POST | `/api/authentication` | Заглушка лабораторной 4. Логин и пароль не проверяются |
| POST | `/api/deauthentication` | Заглушка лабораторной 4 |

### Статусы

У создателя два разных метода, произвольная смена статуса запрещена.

- POST создаёт `draft`
- PUT переводит только `draft` → `published` и обновляет `formed_at`
- DELETE переводит свой `draft` или `published` → `deleted`
- Обратно в `draft` метода нет

## Таблицы базы данных

### `users`

| Поле | Тип | Смысл |
|---|---|---|
| `user_id` | integer, PK | Идентификатор, назначает база |
| `user_login` | varchar(64), unique | Логин |
| `user_name` | varchar(128) | Имя |

### `cargos`

| Поле | Тип | Смысл |
|---|---|---|
| `cargo_id` | integer, PK | Идентификатор, назначает база |
| `cargo_name` | varchar(256) | Название |
| `cargo_description` | text | Описание |
| `publication_status` | varchar(32) | `draft`, `published` или `deleted`. Меняет только сервер |
| `image_url` | varchar(512) | Латинское имя файла изображения в MinIO |
| `video_url` | varchar(512) | Латинское имя файла видео в MinIO |
| `cargo_mass` | integer | Масса, т |
| `cargo_volume` | integer | Объём, м³ |
| `created_at` | timestamp | Дата создания, ставит сервер |
| `formed_at` | timestamp | Дата формирования, обновляется при публикации |
| `creator_user_id` | integer, FK → `users.user_id` | Создатель. В этой лабораторной всегда singleton |

Один черновик на создателя: уникальный частичный индекс `uq_cargos_one_draft_per_creator`.

Отдельных полей модератора и даты завершения в этой предметной области нет.

### `cargo_interest_marks`

| Поле | Тип | Смысл |
|---|---|---|
| `mark_id` | integer, PK | Идентификатор отметки |
| `user_id` | integer, FK → `users.user_id` | Кто поставил |
| `cargo_id` | integer, FK → `cargos.cargo_id` | Какой груз |

Пара (`user_id`, `cargo_id`) уникальна (`uq_interest_user_cargo`). Снятие лайка удаляет строку отметки. Мягкое удаление относится только к грузу.

## Проверка данных после запросов

```sql
SELECT cargo_id, cargo_name, publication_status, image_url, video_url,
       creator_user_id, created_at, formed_at
FROM cargos
ORDER BY cargo_id;

SELECT mark_id, user_id, cargo_id
FROM cargo_interest_marks
ORDER BY mark_id;

SELECT user_id, user_login, user_name
FROM users
ORDER BY user_id;
```

У опубликованного через PUT груза статус `published`, в `image_url` и `video_url` латинские имена. После DELETE статус `deleted`, и этот груз пропадает из списка и ленты. После лайка появляется строка в `cargo_interest_marks` с `user_id = 1`. После регистрации — новая строка в `users`.

## Диаграмма классов

Зависимости такие, как в коде: страницы ходят в домены, домены — в модели, модели отображаются на таблицы.

```mermaid
classDiagram
    class CatalogPage {
        <<страница Каталог>>
        index.html
    }
    class FeedPage {
        <<страница Лента>>
        lenta-podyoma.html
    }
    class AdditionPage {
        <<страница Добавление>>
        cargo_addition.html
    }
    class RegisterPage {
        <<страница Регистрация>>
        домен пользователя
    }

    class CargoDomain {
        <<интерфейс /api/cargos>>
        +GET /api/cargos
        +GET /api/cargos/feed
        +GET /api/cargos/feed/{id}?next=
        +GET /api/cargos/draft
        +POST /api/cargos
        +PUT /api/cargos/{id}
        +DELETE /api/cargos/{id}
        +POST /api/cargos/{id}/likes
    }
    class UserDomain {
        <<интерфейс /api>>
        +POST /api/users
        +POST /api/authentication
        +POST /api/deauthentication
    }

    class Cargo
    class User
    class Like
    class cargos
    class users
    class cargo_interest_marks

    CatalogPage --> CargoDomain : список, удаление
    FeedPage --> CargoDomain : лента, лайк
    AdditionPage --> CargoDomain : черновик, создание, публикация
    RegisterPage --> UserDomain : регистрация, заглушки входа

    CargoDomain --> Cargo
    CargoDomain --> Like
    CargoDomain --> User : создатель singleton
    UserDomain --> User

    Cargo --> cargos
    User --> users
    Like --> cargo_interest_marks
```

Четыре страницы: каталог, лента и добавление уже есть в `cargo_front/templates`. Регистрация — четвёртая страница домена пользователя; шаблона у неё пока нет, метод `POST /api/users` для неё готов.

## Контрольные вопросы

**Веб-сервис.** Программа, к которой другая программа обращается по сети через описанный контракт. Здесь контракт — HTTP JSON на `/api`, клиент — SPA.

**REST.** Стиль поверх HTTP: сущность задаётся адресом (`/api/cargos/5`), действие — методом (GET прочитать, POST создать, PUT заменить состояние публикации, DELETE удалить). Сервер не помнит, на каком шаге формы остановился клиент: каждый запрос самодостаточен.

**RPC.** Удалённый вызов процедуры. В адресе обычно глагол (`/publishCargo`), а не ресурс. Отличие от REST в том, что операция называется в URL, а не выбирается методом HTTP. Заглушки `/api/authentication` и `/api/deauthentication` ближе к RPC: это действия, а не ресурс.

**Методы HTTP.** GET — чтение без изменения. POST — создание или действие (регистрация, лайк). PUT — запись состояния ресурса (публикация). DELETE — удаление. Ещё есть PATCH, HEAD, OPTIONS.

**Заголовки HTTP.** `Host` — куда идёт запрос. `Content-Type` — формат тела (`application/json` или `multipart/form-data` для файлов). `Content-Length` — размер тела. `Accept` — какой ответ ждёт клиент. `Authorization` — для лабораторной 4, сейчас не используется.

**Версии HTTP.** 1.0 — отдельное соединение на запрос. 1.1 — постоянное соединение и обязательный `Host`. 2 — несколько запросов в одном соединении, бинарное кадрирование. 3 — тот же смысл поверх QUIC (UDP), а не TCP.

**HTTPS.** HTTP внутри TLS: трафик шифруется, клиент проверяет сертификат сервера. Для этой лабораторной сервис поднят по HTTP на localhost.

**OSI ISO.** Семь уровней. По этому сервису: прикладной (7) — HTTP и смысл `/api`, представления (6) — JSON и TLS при HTTPS, сеансовый (5) — в чистом виде почти не виден, транспортный (4) — TCP (порт 8000), сетевой (3) — IP, канальный (2) и физический (1) — сеть машины. HTTPS добавляет TLS между HTTP и TCP.
