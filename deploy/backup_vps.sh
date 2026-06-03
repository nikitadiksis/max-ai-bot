#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/max_ai_agent}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${APP_DIR}/backups"
ARCHIVE_PATH="${BACKUP_DIR}/max_ai_agent_backup_${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

cd "${APP_DIR}"

if [ ! -f ".env" ]; then
  echo "Missing ${APP_DIR}/.env" >&2
  exit 1
fi

if [ ! -d "data" ]; then
  echo "Missing ${APP_DIR}/data" >&2
  exit 1
fi

echo "Creating backup: ${ARCHIVE_PATH}"

items=(
  ".env"
  "data"
)

optional_items=(
  "logs"
  "deploy/certbot"
  "docker-compose.yml"
  "deploy/nginx.conf"
)

for item in "${optional_items[@]}"; do
  if [ -e "${item}" ]; then
    items+=("${item}")
  fi
done

tar -czf "${ARCHIVE_PATH}" "${items[@]}"

echo "Done: ${ARCHIVE_PATH}"
