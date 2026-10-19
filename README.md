# Веб-сервис WOLFF — лабораторная 3

API содержит **10 HTTP-операций**: 7 в домене грузов и 3 в домене пользователей.
HTML-страницы предыдущих лабораторных работают отдельно и не включены в Swagger.
Коллекция для Postman: [10 методов](postman/lab3-corrected.postman_collection.json).

## HTTP-методы

| № | Метод | URL | Входные данные и результат |
|---|---|---|---|
| 1 | GET | `/api/cargos?cargo_mass=4` | Только опубликованные грузы с массой от 4 т. Без фильтра или с `0` — все опубликованные. `is_creator`: 1 для своего груза, 0 для чужого |
| 2 | GET | `/api/cargos/feed` | Один опубликованный груз. Без параметров — первый; `?cargo_id=27` — указанный; `?cargo_id=27&next=true` — следующий по ID, после последнего снова первый. `is_liked`: личный лайк 0/1 |
| 3 | GET | `/api/cargos/draft` | Единственный черновик пользователя singleton. ID не передаётся. Если черновика нет — 404 |
| 4 | POST | `/api/cargos` | Создаёт черновик. Только 3 обязательных поля multipart/form-data: `cargo_name`, файл `image`, файл `video`. Ответ 201 |
| 5 | PUT | `/api/cargos/{cargo_id}` | Публикует свой черновик. Можно передать JSON с необязательными `cargo_description`, `cargo_mass`, `cargo_volume`; можно без тела. Ответ 200 |
| 6 | DELETE | `/api/cargos/{cargo_id}` | Мягко удаляет свой черновик или опубликованный груз. Ответ 204 без тела |
| 7 | POST | `/api/cargos/{cargo_id}/likes` | JSON `{"interest": 1}` ставит личный лайк, `{"interest": 0}` снимает. Автор определяется на сервере |
| 8 | POST | `/api/users` | Регистрация: JSON с `user_login`, `user_name`. ID назначается БД. Ответ 201 |
| 9 | POST | `/api/authentication` | Заглушка: JSON с `user_login`, `user_password`. Возвращает `implemented: false` |
| 10 | POST | `/api/deauthentication` | Заглушка без тела. Возвращает `implemented: false` |

Лента — один метод с разными query-параметрами. Прежний API-адрес
`/api/cargos/feed/{cargo_id}?next=true` заменён на
`/api/cargos/feed?cargo_id={cargo_id}&next=true`.
Без `cargo_id` параметр `next=true` возвращает 422. Скрытые HTML-маршруты
`/cargo/{cargo_id}` и `/lift_feed` продолжают работать по прежним адресам.

`is_creator` сравнивает создателя с текущим пользователем. `is_liked` в ответе
ленты проверяет наличие строки в `cargo_interest_marks` для текущего
пользователя и показанного груза. `interest_marks` — общее число лайков всех
пользователей. Эти три значения имеют разный смысл: чужой груз может иметь
`is_creator: 0, is_liked: 1`, а свой — `is_creator: 1, is_liked: 0`.

## Создание и публикация

До кнопки «Далее» нужны **фото, видео и название**. POST принимает ровно эти
три поля. Системные и дополнительные поля в этой форме запрещены (422).
Форма HTML `/cargo_addition` тоже отправляет оба файла в MinIO.

Описание, масса и объём нового черновика равны SQL `NULL` и JSON `null`.
После создания их можно заполнить при публикации через PUT:

```json
{
  "cargo_description": "Подъём панели башенным краном",
  "cargo_mass": 5.5,
  "cargo_volume": 2
}
```

Все три поля необязательные. Если поле не передано, его текущее значение
сохраняется; `null` явно очищает значение. Пустое описание сохраняется как
`NULL`. Для массы и объёма разрешены конечные неотрицательные числа; `0`
сохраняется числом. PUT без тела публикует черновик без добавления характеристик.
После публикации этот PUT повторно использовать для редактирования нельзя.

Файлы отправляются как multipart-файлы, а не URL. В Postman для `image` и `video`
выбирается тип File. Заголовок multipart Content-Type вручную не устанавливается:
клиент добавляет boundary. В MinIO используется бакет `cargo-media`; имена
объектов генерируются как `image-{uuid}.png` и `video-{uuid}.mp4` на латинице.
В БД сохраняются имена объектов; поля ответа `image_public_url` и
`video_public_url` содержат готовые ссылки. Принимаемые типы и ограничение
30 МиБ на файл описаны в `core/storage.py`.

## Пользователь и статусы

`core/current_user.py:get_current_user_id()` — функция-singleton. При первом
вызове она запоминает `user_id = 1`, затем возвращает его во всех операциях.
В лабораторной 3 регистрации и заглушки входа/выхода не меняют этого пользователя.
В таблице `users` должна существовать запись с ID 1.

Допустимые переходы: `draft → published`, `draft → deleted`,
`published → deleted`. Возврат в черновик запрещён. Публикация и удаление
чужого груза возвращают 403; публикация уже опубликованного — 409.
Удалённые записи не выдаются в списке, ленте и черновике. Лайк разрешён
только для опубликованного груза. Повторная установка или отмена лайка
не создаёт дубликатов и не уменьшает счётчик ниже существующих отметок.

`cargo_id`, `publication_status`, `creator_user_id`, даты, а также
несуществующие в этой модели поля модератора/завершения не принимаются от
клиента. Статусы, создатель и даты заполняются сервером. В JSON лишние поля
запрещены схемами с `extra="forbid"`.

## Таблицы базы данных

### users

| Поле | Тип | Назначение |
|---|---|---|
| user_id | integer, PK | ID пользователя, назначается БД |
| user_login | varchar(64), UNIQUE, NOT NULL | Уникальный логин |
| user_name | varchar(128), NOT NULL | Отображаемое имя |

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
| creator_user_id | integer, FK → users.user_id, NOT NULL | Создатель из singleton |

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

## Запуск и проверка

Из каталога backend_cargo_analize, с подготовленным `.env` по `.env.example`:

```bash
docker compose up -d
../venv_for_tiktok/bin/alembic upgrade head
docker compose exec -T postgres psql -U cargo -d cargo_db < db/seed.sql
../venv_for_tiktok/bin/python main.py
```

Swagger: `http://127.0.0.1:8000/docs`, Adminer: `http://localhost:8080`,
MinIO Console: `http://localhost:9101` (порты по docker-compose.yml).
Для Adminer сервер БД — `postgres`, пользователь и БД — `cargo` и `cargo_db`;
пароль берётся из конфигурации окружения/Compose.

Импортировать `postman/lab3-corrected.postman_collection.json` в Postman.
В запросе 02 вручную выбрать фото и короткое видео. ID созданного груза
сохранится в `cargo_id`. В запросе 05 выключенные параметры позволяют
переключать режимы ленты; возвращённый ID сохраняется отдельно в `feed_cargo_id`.
До съёмки лайка/удаления убедиться, что выбран ID своего демонстрационного груза.

Проверки без внешних сервисов:

```bash
../venv_for_tiktok/bin/python -m unittest discover -s tests -v
```

Тесты выполняют HTTP-запросы через ASGI, используют ORM и временную SQLite
в памяти; MinIO подменён. Это проверяет контракты API, личный лайк, права,
публикацию и маршруты. Миграции PostgreSQL, настоящий MinIO и ручной прогон
коллекции проверяются отдельно на запущенных контейнерах.
