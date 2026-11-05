#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP_ROOT="/srv/patent_agent"
SERVICE_USER="patent"
ENV_FILE="/etc/patent-agent.env"
STATE_DIR="/var/lib/patent-agent"
SETUP_MARKER="$STATE_DIR/setup-complete"
FIXTURE_MARKER="$STATE_DIR/portal-fixture-imported"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ "$EUID" -ne 0 ]]; then
    die "Run this script with sudo: sudo bash deployment/civo/setup-vm.sh"
fi

[[ -r /etc/os-release ]] || die "Cannot identify the operating system."
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]] || die "This script supports Ubuntu 24.04."
[[ "$REPO_ROOT" == "$APP_ROOT" ]] || die "The repository must be checked out at $APP_ROOT (found $REPO_ROOT)."
[[ -f "$APP_ROOT/requirements.txt" ]] || die "Root requirements.txt is missing."
[[ -f "$APP_ROOT/deployment/civo/patent-agent.env.example" ]] || die "The Civo environment template is missing."

if systemctl is-active --quiet patent-agent-api || systemctl is-active --quiet patent-portal; then
    die "Patent Agent services are already running. This setup script is for a new VM and will not alter a live deployment."
fi
[[ ! -e "$SETUP_MARKER" ]] || die "Setup is already marked complete."

printf 'Installing system packages...\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    acl build-essential ca-certificates certbot curl git libpq-dev nginx \
    openssl postgresql postgresql-contrib python3.12 python3.12-dev \
    python3.12-venv python3-pip python3-dev python3-certbot-nginx sudo

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "/home/$SERVICE_USER" --create-home --shell /bin/bash "$SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$APP_ROOT/data"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
    "$APP_ROOT/data/chroma_db" "$APP_ROOT/data/portal_media" "$APP_ROOT/data/reports"
install -d -o root -g root -m 0755 "$STATE_DIR"

printf 'Building the React frontend with Node 22...\n'
if [[ ! -s "/home/$SERVICE_USER/.nvm/nvm.sh" ]]; then
    sudo -u "$SERVICE_USER" -H bash -c \
        'cd /home/patent && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash'
fi
sudo -u "$SERVICE_USER" -H bash -c \
    'cd /home/patent && export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && nvm install 22 && nvm alias default 22 && cd /srv/patent_agent/web_portal/frontend && nvm use 22 && node --version && npm ci && npm run build'

printf 'Creating Python environments and installing dependencies...\n'
if [[ ! -x "$APP_ROOT/.venv-ai/bin/python" ]]; then
    sudo -u "$SERVICE_USER" -H python3.12 -m venv "$APP_ROOT/.venv-ai"
fi
if [[ ! -x "$APP_ROOT/.venv-portal/bin/python" ]]; then
    sudo -u "$SERVICE_USER" -H python3.12 -m venv "$APP_ROOT/.venv-portal"
fi
requirements_tmp="$(mktemp /tmp/patent-agent-requirements-cpu.XXXXXX)"
trap 'rm -f "${requirements_tmp:-}"' EXIT
grep -Ev '^(torch|torchaudio|torchvision)([<=>].*)?$' "$APP_ROOT/requirements.txt" > "$requirements_tmp"
chmod 0644 "$requirements_tmp"
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-ai/bin/python" -m pip install --upgrade pip wheel
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-ai/bin/python" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-ai/bin/python" -m pip install -r "$requirements_tmp"
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-portal/bin/python" -m pip install --upgrade pip wheel
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-portal/bin/python" -m pip install -r "$APP_ROOT/web_portal/requirements.txt"
rm -f "$requirements_tmp"
trap - EXIT

printf 'Installing and starting Ollama...\n'
if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
install -d -m 0755 /etc/systemd/system/ollama.service.d
install -o root -g root -m 0644 "$APP_ROOT/deployment/civo/ollama-service-override.conf" \
    /etc/systemd/system/ollama.service.d/override.conf
systemctl daemon-reload
systemctl enable --now ollama
systemctl restart ollama
ollama pull mistral

if [[ ! -f "$ENV_FILE" ]]; then
    printf '\nConfigure the production environment. Values are stored in %s.\n' "$ENV_FILE"
    read -r -p 'Public hostname (for example patentdesk.example.com): ' DOMAIN
    read -r -p 'Email for certificate expiry notices: ' CERT_EMAIL
    read -r -p 'Google OAuth client ID (leave blank to configure later): ' GOOGLE_CLIENT_ID
    read -r -s -p 'Google OAuth client secret (leave blank to configure later): ' GOOGLE_CLIENT_SECRET
    printf '\n'
    [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "Enter a valid public hostname."
    [[ "$CERT_EMAIL" == *@*.* ]] || die "Enter a valid email address for Certbot."

    DB_PASSWORD="$(openssl rand -hex 24)"
    DJANGO_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"

    role_exists="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'patent_portal'")"
    if [[ "$role_exists" != "1" ]]; then
        runuser -u postgres -- createuser --login patent_portal
    fi
    printf "ALTER ROLE patent_portal WITH LOGIN PASSWORD '%s';\n" "$DB_PASSWORD" \
        | runuser -u postgres -- psql -v ON_ERROR_STOP=1 >/dev/null
    db_exists="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname = 'patent_portal'")"
    if [[ "$db_exists" != "1" ]]; then
        runuser -u postgres -- createdb --owner patent_portal patent_portal
    fi

    env_tmp="$(mktemp /tmp/patent-agent-env.XXXXXX)"
    export PATENT_ENV_DOMAIN="$DOMAIN"
    export PATENT_ENV_DB_PASSWORD="$DB_PASSWORD"
    export PATENT_ENV_DJANGO_SECRET="$DJANGO_SECRET"
    export PATENT_ENV_GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID"
    export PATENT_ENV_GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET"
    python3 - "$APP_ROOT/deployment/civo/patent-agent.env.example" "$env_tmp" <<'PY'
import os
import sys
from pathlib import Path

template = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
domain = os.environ["PATENT_ENV_DOMAIN"]
values = {
    "DJANGO_SECRET_KEY": os.environ["PATENT_ENV_DJANGO_SECRET"],
    "DJANGO_DEBUG": "false",
    "DJANGO_ALLOWED_HOSTS": domain,
    "CSRF_TRUSTED_ORIGINS": f"https://{domain}",
    "DATABASE_URL": (
        "postgresql://patent_portal:"
        f"{os.environ['PATENT_ENV_DB_PASSWORD']}@127.0.0.1:5432/patent_portal"
    ),
    "GOOGLE_OAUTH_CLIENT_ID": os.environ["PATENT_ENV_GOOGLE_CLIENT_ID"],
    "GOOGLE_OAUTH_CLIENT_SECRET": os.environ["PATENT_ENV_GOOGLE_CLIENT_SECRET"],
    "GOOGLE_OAUTH_REDIRECT_URI": f"https://{domain}/api/auth/google/callback/",
    "PORTAL_FRONTEND_URL": f"https://{domain}",
}
output = []
written = set()
for line in template:
    if line and not line.startswith("#") and "=" in line:
        key = line.split("=", 1)[0]
        if key in values:
            value = values[key]
            if "\n" in value or "\r" in value:
                raise SystemExit(f"Newline is not valid in {key}.")
            output.append(f"{key}={value}")
            written.add(key)
            continue
    output.append(line)
missing = set(values) - written
if missing:
    raise SystemExit(f"Template is missing keys: {', '.join(sorted(missing))}")
Path(sys.argv[2]).write_text("\n".join(output) + "\n", encoding="utf-8")
PY
    install -o root -g "$SERVICE_USER" -m 0640 "$env_tmp" "$ENV_FILE"
    rm -f "$env_tmp"
    unset PATENT_ENV_DOMAIN PATENT_ENV_DB_PASSWORD PATENT_ENV_DJANGO_SECRET \
        PATENT_ENV_GOOGLE_CLIENT_ID PATENT_ENV_GOOGLE_CLIENT_SECRET DB_PASSWORD DJANGO_SECRET GOOGLE_CLIENT_SECRET
    printf 'Created the protected environment file.\n'
else
    printf 'Using the existing protected environment file without changing it.\n'
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    DOMAIN="${DJANGO_ALLOWED_HOSTS%%,*}"
    read -r -p 'Email for certificate expiry notices: ' CERT_EMAIL
    [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "DJANGO_ALLOWED_HOSTS must contain a hostname."
    [[ "$CERT_EMAIL" == *@*.* ]] || die "Enter a valid email address for Certbot."
fi

printf 'Installing staged application data...\n'
for name in chroma_db portal_media reports; do
    source_dir="/tmp/patent-agent-data/$name"
    destination_dir="$APP_ROOT/data/$name"
    if [[ -d "$source_dir" ]]; then
        cp -an "$source_dir/." "$destination_dir/"
    fi
done
if [[ -f /tmp/patent-agent-data/patent_agent.db && ! -e "$APP_ROOT/patent_agent.db" ]]; then
    install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0640 \
        /tmp/patent-agent-data/patent_agent.db "$APP_ROOT/patent_agent.db"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_ROOT/data"
[[ -d "$APP_ROOT/data/chroma_db/full_cpc_db" ]] || die "Chroma data is missing. Stage data/chroma_db/full_cpc_db before setup."

run_portal_manage() {
    sudo -u "$SERVICE_USER" -H bash -c '
        cd /home/patent
        set -a
        . /etc/patent-agent.env
        set +a
        cd /srv/patent_agent/web_portal
        exec /srv/patent_agent/.venv-portal/bin/python manage.py "$@"
    ' -- "$@"
}

printf 'Applying Django migrations...\n'
run_portal_manage migrate

if [[ -f /tmp/patent-agent-data/portal-data.json && ! -e "$FIXTURE_MARKER" ]]; then
    install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0600 \
        /tmp/patent-agent-data/portal-data.json "$APP_ROOT/portal-data.json"
    printf 'A portal data fixture is staged. It imports local users and records.\n'
    read -r -p 'Import this fixture into PostgreSQL now? [y/N] ' import_fixture
    if [[ "$import_fixture" =~ ^[Yy]$ ]]; then
        run_portal_manage loaddata "$APP_ROOT/portal-data.json"
        touch "$FIXTURE_MARKER"
    fi
fi

run_portal_manage collectstatic --noinput
read -r -p 'Create an additional Django superuser? Answer yes only if the imported data has no admin account [y/N] ' create_admin
if [[ "$create_admin" =~ ^[Yy]$ ]]; then
    run_portal_manage createsuperuser
fi

printf 'Granting Nginx access to static files only...\n'
setfacl -m u:www-data:--x "$APP_ROOT" "$APP_ROOT/web_portal" "$APP_ROOT/web_portal/frontend"
setfacl -R -m u:www-data:rX "$APP_ROOT/web_portal/frontend/dist" "$APP_ROOT/web_portal/staticfiles"
setfacl -m d:u:www-data:rX "$APP_ROOT/web_portal/frontend/dist" "$APP_ROOT/web_portal/staticfiles"

install -o root -g root -m 0644 "$APP_ROOT/deployment/civo/patent-agent-api.service" \
    /etc/systemd/system/patent-agent-api.service
install -o root -g root -m 0644 "$APP_ROOT/deployment/civo/patent-portal.service" \
    /etc/systemd/system/patent-portal.service
public_ipv4="$(curl -4 -fsSL https://api.ipify.org | tr -d '\r\n')"
dns_ipv4="$(getent ahostsv4 "$DOMAIN" | awk 'NR == 1 { print $1; exit }')"
[[ -n "$dns_ipv4" && "$dns_ipv4" == "$public_ipv4" ]] || \
    die "DNS for $DOMAIN must resolve to this VM's public IPv4 ($public_ipv4); found ${dns_ipv4:-no A record}."

install -d -o www-data -g www-data -m 0755 /var/www/letsencrypt/.well-known/acme-challenge
install -d -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled
if [[ ! -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    python3 - "$APP_ROOT/deployment/civo/nginx-bootstrap.conf" /etc/nginx/sites-available/patent-agent "$DOMAIN" <<'PY'
import sys
from pathlib import Path

source, destination, domain = sys.argv[1:]
content = Path(source).read_text(encoding="utf-8").replace("portal.example.com", domain)
Path(destination).write_text(content, encoding="utf-8")
PY
    ln -sfn /etc/nginx/sites-available/patent-agent /etc/nginx/sites-enabled/patent-agent
    nginx -t
    systemctl reload nginx
    certbot certonly --non-interactive --webroot -w /var/www/letsencrypt \
        -d "$DOMAIN" -m "$CERT_EMAIL" --agree-tos --no-eff-email
fi

python3 - "$APP_ROOT/web_portal/nginx.conf.example" /etc/nginx/sites-available/patent-agent "$DOMAIN" <<'PY'
import sys
from pathlib import Path

source, destination, domain = sys.argv[1:]
content = Path(source).read_text(encoding="utf-8").replace("portal.example.com", domain)
Path(destination).write_text(content, encoding="utf-8")
PY
ln -sfn /etc/nginx/sites-available/patent-agent /etc/nginx/sites-enabled/patent-agent
nginx -t
systemctl reload nginx
systemctl daemon-reload
systemctl enable --now patent-agent-api patent-portal
systemctl restart patent-agent-api patent-portal
systemctl enable --now certbot.timer

touch "$SETUP_MARKER"
printf '\nDeployment setup finished. Open https://%s/\n' "$DOMAIN"
if [[ -z "${GOOGLE_OAUTH_CLIENT_ID:-}" || -z "${GOOGLE_OAUTH_CLIENT_SECRET:-}" ]]; then
    printf 'Google OAuth credentials are blank; add them to %s before testing sign-in.\n' "$ENV_FILE"
fi
printf 'Check status with: systemctl status patent-agent-api patent-portal nginx --no-pager\n'
