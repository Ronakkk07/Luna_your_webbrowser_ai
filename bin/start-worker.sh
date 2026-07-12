#!/usr/bin/env bash
# Celery worker entrypoint: runs the heavy/slow jobs (Whisper transcription, web
# research, LLM chains) off the web tier. Set ENABLE_WHISPER=true on this service
# only if you want server-side speech-to-text (needs ~1GB+ RAM).
set -o errexit

exec celery -A luna_backend worker \
  --loglevel="${CELERY_LOGLEVEL:-info}" \
  --concurrency="${CELERY_CONCURRENCY:-2}"
