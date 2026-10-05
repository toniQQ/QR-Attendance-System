#!/usr/bin/env bash
#
# Deploy QR Attendance System to conference.intelligentso.com.
#
# Run from the project root on the server:
#     bash deploy/deploy.sh
#
# Server already runs nginx + certbot as user quinto (passwordless sudo);
# this script does NOT install system packages.

set -euo pipefail

DOMAIN="conference.intelligentso.com"
APP_USER="quinto"
APP_DIR="/home/${APP_USER}/QR-Attendance-System"
VENV="${APP_DIR}/venv"
EMAIL="${CERTBOT_EMAIL:-admin@intelligentso.com}"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

log "Creating virtualenv and installing Python deps"
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install -r "${APP_DIR}/requirements.txt"

log "Ensuring .env exists"
if [ ! -f "${APP_DIR}/.env" ]; then
    cp "${APP_DIR}/deploy/.env.example" "${APP_DIR}/.env"
    SECRET=$("${VENV}/bin/python" -c \
        "import secrets; print(secrets.token_urlsafe(50))")
    sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY='${SECRET}'|" "${APP_DIR}/.env"
    echo "Created ${APP_DIR}/.env"
fi

log "Running migrations and collecting static files"
set -a; source "${APP_DIR}/.env"; set +a
mkdir -p "${APP_DIR}/logs"
"${VENV}/bin/python" "${APP_DIR}/manage.py" check --deploy || true
"${VENV}/bin/python" "${APP_DIR}/manage.py" migrate --noinput
"${VENV}/bin/python" "${APP_DIR}/manage.py" collectstatic --noinput

log "Installing systemd service"
sudo cp "${APP_DIR}/deploy/qr-attendance.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable qr-attendance
sudo systemctl restart qr-attendance

log "Installing Nginx site (pre-SSL)"
sudo cp "${APP_DIR}/deploy/nginx.conf" \
    "/etc/nginx/sites-available/${DOMAIN}.conf"
sudo ln -sf "/etc/nginx/sites-available/${DOMAIN}.conf" \
    "/etc/nginx/sites-enabled/${DOMAIN}.conf"
sudo nginx -t
sudo systemctl reload nginx

log "Requesting TLS certificate (certbot rewrites the nginx site for SSL)"
if ! sudo certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos \
        -m "${EMAIL}" --redirect --keep-until-expiring; then
    echo "certbot failed - verify ${DOMAIN} resolves here, then run:"
    echo "  sudo certbot --nginx -d ${DOMAIN}"
fi

log "Done. Verify with: curl -I https://${DOMAIN}/"
echo "Create the first admin with:"
echo "  ${VENV}/bin/python ${APP_DIR}/manage.py createsuperuser"
