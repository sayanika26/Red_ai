#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PRITHI_VENV_DIR:-${HOME}/.virtualenvs/prithi-voice}"
PYTHON="${VENV_DIR}/bin/python"
SOURCE_DB="${PRITHI_MEMORY_DB:-${PROJECT_ROOT}/runtime/prithi_memory/prithi_memory.db}"
BACKUP_ROOT="${PRITHI_BACKUP_DIR:-${HOME}/prithi-backups}"
DESTINATION="${1:-${BACKUP_ROOT}/prithi-v1-$(date -u +%Y%m%dT%H%M%SZ)}"

[[ -x "${PYTHON}" ]] || { echo "Prithi Python environment is missing." >&2; exit 1; }
mkdir -p "${DESTINATION}/memory" "${DESTINATION}/templates"
chmod 700 "${DESTINATION}" "${DESTINATION}/memory" "${DESTINATION}/templates"

if [[ -f "${SOURCE_DB}" ]]; then
  "${PYTHON}" - "${SOURCE_DB}" "${DESTINATION}/memory/prithi_memory.db" <<'PY'
import sqlite3
import sys
source, destination = sys.argv[1:]
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as incoming:
    with sqlite3.connect(destination) as outgoing:
        incoming.backup(outgoing)
        if outgoing.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup database integrity check failed")
PY
  chmod 600 "${DESTINATION}/memory/prithi_memory.db"
  echo "SQLite memory backed up: yes"
else
  echo "SQLite memory backed up: no database present"
fi

for file in VERSION app/.env.example app/model_profiles.json; do
  [[ -f "${PROJECT_ROOT}/${file}" ]] && cp -p "${PROJECT_ROOT}/${file}" "${DESTINATION}/templates/$(basename "${file}")"
done
if [[ -f "${PROJECT_ROOT}/runtime/custom_models/manifest.json" ]]; then
  mkdir -p "${DESTINATION}/custom_models"
  cp -p "${PROJECT_ROOT}/runtime/custom_models/manifest.json" "${DESTINATION}/custom_models/manifest.json"
fi
cat >"${DESTINATION}/BACKUP_CONTENTS.txt" <<'EOF'
Prithi private persistent-data backup.
Contains SQLite memory plus safe templates/model references when present.
Does not contain app/.env, credentials, service-account JSON, audio, or model weights.
EOF
chmod 600 "${DESTINATION}/BACKUP_CONTENTS.txt"
echo "Backup complete: ${DESTINATION}"
