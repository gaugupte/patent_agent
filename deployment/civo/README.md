# Civo deployment runbook

This runbook deploys the React portal, Django, FastAPI/LangGraph, PostgreSQL, Chroma data, and Ollama on one Ubuntu 24.04 Civo Compute VM. Run the common steps once, then choose either the CPU or GPU branch.

## 0. Choose the VM

| Profile | Civo selection | Region | GPU | Current list price, compute only |
| --- | --- | --- | --- | ---: |
| CPU-only | CPU Optimized Medium, 16 vCPU / 32 GB RAM / 80 GB NVMe | Mumbai (`MUM1`) | None; Ollama uses CPU | $0.380952/hour, about $278 per 730 hours |
| GPU | Small, 1 × NVIDIA A100 40 GB, 8 vCPU / 56 GB RAM / 200 GB NVMe | London (`LON1`) | 1 × A100 | $1.09/hour, about $796 per 730 hours |

Prices are from [Civo Compute pricing](https://www.civo.com/pricing) and can change. Civo lists GPU Compute in London and CPU Compute in Mumbai; check the region selector and account quota before creating the VM. The GPU VM stores IDFs and reports in London. Confirm that this data location is acceptable for client material.

Civo continues billing for a stopped VM at the same hourly rate. Deleting it stops VM charges, but data must first be copied to separately billed persistent storage or backups. A deleted GPU VM may take time to recreate if capacity is unavailable.

## 1. Prepare credentials and a deployable source revision

The application now reads LangSmith, OpenAlex, SerpAPI, Google OAuth, SMTP, and Django credentials from environment variables. `config/config.py` loads a local root `.env`; Django settings load the same file. Production services use `/etc/patent-agent.env`.

Credential values were present in earlier source revisions. Removing them from the current files does not remove them from Git history. Rotate the affected LangSmith, OpenAlex, SerpAPI, Hugging Face, and Google OAuth credentials in their provider consoles before deployment. If a repository containing them was public, treat the values as compromised.

1. Review `git status --short` and `git diff`; preserve the existing working-tree changes you intend to deploy.
2. Rotate exposed credentials, then remove old values from local `.env` files and provider dashboards.
3. Copy `.env.example` to `.env` for local development and fill only credentials you actively use. `.env` is ignored by Git. Confirm with:

   ```powershell
   Copy-Item .env.example .env
   git check-ignore .env
   ```

4. Commit the reviewed source to a **private** Git repository. Do not add `.env`, SQLite databases, uploaded IDFs, Chroma data, or reports.
5. In Google Cloud OAuth settings, add the production origin and callback URL: `https://YOUR_DOMAIN/` and `https://YOUR_DOMAIN/api/auth/google/callback/`.

The root requirements currently pin CUDA PyTorch packages, while `services/suspect_embedding_service.py` explicitly selects CPU. Both VM profiles can therefore install CPU PyTorch for embeddings; on the GPU profile, Ollama uses the NVIDIA GPU independently.

## 2. Create the Civo instance and firewall

In the Civo dashboard choose **Compute → Create instance**:

1. Select one of the profiles in section 0.
2. Select Ubuntu 24.04. For the GPU profile, choose the Civo CUDA image `24.04-cuda13-1` so NVIDIA drivers, the container toolkit, and CUDA are installed.
3. Add an SSH public key and assign a public IP.
4. Add an inbound Civo firewall allowing TCP 22 only from your current public IP, plus TCP 80 and 443 from the internet. Do not allow inbound TCP 8000, 8001, 5432, or 11434.

Connect from Windows PowerShell using the image's initial username:

```powershell
ssh <initial-linux-user>@<VM_PUBLIC_IP>
```

## 3. Base Ubuntu setup

Run these commands over SSH:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y ca-certificates curl git nginx postgresql postgresql-contrib \
  python3.12 python3.12-venv python3-pip python3-dev build-essential libpq-dev \
  ufw certbot python3-certbot-nginx
```

Create the non-root service/deploy account and source directory:

```bash
sudo useradd --system --home-dir /home/patent --create-home --shell /bin/bash patent
sudo install -d -o patent -g patent -m 0750 /srv/patent_agent
```

The dashboard firewall is the first SSH restriction. Set the VM firewall too, replacing the example address with your public IP:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from YOUR_PUBLIC_IP/32 to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## 4. Check out the private repository

Create a read-only Git deploy key for the `patent` account:

```bash
sudo install -d -o patent -g patent -m 0700 /home/patent/.ssh
sudo -u patent ssh-keygen -t ed25519 -N '' -f /home/patent/.ssh/id_ed25519 -C civo-patent-agent
sudo cat /home/patent/.ssh/id_ed25519.pub
```

Add the displayed **public** key as a read-only deploy key to your private Git repository. Keep the private key on the VM. Then clone the repository:

```bash
sudo -u patent git clone git@github.com:YOUR_ORG/YOUR_PRIVATE_REPO.git /srv/patent_agent
```

If using a Git host other than GitHub, replace the clone URL. The repository's `deployment/civo` files are used below.

## 5. Install Node with NVM and build React

The frontend's Vite packages require Node `^20.19.0 || >=22.12.0`. Install Node 22 with NVM for the `patent` account (NVM is per-user and is used only for building):

```bash
sudo -u patent -H bash -lc 'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash'
sudo -u patent -H bash -lc 'source ~/.bashrc && nvm install 22 && nvm alias default 22'
sudo -u patent -H bash -lc 'cd /srv/patent_agent/web_portal/frontend && nvm use 22 && node --version && npm ci && npm run build'
```

The build output is `/srv/patent_agent/web_portal/frontend/dist`; Nginx serves it directly.

## 6. Install Python environments and dependencies

Create separate environments for the AI service and Django portal:

```bash
sudo -u patent python3.12 -m venv /srv/patent_agent/.venv-ai
sudo -u patent python3.12 -m venv /srv/patent_agent/.venv-portal
sudo install -d -o patent -g patent -m 0750 /srv/patent_agent/data
```

Install CPU PyTorch for the current CPU embedding implementation, then install the rest of the root requirements while omitting the three CUDA-specific pins:

```bash
grep -Ev '^(torch|torchaudio|torchvision)([<=>].*)?$' /srv/patent_agent/requirements.txt > /tmp/patent-agent-requirements-cpu.txt
sudo -u patent /srv/patent_agent/.venv-ai/bin/python -m pip install --upgrade pip wheel
sudo -u patent /srv/patent_agent/.venv-ai/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
sudo -u patent /srv/patent_agent/.venv-ai/bin/python -m pip install -r /tmp/patent-agent-requirements-cpu.txt
sudo -u patent /srv/patent_agent/.venv-portal/bin/python -m pip install --upgrade pip wheel
sudo -u patent /srv/patent_agent/.venv-portal/bin/python -m pip install -r /srv/patent_agent/web_portal/requirements.txt
```

This is the same Python dependency setup on both VM profiles. The GPU profile's CUDA image accelerates Ollama; the current embedding code stays on CPU. If embeddings are later moved to CUDA, change the embedding device and install a matching PyTorch CUDA build as a separate change.

## 7. Install Ollama and verify hardware

For both profiles, install the Linux Ollama service and fetch the configured model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull mistral
```

Force the Ollama API to listen on loopback so only local services can call it:

```bash
sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
sudo install -o root -g root -m 0644 /srv/patent_agent/deployment/civo/ollama-service-override.conf /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

On the CPU profile, Ollama will report CPU inference. On the GPU profile, first confirm the NVIDIA device:

```bash
nvidia-smi
```

Then generate one response and inspect placement:

```bash
ollama run mistral "Reply with the word ready."
ollama ps
```

The `PROCESSOR` column should report GPU use on the A100 VM. Ollama should remain local; the firewall must keep port 11434 closed.

## 8. Create PostgreSQL and the protected environment file

Create a strong hex database password, then create the portal role and database:

```bash
openssl rand -hex 24
sudo -u postgres psql
```

At the PostgreSQL prompt, use the generated value when `\password` prompts:

```sql
CREATE ROLE patent_portal LOGIN;
\password patent_portal
CREATE DATABASE patent_portal OWNER patent_portal;
\q
```

Generate the Django secret before editing the environment file so it is ready to paste:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
openssl rand -hex 24
```

Install the tracked, placeholder-only template as a root-owned environment file, then edit it:

```bash
sudo install -o root -g patent -m 0640 /srv/patent_agent/deployment/civo/patent-agent.env.example /etc/patent-agent.env
sudoedit /etc/patent-agent.env
```

Set the domain, generated Django secret, PostgreSQL password, OAuth values, and SMTP values. Keep `LANGCHAIN_TRACING_V2=false` and `LANGSMITH_TRACING=false` unless external tracing is intentionally enabled. The template sets Chroma, reports, and uploads to persistent paths under `/srv/patent_agent/data`. Do not put shell commands, `export`, or real credentials in the repository template.

Paste the generated secret into `DJANGO_SECRET_KEY` and the database password into `DATABASE_URL`. Hexadecimal avoids URL-escaping problems in the database URL.

Check owner and mode:

```bash
sudo chown root:patent /etc/patent-agent.env
sudo chmod 0640 /etc/patent-agent.env
sudo stat -c '%U %G %a %n' /etc/patent-agent.env
```

The Google OAuth secret and other API keys belong only in this file (or a secrets manager), never in `.py`, `.md`, Git, or a frontend build.

## 9. Transfer persistent data from Windows

From PowerShell in the local project root, first create a staging directory on the VM, then copy the ignored data separately. Replace `<initial-linux-user>` and `<VM_PUBLIC_IP>`:

```powershell
ssh <initial-linux-user>@<VM_PUBLIC_IP> "mkdir -p /tmp/patent-agent-data"
```

```powershell
scp -r .\data\chroma_db <initial-linux-user>@<VM_PUBLIC_IP>:/tmp/patent-agent-data/
scp -r .\data\portal_media <initial-linux-user>@<VM_PUBLIC_IP>:/tmp/patent-agent-data/
scp -r .\data\reports <initial-linux-user>@<VM_PUBLIC_IP>:/tmp/patent-agent-data/
```

On the VM, install the directories with the service account as owner:

```bash
sudo install -d -o patent -g patent /srv/patent_agent/data/chroma_db
sudo install -d -o patent -g patent /srv/patent_agent/data/portal_media
sudo install -d -o patent -g patent /srv/patent_agent/data/reports
sudo cp -a /tmp/patent-agent-data/chroma_db/. /srv/patent_agent/data/chroma_db/
sudo cp -a /tmp/patent-agent-data/portal_media/. /srv/patent_agent/data/portal_media/
sudo cp -a /tmp/patent-agent-data/reports/. /srv/patent_agent/data/reports/
sudo chown -R patent:patent /srv/patent_agent/data
```

The Chroma directory is ignored by Git and was about 0.43 GB locally; the FastAPI service needs the existing `full_cpc_db` collection. Copy `web_portal/portal.sqlite3` data through Django fixtures if existing portal users and records must be retained. Run locally:

```powershell
python web_portal/manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude sessions -o portal-data.json
scp .\portal-data.json <initial-linux-user>@<VM_PUBLIC_IP>:/tmp/portal-data.json
```

The audit SQLite database `patent_agent.db` is also ignored by Git; copy it separately if its audit history should be preserved. From PowerShell, if the file exists:

```powershell
scp .\patent_agent.db <initial-linux-user>@<VM_PUBLIC_IP>:/tmp/patent_agent.db
```

On the VM, place it where the audit service expects it and set ownership:

```bash
sudo install -o patent -g patent -m 0640 /tmp/patent_agent.db /srv/patent_agent/patent_agent.db
```

The file uploads and reports still need the separate directory copies above.

## 10. Migrate Django and start services

On the VM:

```bash
sudo -u patent /srv/patent_agent/.venv-portal/bin/python /srv/patent_agent/web_portal/manage.py migrate
```

If you exported portal records, load them after migrations:

```bash
sudo cp /tmp/portal-data.json /srv/patent_agent/portal-data.json
sudo chown patent:patent /srv/patent_agent/portal-data.json
sudo -u patent /srv/patent_agent/.venv-portal/bin/python /srv/patent_agent/web_portal/manage.py loaddata /srv/patent_agent/portal-data.json
```

Collect Django admin assets and create a superuser only when the database is new:

```bash
sudo -u patent /srv/patent_agent/.venv-portal/bin/python /srv/patent_agent/web_portal/manage.py collectstatic --noinput
sudo -u patent /srv/patent_agent/.venv-portal/bin/python /srv/patent_agent/web_portal/manage.py createsuperuser
```

Install the checked-in systemd services:

```bash
sudo install -o root -g root -m 0644 /srv/patent_agent/deployment/civo/patent-agent-api.service /etc/systemd/system/patent-agent-api.service
sudo install -o root -g root -m 0644 /srv/patent_agent/deployment/civo/patent-portal.service /etc/systemd/system/patent-portal.service
sudo systemctl daemon-reload
sudo systemctl enable --now patent-agent-api patent-portal
sudo systemctl status ollama patent-agent-api patent-portal --no-pager
```

The API and portal bind only to localhost. The AI service uses one Uvicorn worker so startup does not load a separate Chroma/embedding context into every worker. Its report directory and Django's report root point to the same persistent path.

## 11. Configure DNS, Nginx, and HTTPS

1. Create an A record for `YOUR_DOMAIN` pointing to the VM public IP. Create the ACME challenge directory:

   ```bash
   sudo install -d -o www-data -g www-data -m 0755 /var/www/letsencrypt/.well-known/acme-challenge
   ```

2. Install the HTTP bootstrap site, replace `portal.example.com` with the real domain, enable it, and reload Nginx:

   ```bash
   sudo cp /srv/patent_agent/deployment/civo/nginx-bootstrap.conf /etc/nginx/sites-available/patent-agent
   sudoedit /etc/nginx/sites-available/patent-agent
   sudo ln -s /etc/nginx/sites-available/patent-agent /etc/nginx/sites-enabled/patent-agent
   sudo nginx -t
   sudo systemctl reload nginx
   ```

3. Request the certificate using the webroot challenge:

   ```bash
   sudo certbot certonly --webroot -w /var/www/letsencrypt -d YOUR_DOMAIN -m YOUR_EMAIL --agree-tos --no-eff-email
   ```

4. Update `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `GOOGLE_OAUTH_REDIRECT_URI`, and `PORTAL_FRONTEND_URL` in `/etc/patent-agent.env` to the real HTTPS domain. Install the final Nginx configuration and replace its sample hostname:

   ```bash
   sudo cp /srv/patent_agent/web_portal/nginx.conf.example /etc/nginx/sites-available/patent-agent
   sudoedit /etc/nginx/sites-available/patent-agent
   sudo nginx -t
   sudo systemctl reload nginx
   sudo systemctl restart patent-agent-api patent-portal
   ```

## 12. Verify and back up

Check local service health from the VM:

```bash
curl http://127.0.0.1:8000/health
curl -H 'Host: YOUR_DOMAIN' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8001/api/health/
curl -I https://YOUR_DOMAIN/
```

Then sign in through the portal, upload a small UTF-8 `.txt` IDF, wait for analysis, and download the generated report. Watch logs with `journalctl -u patent-agent-api -f` and `journalctl -u patent-portal -f`.

Set up recurring PostgreSQL dumps and copies of `/srv/patent_agent/data` to storage outside the VM. Configure a Civo billing alert. A stopped instance remains billable; deleting it requires restoring from backups or persistent storage when recreating the service.
