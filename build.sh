#!/usr/bin/env bash
# Render build step: install deps, collect static, run migrations, and
# (optionally) create the first admin/login user from env vars.
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Create a login for the extension if DJANGO_SUPERUSER_* env vars are set.
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  python manage.py createsuperuser --no-input || true
fi
