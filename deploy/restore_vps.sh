#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: bash deploy/restore_vps.sh /path/to/backup.tar.gz" >&2
  exit 1
fi

ARCHIVE_PATH="$1"
APP_DIR="${APP_DIR:-/root/max_ai_agent}"

if [ ! -f "${ARCHIVE_PATH}" ]; then
  echo "Archive not found: ${ARCHIVE_PATH}" >&2
  exit 1
fi

mkdir -p "${APP_DIR}"
cd "${APP_DIR}"

mkdir -p data logs backups deploy/certbot

echo "Restoring from ${ARCHIVE_PATH} into ${APP_DIR}"
tar -xzf "${ARCHIVE_PATH}" -C "${APP_DIR}"

echo "Restore complete."
echo "Next step:"
echo "  cd ${APP_DIR} && docker compose up -d --build bot"
