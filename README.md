# WOLFF — веб-сервис грузов

Лабораторная 4. FastAPI, PostgreSQL, SQLAlchemy, Redis и MinIO.
Авторизация работает через cookie-сессии Redis; пароли хранятся как Argon2id-хеши.

## Запуск

Из каталога проекта, с установленными Docker и Python 3.12:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Если `.env` отсутствует, создать его из `.env.example` и проверить настройки
подключений. При существующем `.env` оставить свою конфигурацию.

```bash
docker compose up -d
.venv/bin/alembic upgrade head
.venv/bin/python main.py
```

При использовании существующего окружения `../venv_for_tiktok` команды можно
выполнять его интерпретатором вместо `.venv/bin/python`.

Swagger: http://127.0.0.1:8000/docs. HTML-каталог: http://127.0.0.1:8000/.
MinIO Console: http://localhost:9101. Adminer: http://localhost:8080.
PostgreSQL доступен с хоста на порту 5433, Redis — на 6379.
Бэкенд запускается отдельно от контейнеров хранилищ.

## Вход и доступ

Для нового пользователя выполнить `POST /api/users`: `user_login`, `user_name`,
`user_password` длиной 8–128 символов. Затем выполнить `POST /api/authentication`
с логином и паролем. Ответ устанавливает HttpOnly cookie `session_id`.
В Swagger браузер отправляет её автоматически; ввод через кнопку Authorize не нужен.
В Postman передавать заголовок `Cookie: session_id=<значение>`.
Использовать один адрес, например `127.0.0.1`, для входа и остальных запросов.

Каталог и лента доступны гостю. Создание, свой черновик, публикация, удаление
и лайки требуют сессии. Гостю защищённый метод возвращает 401, попытке изменить
чужой груз — 403. Создатель и автор лайка определяются из сессии на сервере.
Выход `POST /api/deauthentication` удаляет текущую сессию и cookie.
Коллекция запросов: [Postman](postman/lab4-authorization.postman_collection.json).

## HTTP-методы

| № | Метод | URL | Входные данные и результат |
|---|---|---|---|
| 1 | GET | `/api/cargos?cargo_mass=4` | Только опубликованные грузы с массой от 4 т. Без фильтра или с `0` — все опубликованные. `is_creator`: 1 для своего груза, 0 для чужого |
| 2 | GET | `/api/cargos/feed` | Один опубликованный груз. Без параметров — первый; `?cargo_id=27` — указанный; `?cargo_id=27&next=true` — следующий по ID, после последнего снова первый. `is_liked`: личный лайк 0/1 |
| 3 | GET | `/api/cargos/draft` | Нужен вход. Единственный черновик пользователя из сессии. ID не передаётся. Если черновика нет — 404 |
| 4 | POST | `/api/cargos` | После входа создаёт свой черновик. Только 3 обязательных поля multipart/form-data: `cargo_name`, файл `image`, файл `video`. Ответ 201 |
| 5 | PUT | `/api/cargos/{cargo_id}` | После входа публикует свой черновик. Можно передать JSON с необязательными `cargo_description`, `cargo_mass`, `cargo_volume`; можно без тела. Ответ 200 |
| 6 | DELETE | `/api/cargos/{cargo_id}` | После входа мягко удаляет свой черновик или опубликованный груз. Ответ 204 без тела |
| 7 | POST | `/api/cargos/{cargo_id}/likes` | Нужен вход. JSON `{"interest": 1}` ставит личный лайк, `{"interest": 0}` снимает. Автор определяется на сервере |
| 8 | POST | `/api/users` | Публичная регистрация: `user_login`, `user_name`, `user_password` (8–128 символов). В БД только Argon2id-хеш. Ответ 201 без пароля |
| 9 | POST | `/api/authentication` | Вход: JSON с `user_login`, `user_password`. Создаёт Redis-сессию и HttpOnly cookie `session_id`. Ответ 200 с пользователем и временем жизни; неверный пароль — 401 |
| 10 | POST | `/api/deauthentication` | Выход без тела. Удаляет сессию в Redis и cookie. Ответ 204; повторный выход без cookie разрешён |


## Правила работы с грузом

При создании передаются ровно три обязательных поля multipart/form-data:
название `cargo_name`, файл фото `image` и файл видео `video`.
Описание, масса и объём сначала равны `null`; их можно передать при публикации
через PUT. Масса — в тоннах, объём — в м³; числа конечные и неотрицательные.
PUT без тела допускается. Фильтр `cargo_mass=4` выбирает массу от 4 тонн.

Разрешены переходы `draft → published`, `draft → deleted`, `published → deleted`.
Возврата в черновик нет. Удаление логическое, удалённые грузы клиенту не выдаются.
У пользователя не более одного черновика. Публикация повторно возвращает 409.
Системные поля, статус, создатель и даты не принимаются для изменения с клиента.

`is_creator` показывает принадлежность груза, `is_liked` — личный лайк в ленте,
`interest_marks` — общее число лайков. `interest=1` ставит лайк, `interest=0` снимает.
Повторная установка не создаёт дубликатов. Лента без ID возвращает первый груз;
с `cargo_id` и `next=true` — следующий, после последнего снова первый.
`next=true` без `cargo_id` возвращает 422.

Файлы хранятся в бакете MinIO `cargo-media`, в БД — их имена на латинице.
В ответе есть вычисленные `image_public_url` и `video_public_url`.
Лимит каждого файла — 30 МиБ. Изображения: JPG/JPEG, PNG, WebP, GIF;
видео: MP4, WebM, MOV. Docker volumes сохраняют БД, файлы и сессии.

## Таблицы базы данных

### users

| Поле | Тип | Назначение |
|---|---|---|
| user_id | integer, PK | ID пользователя, назначается БД |
| user_login | varchar(64), UNIQUE, NOT NULL | Уникальный логин |
| user_name | varchar(128), NOT NULL | Отображаемое имя |
| password_hash | varchar(512), NULL для старых записей | Argon2id-хеш пароля; через API не выдаётся |

### cargos

| Поле | Тип | Назначение |
|---|---|---|
| cargo_id | integer, PK | ID груза, назначается БД |
| cargo_name | varchar(256), NOT NULL | Название, обязательно при создании |
| cargo_description | text, NULL | Необязательное описание |
| publication_status | varchar(32), NOT NULL | draft / published / deleted |
| image_url | varchar(512), NOT NULL | Имя файла изображения в MinIO; старые записи могут содержать URL |
| video_url | varchar(512), NOT NULL | Имя файла видео в MinIO; старые записи могут содержать URL |
| cargo_mass | float, NULL | Масса в тоннах |
| cargo_volume | float, NULL | Объём в м³ |
| created_at | timestamp, NOT NULL | Дата создания на сервере, UTC |
| formed_at | timestamp, NOT NULL | При создании — время создания, при публикации обновляется |
| creator_user_id | integer, FK → users.user_id, NOT NULL | Создатель из действующей сессии |

Частичный уникальный индекс `uq_cargos_one_draft_per_creator` запрещает
более одного черновика одного пользователя. Он создаётся миграцией 001.
Миграция 002 переводит массу/объём в float, миграция 003 разрешает NULL
для описания, массы и объёма. Полей модератора и завершения в текущей модели нет.

### cargo_interest_marks

| Поле | Тип | Назначение |
|---|---|---|
| mark_id | integer, PK | ID отметки |
| user_id | integer, FK → users.user_id, NOT NULL | Пользователь, поставивший лайк |
| cargo_id | integer, FK → cargos.cargo_id, NOT NULL | Груз |

Ограничение UNIQUE(user_id, cargo_id) запрещает повторный лайк одной пары.
`is_creator`, `is_liked`, `interest_marks` и публичные URL вычисляются в
ответах API и отдельными столбцами в таблицах не хранятся.
