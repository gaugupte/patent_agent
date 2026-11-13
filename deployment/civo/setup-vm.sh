#!/usr/bin/env bash
# Stop on errors, unset variables, and failed pipeline commands.
set -Eeuo pipefail
# Restrict default permissions for files created by this privileged script.
umask 077

# Define the application checkout and service-account locations.
APP_ROOT="/srv/patent_agent"
SERVICE_USER="patent"
# Keep credentials outside the repository in a protected system file.
ENV_FILE="/etc/patent-agent.env"
# Store setup completion and fixture-import markers outside the application tree.
STATE_DIR="/var/lib/patent-agent"
SETUP_MARKER="$STATE_DIR/setup-complete"
FIXTURE_MARKER="$STATE_DIR/portal-fixture-imported"
# Resolve the checkout root from this script's path for location validation.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Print a consistent error and terminate when a prerequisite is not met.
die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

# Require root so the script can install packages and configure system services.
if [[ "$EUID" -ne 0 ]]; then
    die "Run this script with sudo: sudo bash deployment/civo/setup-vm.sh"
fi

# Read Ubuntu release metadata and reject unsupported operating systems.
[[ -r /etc/os-release ]] || die "Cannot identify the operating system."
# shellcheck disable=SC1091
source /etc/os-release
# Limit automated setup to the Ubuntu release this runbook targets.
[[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]] || die "This script supports Ubuntu 24.04."
# Require the repository to be checked out at the fixed service path.
[[ "$REPO_ROOT" == "$APP_ROOT" ]] || die "The repository must be checked out at $APP_ROOT (found $REPO_ROOT)."
# Verify key application inputs exist before modifying the VM.
[[ -f "$APP_ROOT/requirements.txt" ]] || die "Root requirements.txt is missing."
[[ -f "$APP_ROOT/deployment/civo/patent-agent.env.example" ]] || die "The Civo environment template is missing."

# Protect a live deployment and prevent rerunning a completed first-time setup.
if systemctl is-active --quiet patent-agent-api || systemctl is-active --quiet patent-portal; then
    die "Patent Agent services are already running. This setup script is for a new VM and will not alter a live deployment."
fi
[[ ! -e "$SETUP_MARKER" ]] || die "Setup is already marked complete."

# Refresh Ubuntu's package index before installing required server tools.
printf 'Installing system packages...\n'
apt-get update
# Install web server, database, certificate, compiler, Python, and ACL dependencies.
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    acl build-essential ca-certificates certbot curl git libpq-dev nginx \
    openssl postgresql postgresql-contrib python3.12 python3.12-dev \
    python3.12-venv python3-pip python3-dev python3-certbot-nginx sudo

# Create the dedicated non-login system account when it does not exist yet.
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "/home/$SERVICE_USER" --create-home --shell /bin/bash "$SERVICE_USER"
fi
# Create persistent application-data directories owned by the service account.
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$APP_ROOT/data"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
    "$APP_ROOT/data/chroma_db" "$APP_ROOT/data/portal_media" "$APP_ROOT/data/reports"
# Create root-owned state storage for one-time setup markers.
install -d -o root -g root -m 0755 "$STATE_DIR"

# Install Node through nvm and produce the production React build.
printf 'Building the React frontend with Node 22...\n'
# Install nvm only when this service account does not already have it.
if [[ ! -s "/home/$SERVICE_USER/.nvm/nvm.sh" ]]; then
    sudo -u "$SERVICE_USER" -H bash -c \
        'cd /home/patent && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash'
fi
# Load nvm as the service user, install Node 22, then install and build frontend assets.
sudo -u "$SERVICE_USER" -H bash -c \
    'cd /home/patent && export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && nvm install 22 && nvm alias default 22 && cd /srv/patent_agent/web_portal/frontend && nvm use 22 && node --version && npm ci && npm run build'

# Create independent Python environments for AI services and Django portal code.
printf 'Creating Python environments and installing dependencies...\n'
# Create the AI virtual environment only if it is missing.
if [[ ! -x "$APP_ROOT/.venv-ai/bin/python" ]]; then
    sudo -u "$SERVICE_USER" -H python3.12 -m venv "$APP_ROOT/.venv-ai"
fi
# Create the portal virtual environment only if it is missing.
if [[ ! -x "$APP_ROOT/.venv-portal/bin/python" ]]; then
    sudo -u "$SERVICE_USER" -H python3.12 -m venv "$APP_ROOT/.venv-portal"
fi
# Create a temporary requirements file that can be removed on exit.
requirements_tmp="$(mktemp /tmp/patent-agent-requirements-cpu.XXXXXX)"
# Ensure the temporary requirements file is cleaned up if installation fails.
trap 'rm -f "${requirements_tmp:-}"' EXIT
# Exclude repository-pinned torch packages so the CPU-specific build can be installed explicitly.
grep -Ev '^(torch|torchaudio|torchvision)([<=>].*)?$' "$APP_ROOT/requirements.txt" > "$requirements_tmp"
# Make the filtered requirements readable by the service account's pip process.
chmod 0644 "$requirements_tmp"
# Upgrade packaging tools in the AI environment.
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-ai/bin/python" -m pip install --upgrade pip wheel
# Install CPU-only PyTorch for this CPU VM profile.
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-ai/bin/python" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
# Install the remaining root application dependencies into the AI environment.
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-ai/bin/python" -m pip install -r "$requirements_tmp"
# Upgrade packaging tools in the Django portal environment.
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-portal/bin/python" -m pip install --upgrade pip wheel
# Install Django portal dependencies from its dedicated requirements file.
sudo -u "$SERVICE_USER" -H "$APP_ROOT/.venv-portal/bin/python" -m pip install -r "$APP_ROOT/web_portal/requirements.txt"
# Remove the temporary requirements file and its cleanup trap after success.
rm -f "$requirements_tmp"
trap - EXIT

# Install Ollama if absent, apply its service override, and download the configured model.
printf 'Installing and starting Ollama...\n'
# Avoid reinstalling Ollama when the binary is already available.
if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
# Create the systemd override directory and install the repository's Ollama settings.
install -d -m 0755 /etc/systemd/system/ollama.service.d
install -o root -g root -m 0644 "$APP_ROOT/deployment/civo/ollama-service-override.conf" \
    /etc/systemd/system/ollama.service.d/override.conf
# Reload systemd configuration, start Ollama, then pull the required Mistral model.
systemctl daemon-reload
systemctl enable --now ollama
systemctl restart ollama
ollama pull mistral

# Create production credentials and settings only when no environment file exists.
if [[ ! -f "$ENV_FILE" ]]; then
    printf '\nConfigure the production environment. Values are stored in %s.\n' "$ENV_FILE"
# Collect public site, certificate, and optional OAuth settings interactively.
    read -r -p 'Public hostname (for example patentdesk.example.com): ' DOMAIN
    read -r -p 'Email for certificate expiry notices: ' CERT_EMAIL
    read -r -p 'Google OAuth client ID (leave blank to configure later): ' GOOGLE_CLIENT_ID
    read -r -s -p 'Google OAuth client secret (leave blank to configure later): ' GOOGLE_CLIENT_SECRET
    printf '\n'
# Validate values that are required to configure HTTPS and OAuth callback URLs.
    [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "Enter a valid public hostname."
    [[ "$CERT_EMAIL" == *@*.* ]] || die "Enter a valid email address for Certbot."

# Generate strong random secrets for PostgreSQL and Django.
    DB_PASSWORD="$(openssl rand -hex 24)"
    DJANGO_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"

# Create the PostgreSQL role if this database server does not already have it.
    role_exists="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'patent_portal'")"
    if [[ "$role_exists" != "1" ]]; then
        runuser -u postgres -- createuser --login patent_portal
    fi
    # Set the database role password using the generated secret.
    printf "ALTER ROLE patent_portal WITH LOGIN PASSWORD '%s';\n" "$DB_PASSWORD" \
        | runuser -u postgres -- psql -v ON_ERROR_STOP=1 >/dev/null
    # Create the application database only if it is not present already.
    db_exists="$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname = 'patent_portal'")"
    if [[ "$db_exists" != "1" ]]; then
        runuser -u postgres -- createdb --owner patent_portal patent_portal
    fi

    # Create a private temporary file for rendering the environment template.
    env_tmp="$(mktemp /tmp/patent-agent-env.XXXXXX)"
    # Pass values to the template renderer through its process environment.
    export PATENT_ENV_DOMAIN="$DOMAIN"
    export PATENT_ENV_DB_PASSWORD="$DB_PASSWORD"
    export PATENT_ENV_DJANGO_SECRET="$DJANGO_SECRET"
    export PATENT_ENV_GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID"
    export PATENT_ENV_GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET"
    # Render only known settings into the template without placing secrets in shell history.
    python3 - "$APP_ROOT/deployment/civo/patent-agent.env.example" "$env_tmp" <<'PY'
# Read environment values and template paths for safe environment-file generation.
import os
import sys
from pathlib import Path

# Load the placeholder template and the requested public hostname.
template = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
domain = os.environ["PATENT_ENV_DOMAIN"]
# Map the production settings generated or entered above to their final values.
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
# Prepare output lines and track which required settings were found in the template.
output = []
written = set()
# Replace matching non-comment template entries while preserving unrelated settings.
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
# Refuse to write an incomplete environment file if expected template keys are absent.
missing = set(values) - written
if missing:
    raise SystemExit(f"Template is missing keys: {', '.join(sorted(missing))}")
# Write the completed settings file with a final newline.
Path(sys.argv[2]).write_text("\n".join(output) + "\n", encoding="utf-8")
PY
    # Install the generated secrets file with root ownership and service-group read access.
    install -o root -g "$SERVICE_USER" -m 0640 "$env_tmp" "$ENV_FILE"
    # Remove temporary secrets and clear their exported shell variables.
    rm -f "$env_tmp"
    unset PATENT_ENV_DOMAIN PATENT_ENV_DB_PASSWORD PATENT_ENV_DJANGO_SECRET \
        PATENT_ENV_GOOGLE_CLIENT_ID PATENT_ENV_GOOGLE_CLIENT_SECRET DB_PASSWORD DJANGO_SECRET GOOGLE_CLIENT_SECRET
    printf 'Created the protected environment file.\n'
else
    # Preserve existing credentials and derive the domain from their allowed-host setting.
    printf 'Using the existing protected environment file without changing it.\n'
    # Export environment entries for any commands launched by this script.
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    # Stop automatic exporting after loading the production settings.
    set +a
    # Use the first allowed host as the site's HTTPS hostname.
    DOMAIN="${DJANGO_ALLOWED_HOSTS%%,*}"
    # Ask for the certificate contact email and validate both required values.
    read -r -p 'Email for certificate expiry notices: ' CERT_EMAIL
    [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "DJANGO_ALLOWED_HOSTS must contain a hostname."
    [[ "$CERT_EMAIL" == *@*.* ]] || die "Enter a valid email address for Certbot."
fi

# Copy transferred data into persistent locations without overwriting existing files.
printf 'Installing staged application data...\n'
# Process each persistent data directory that may have been staged from local development.
for name in chroma_db portal_media reports; do
    # Define the temporary input and persistent destination for this data type.
    source_dir="/tmp/patent-agent-data/$name"
    destination_dir="$APP_ROOT/data/$name"
    # Import only when the corresponding staging directory is present.
    if [[ -d "$source_dir" ]]; then
        cp -an "$source_dir/." "$destination_dir/"
    fi
done
# Install the optional audit database only if the staged copy exists and no destination exists.
if [[ -f /tmp/patent-agent-data/patent_agent.db && ! -e "$APP_ROOT/patent_agent.db" ]]; then
    install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0640 \
        /tmp/patent-agent-data/patent_agent.db "$APP_ROOT/patent_agent.db"
fi
# Ensure the service account owns all persistent application data.
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_ROOT/data"
# Require the expected Chroma collection before continuing to service startup.
[[ -d "$APP_ROOT/data/chroma_db/full_cpc_db" ]] || die "Chroma data is missing. Stage data/chroma_db/full_cpc_db before setup."

# Run Django management commands as the service user with production settings loaded.
run_portal_manage() {
    # Switch user, load the protected environment, and run manage.py from the Django project.
    sudo -u "$SERVICE_USER" -H bash -c '
        cd /home/patent
        set -a
        . /etc/patent-agent.env
        set +a
        cd /srv/patent_agent/web_portal
        exec /srv/patent_agent/.venv-portal/bin/python manage.py "$@"
    ' -- "$@"
}

# Apply database migrations before importing records or collecting static assets.
printf 'Applying Django migrations...\n'
run_portal_manage migrate

# Offer to import a staged local portal database fixture only once.
if [[ -f /tmp/patent-agent-data/portal-data.json && ! -e "$FIXTURE_MARKER" ]]; then
    # Copy the fixture with restrictive permissions so user records remain private.
    install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0600 \
        /tmp/patent-agent-data/portal-data.json "$APP_ROOT/portal-data.json"
    # Ask before importing local users and records into the production database.
    printf 'A portal data fixture is staged. It imports local users and records.\n'
    read -r -p 'Import this fixture into PostgreSQL now? [y/N] ' import_fixture
    # Load the fixture only after an explicit affirmative response.
    if [[ "$import_fixture" =~ ^[Yy]$ ]]; then
        run_portal_manage loaddata "$APP_ROOT/portal-data.json"
        # Mark successful import to prevent accidental repeated imports.
        touch "$FIXTURE_MARKER"
    fi
fi

# Generate Django's collected static files for Nginx to serve.
run_portal_manage collectstatic --noinput
# Create an administrator only when the operator confirms one is needed.
read -r -p 'Create an additional Django superuser? Answer yes only if the imported data has no admin account [y/N] ' create_admin
if [[ "$create_admin" =~ ^[Yy]$ ]]; then
    run_portal_manage createsuperuser
fi

# Allow Nginx to traverse parent folders and read only frontend and Django static assets.
printf 'Granting Nginx access to static files only...\n'
setfacl -m u:www-data:--x "$APP_ROOT" "$APP_ROOT/web_portal" "$APP_ROOT/web_portal/frontend"
setfacl -R -m u:www-data:rX "$APP_ROOT/web_portal/frontend/dist" "$APP_ROOT/web_portal/staticfiles"
setfacl -m d:u:www-data:rX "$APP_ROOT/web_portal/frontend/dist" "$APP_ROOT/web_portal/staticfiles"

# Install both systemd unit definitions from the repository into the system directory.
install -o root -g root -m 0644 "$APP_ROOT/deployment/civo/patent-agent-api.service" \
    /etc/systemd/system/patent-agent-api.service
install -o root -g root -m 0644 "$APP_ROOT/deployment/civo/patent-portal.service" \
    /etc/systemd/system/patent-portal.service
# Discover the VM's public IPv4 and the hostname's resolved IPv4 for a DNS consistency check.
public_ipv4="$(curl -4 -fsSL https://api.ipify.org | tr -d '\r\n')"
dns_ipv4="$(getent ahostsv4 "$DOMAIN" | awk 'NR == 1 { print $1; exit }')"
# Stop if the public hostname does not resolve directly to this VM.
[[ -n "$dns_ipv4" && "$dns_ipv4" == "$public_ipv4" ]] || \
    die "DNS for $DOMAIN must resolve to this VM's public IPv4 ($public_ipv4); found ${dns_ipv4:-no A record}."

# Prepare ACME challenge storage and standard Nginx site directories.
install -d -o www-data -g www-data -m 0755 /var/www/letsencrypt/.well-known/acme-challenge
install -d -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled
# Request a new Let's Encrypt certificate only if one is not already installed.
if [[ ! -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    # Render a temporary HTTP-only site configuration so Certbot can validate the domain.
    python3 - "$APP_ROOT/deployment/civo/nginx-bootstrap.conf" /etc/nginx/sites-available/patent-agent "$DOMAIN" <<'PY'
# Load the bootstrap template and paths supplied by the shell command.
import sys
from pathlib import Path

# Replace the example hostname and write the Nginx configuration to its target path.
source, destination, domain = sys.argv[1:]
content = Path(source).read_text(encoding="utf-8").replace("portal.example.com", domain)
Path(destination).write_text(content, encoding="utf-8")
PY
    # Enable the bootstrap site, validate its syntax, and reload Nginx before certificate issuance.
    ln -sfn /etc/nginx/sites-available/patent-agent /etc/nginx/sites-enabled/patent-agent
    nginx -t
    systemctl reload nginx
    # Obtain and install the HTTPS certificate using the HTTP webroot challenge.
    certbot certonly --non-interactive --webroot -w /var/www/letsencrypt \
        -d "$DOMAIN" -m "$CERT_EMAIL" --agree-tos --no-eff-email
fi

# Render the final HTTPS Nginx configuration with this VM's public hostname.
python3 - "$APP_ROOT/web_portal/nginx.conf.example" /etc/nginx/sites-available/patent-agent "$DOMAIN" <<'PY'
# Load Python path utilities to read and write the Nginx configuration template.
import sys
from pathlib import Path

# Replace the sample domain and save the site's final Nginx configuration.
source, destination, domain = sys.argv[1:]
content = Path(source).read_text(encoding="utf-8").replace("portal.example.com", domain)
Path(destination).write_text(content, encoding="utf-8")
PY
# Enable the final site and verify the Nginx configuration before reload.
ln -sfn /etc/nginx/sites-available/patent-agent /etc/nginx/sites-enabled/patent-agent
# Reload systemd, start and restart application services, and enable certificate renewal.
nginx -t
systemctl reload nginx
systemctl daemon-reload
systemctl enable --now patent-agent-api patent-portal
systemctl restart patent-agent-api patent-portal
systemctl enable --now certbot.timer

# Record successful first-time setup and print the site URL and operational next steps.
touch "$SETUP_MARKER"
printf '\nDeployment setup finished. Open https://%s/\n' "$DOMAIN"
if [[ -z "${GOOGLE_OAUTH_CLIENT_ID:-}" || -z "${GOOGLE_OAUTH_CLIENT_SECRET:-}" ]]; then
    printf 'Google OAuth credentials are blank; add them to %s before testing sign-in.\n' "$ENV_FILE"
fi
printf 'Check status with: systemctl status patent-agent-api patent-portal nginx --no-pager\n'
