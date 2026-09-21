# backend_cargo_analize

Лабораторная: FastAPI, Jinja, PostgreSQL, Minio.

## Запуск

```bash
cd backend_cargo_analize
cp .env.example .env
docker compose up -d
pip install -r requirements.txt
alembic upgrade head
python3 main.py
```

Приложение: http://127.0.0.1:8000  
Adminer: http://localhost:8080 — PostgreSQL, сервер `postgres`, логин и пароль `cargo`, база `cargo_db`.  
Postgres с хоста: порт `5433`.

Фронт: `cargo_front/templates`, статика: `cargo_front/static`.
