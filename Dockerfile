# =========================================================================
# Stage 1 — builder: компилирует C-расширения (mysqlclient, Pillow и т.д.)
# =========================================================================
FROM python:3.13-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build-time зависимости. Эти пакеты НЕ попадают в финальный образ.
RUN apk add --no-cache \
        build-base \
        mariadb-connector-c-dev \
        pkgconf \
        jpeg-dev \
        zlib-dev \
        libffi-dev \
        openssl-dev

COPY requirements.txt .

# Собираем все зависимости в wheels (включая gunicorn для прода).
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels -r requirements.txt gunicorn


# =========================================================================
# Stage 2 — runtime: минимальный образ только с .so-библиотеками
# =========================================================================
FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=rental_project.settings

# Только runtime-библиотеки (без -dev и build-base).
RUN apk add --no-cache \
        mariadb-connector-c \
        libjpeg-turbo \
        zlib \
        libffi \
        openssl \
    && addgroup -S app && adduser -S app -G app

WORKDIR /app

# Ставим wheels из builder'а — без интернета, без компилятора.
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels

# Копируем код приложения.
COPY --chown=app:app . .

# Папки для логов и статики.
RUN mkdir -p /app/logs /app/staticfiles && chown -R app:app /app/logs /app/staticfiles

USER app

EXPOSE 8000

# Entrypoint ждёт БД, прогоняет миграции, собирает статику, потом CMD.
ENTRYPOINT ["python", "/app/docker_entrypoint.py"]

# Прод-сервер: gunicorn. Можно переопределить в compose для dev (runserver).
CMD ["gunicorn", "rental_project.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
