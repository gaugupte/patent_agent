#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP_ROOT="/srv/patent_agent"
SERVICE_USER="patent"
ENV_FILE="/etc/patent-agent.env"
BACKUP_ROOT="/var/backups/patent-agent"
TARGET_SHA="${1:-}"
BACKUP_DIR=""
PREVIOUS_SHA=""
SERVICES_STOPPED=0
UPDATE_STARTED=0

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run this script with sudo."
[[ "$TARGET_SHA" =~ ^[a-f0-9]{40,64}$ ]] || die "Pass the full 40-character commit SHA to deploy."
[[ -d "$APP_ROOT/.git" ]] || die "No Git checkout found at $APP_ROOT."
[[ -r "$ENV_FILE" ]] || die "Production environment file $ENV_FILE is missing."

service_git() {
    runuser -u "$SERVICE_USER" -- git -C "$APP_ROOT" "$@"
}

run_portal_manage() {
    runuser -u "$SERVICE_USER" -- bash -c '
        set -a
        . /etc/patent-agent.env
        set +a
        cd /srv/patent_agent/web_portal
        exec /srv/patent_agent/.venv-portal/bin/python manage.py "$@"
    ' -- "$@"
}

install_dependencies() {
    local requirements_tmp
    requirements_tmp="$(mktemp /tmp/patent-agent-requirements-cpu.XXXXXX)"
    grep -Ev '^(torch|torchaudio|torchvision)([<=>].*)?$' \
        "$APP_ROOT/requirements.txt" > "$requirements_tmp"
    chmod 0644 "$requirements_tmp"

    runuser -u "$SERVICE_USER" -- "$APP_ROOT/.venv-ai/bin/python" -m pip install \
        -r "$requirements_tmp"
    runuser -u "$SERVICE_USER" -- "$APP_ROOT/.venv-portal/bin/python" -m pip install \
        -r "$APP_ROOT/web_portal/requirements.txt"
    rm -f "$requirements_tmp"
}

build_frontend() {
    runuser -u "$SERVICE_USER" -- bash -c '
        export NVM_DIR="$HOME/.nvm"
        . "$NVM_DIR/nvm.sh"
        cd /srv/patent_agent/web_portal/frontend
        nvm use 22
        npm ci
        npm run build
    '
}

check_site() {
    local domain="$1"
    local attempt

    for attempt in $(seq 1 24); do
        if curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null \
            && curl --fail --silent --show-error --resolve "$domain:443:127.0.0.1" \
                "https://$domain/api/health/" >/dev/null \
            && curl --fail --silent --show-error --resolve "$domain:443:127.0.0.1" \
                "https://$domain/" >/dev/null; then
            return 0
        fi
        sleep 5
    done
    return 1
}

rollback() {
    local original_status="$1"
    local rollback_failed=0

    set +e
    printf '\nDeployment failed; rolling back to %s.\n' "${PREVIOUS_SHA:-unknown}" >&2

    if [[ "$UPDATE_STARTED" -eq 1 && -n "$PREVIOUS_SHA" ]]; then
        service_git reset --hard "$PREVIOUS_SHA" || rollback_failed=1
        if [[ -s "$BACKUP_DIR/postgres.dump" ]]; then
            runuser -u postgres -- dropdb --if-exists patent_portal || rollback_failed=1
            runuser -u postgres -- createdb --owner patent_portal patent_portal || rollback_failed=1
            runuser -u postgres -- pg_restore --no-owner --no-privileges --role=patent_portal \
                --dbname=patent_portal "$BACKUP_DIR/postgres.dump" || rollback_failed=1
        else
            printf 'Database backup is missing; database was not restored.\n' >&2
            rollback_failed=1
        fi
        install_dependencies || rollback_failed=1
        build_frontend || rollback_failed=1
        run_portal_manage collectstatic --noinput || rollback_failed=1
    fi

    systemctl start patent-agent-api patent-portal || rollback_failed=1
    if [[ -n "${DJANGO_ALLOWED_HOSTS:-}" ]]; then
        domain="${DJANGO_ALLOWED_HOSTS%%,*}"
        check_site "$domain" || rollback_failed=1
    fi

    if [[ "$rollback_failed" -eq 0 ]]; then
        printf 'Rollback completed; the previous application version is serving again.\n' >&2
    else
        printf 'Rollback did not fully complete. Inspect services and restore backup at %s.\n' \
            "${BACKUP_DIR:-not created}" >&2
    fi
    exit "$original_status"
}

handle_error() {
    local status="$?"
    trap - ERR
    if [[ "$SERVICES_STOPPED" -eq 1 ]]; then
        rollback "$status"
    fi
    exit "$status"
}

trap handle_error ERR

printf 'Checking the current checkout and requested commit...\n'
[[ "$(service_git rev-parse --is-inside-work-tree)" == "true" ]] || die "Invalid application checkout."
[[ -z "$(service_git status --porcelain --untracked-files=no)" ]] || \
    die "Tracked application files have local changes. Refusing to overwrite them."
PREVIOUS_SHA="$(service_git rev-parse HEAD)"
service_git fetch --prune origin main
service_git cat-file -e "$TARGET_SHA^{commit}"
service_git merge-base --is-ancestor "$TARGET_SHA" FETCH_HEAD || \
    die "The requested commit is not on origin/main."

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
DOMAIN="${DJANGO_ALLOWED_HOSTS%%,*}"
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "Invalid DJANGO_ALLOWED_HOSTS in $ENV_FILE."

install -d -o root -g postgres -m 0750 "$BACKUP_ROOT"
BACKUP_DIR="$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-${PREVIOUS_SHA:0:8}"
install -d -o root -g postgres -m 0750 "$BACKUP_DIR"
printf '%s\n' "$PREVIOUS_SHA" > "$BACKUP_DIR/previous-commit.txt"
chown root:postgres "$BACKUP_DIR/previous-commit.txt"
chmod 0640 "$BACKUP_DIR/previous-commit.txt"

printf 'Stopping application services and backing up PostgreSQL...\n'
systemctl stop patent-portal patent-agent-api
SERVICES_STOPPED=1
runuser -u postgres -- pg_dump --format=custom --no-owner --no-acl patent_portal \
    > "$BACKUP_DIR/postgres.dump"
chown root:postgres "$BACKUP_DIR/postgres.dump"
chmod 0640 "$BACKUP_DIR/postgres.dump"

printf 'Checking out %s and updating dependencies...\n' "$TARGET_SHA"
UPDATE_STARTED=1
service_git reset --hard "$TARGET_SHA"
install_dependencies
build_frontend

printf 'Applying database migrations and collecting static files...\n'
run_portal_manage migrate --noinput
run_portal_manage collectstatic --noinput

printf 'Starting services and checking the application...\n'
systemctl start patent-agent-api patent-portal
check_site "$DOMAIN"
systemctl is-active --quiet patent-agent-api
systemctl is-active --quiet patent-portal

trap - ERR
printf '\nDeployment succeeded: %s\n' "$TARGET_SHA"
printf 'Pre-deployment PostgreSQL backup: %s/postgres.dump\n' "$BACKUP_DIR"
