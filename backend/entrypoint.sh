#!/bin/sh
set -e

python manage.py collectstatic --no-input
python manage.py migrate --no-input

# The dashboard advertises a pre-filled demo account, so make sure it exists.
# seed_demo is idempotent; a failure here must not keep the API offline.
python manage.py seed_demo || echo "[entrypoint] seed_demo skipped"

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 3 \
    --access-logfile -