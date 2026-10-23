# syntax=docker/dockerfile:1.7
# Django + gunicorn, with nginx in the same image serving /static/ and /media/.
#
# This is the only Python app in the estate; everything else is Node, so it does
# not use templates/Dockerfile.nextjs.
#
# nginx is here rather than relying on Django because DEBUG=False makes Django
# refuse to serve static files, and the ise-test vhost it replaces served
# /static/ and /media/ by alias with gunicorn behind it. Keeping that split
# means the app renders identically.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

FROM base AS deps
# libpq for psycopg2-binary's runtime, zlib/jpeg for Pillow.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r requirements.txt

FROM base AS runner
RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx libpq5 \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /etc/nginx/sites-enabled/default
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
COPY deploy/container-nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -rf /app/venv /app/logs /app/db.sqlite3 /app/media

# SECRET_KEY is required for collectstatic but is not a real secret at build
# time; the runtime value arrives from the environment.
RUN DJANGO_SECRET_KEY=build-only-not-used \
    python manage.py collectstatic --noinput \
 && mkdir -p /app/media /app/data

# db.sqlite3 and media/ are the only mutable state. Both come from volumes --
# baking them in is what made the previous image lose uploads on redeploy.
VOLUME ["/app/data", "/app/media"]

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/api/health',timeout=4).status==200 else 1)"
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
