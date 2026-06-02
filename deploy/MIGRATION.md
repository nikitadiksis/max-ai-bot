# VPS Migration Checklist

This project can be moved to another VPS without losing users, plans, payments,
or referral data as long as these server-only assets are preserved:

- `.env`
- `data/`
- `logs/` (optional, but useful)
- TLS certs from `deploy/certbot/` if you want to keep the current HTTPS setup

## What must be prepared in advance

1. Lower DNS TTL for the main domain a day before migration if possible.
2. Make a fresh backup archive from the old server.
3. Prepare the new VPS with Docker and Docker Compose plugin.
4. Restore `.env`, `data/`, and optional folders on the new VPS.
5. Start the bot on the new VPS.
6. Verify `/health`, `/status`, `/analytics`, and payment/webhook endpoints.
7. Switch the domain A record to the new VPS IP.
8. Keep the old VPS alive for a short overlap window until traffic is stable.

## Old server: create backup

On the old server:

```bash
cd /root/max_ai_agent
bash deploy/backup_vps.sh
```

The script creates an archive in:

```bash
/root/max_ai_agent/backups/
```

## New server: first-time setup

Example for Ubuntu:

```bash
apt update
apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sh
mkdir -p /root/max_ai_agent
cd /root/max_ai_agent
git clone https://github.com/nikitadiksis/max-ai-bot.git .
mkdir -p data logs backups
```

## New server: restore backup

Upload the backup archive to the new VPS, then run:

```bash
cd /root/max_ai_agent
bash deploy/restore_vps.sh /root/max_ai_agent/backups/max_ai_agent_backup_YYYYmmdd_HHMMSS.tar.gz
```

## Start services

```bash
cd /root/max_ai_agent
docker compose up -d --build bot
```

If this VPS will also terminate HTTPS directly with nginx from this repo:

```bash
docker compose up -d --build
```

If system nginx is used instead, keep only the bot container and restore the
server nginx config separately.

## Validate before DNS switch

Run these checks on the new VPS:

```bash
docker compose ps
curl -sS http://127.0.0.1:8000/health
```

If nginx is already wired to the domain on the new VPS:

```bash
curl -I https://aimaxbots.ru/health
```

Functional checks:

- bot answers in MAX
- `/health` returns `status=ok`
- `/status` opens
- `/analytics` login works
- current user plans are intact
- payment status pages open
- image generation works

## Minimal downtime switch

Recommended flow:

1. Keep old VPS online.
2. Restore and verify new VPS.
3. Change DNS A record to the new IP.
4. Wait for traffic to stabilize.
5. Only then stop the old VPS.

## What the user still must do manually

- buy or create the new VPS
- point the domain to the new IP
- if needed, re-issue or restore HTTPS certificates

Everything else in this repo is already prepared for container-based migration.
