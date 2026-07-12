# Luna backend — single image used by both the web and the Celery worker services.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=luna_backend.settings

# ffmpeg is needed by faster-whisper on the worker; slim otherwise.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Collect static at build (WhiteNoise serves them). Uses the built-in defaults;
# real secrets are injected at runtime by Railway.
RUN DJANGO_DEBUG=false SECRET_KEY=build-only python manage.py collectstatic --no-input

EXPOSE 8000
CMD ["bash", "bin/start-web.sh"]
