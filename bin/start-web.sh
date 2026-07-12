#!/usr/bin/env bash
# Web service entrypoint: apply migrations, then serve with gunicorn.
# (For many web instances, move `migrate` to a one-off release step instead.)
set -o errexit

python manage.py migrate --no-input

exec gunicorn luna_backend.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads "${WEB_THREADS:-4}" \
  --timeout "${WEB_TIMEOUT:-120}"
