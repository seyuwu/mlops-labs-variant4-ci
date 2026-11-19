# Лабораторная работа 2 — платформа онлайн-обучения

Вариант 4: курсы, уроки, обучающиеся, прогресс и тесты. Файлы уроков хранятся в MinIO, данные — в PostgreSQL. Для локальных тестов используется SQLite.

## Лёгкая локальная проверка

```bash
pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --port 8000
```

Документация: http://127.0.0.1:8000/docs. Для отправки файлов локально нужен MinIO.

## Контейнеры

```bash
docker compose up --build -d
docker compose ps
docker compose --profile monitoring up -d
docker compose down
```

Для ограниченной по ресурсам машины добавьте оба файла: `docker compose -f docker-compose.yml -f docker-compose.low-resource.yml up --build -d`. Мониторинг по-прежнему запускается отдельно с `--profile monitoring`.

API доступен через Nginx на http://127.0.0.1:8080/docs. Мониторинг включается отдельно, чтобы не занимать ресурсы постоянно. Данные PostgreSQL и MinIO сохраняются в томах. Для кеширования можно задать `REDIS_URL`; без него или при отказе Redis данные читаются из базы. Значения паролей по умолчанию предназначены только для локального учебного запуска; для другого окружения задайте переменные `POSTGRES_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `GRAFANA_PASSWORD`.
