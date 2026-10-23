#!/bin/sh
# gunicorn in the background, nginx in the foreground, mirroring how ise-test ran
# this app. If gunicorn dies the container must die with it -- otherwise nginx
# keeps answering and /api/health keeps returning 200 while every real page
# 502s, the failure mode where every signal says the deploy worked.
set -e

# settings.py hardcodes the SQLite file as BASE_DIR / "db.sqlite3", so it cannot
# be pointed at a volume by configuration. Symlink it onto the volume instead of
# editing the app: SQLite follows the symlink and writes its -wal and -shm
# alongside the real file, on the volume. Without this the database lives in the
# container layer and every redeploy silently discards it.
mkdir -p /app/data
if [ ! -e /app/data/db.sqlite3 ] && [ -f /app/db.sqlite3 ] && [ ! -L /app/db.sqlite3 ]; then
    mv /app/db.sqlite3 /app/data/db.sqlite3
fi
ln -sfn /app/data/db.sqlite3 /app/db.sqlite3

python manage.py migrate --noinput

gunicorn QR_Attendance_System.wsgi:application \
  --bind 127.0.0.1:3998 --workers 3 --threads 2 --timeout 120 \
  --keep-alive 5 --max-requests 1000 --max-requests-jitter 100 \
  --access-logfile - --error-logfile - --log-level info &
GUNICORN_PID=$!

( while kill -0 "$GUNICORN_PID" 2>/dev/null; do sleep 5; done
  echo "entrypoint: gunicorn exited — stopping nginx" >&2
  kill -TERM 1 2>/dev/null ) &

exec nginx -g 'daemon off;'
