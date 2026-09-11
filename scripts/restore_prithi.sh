#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PRITHI_VENV_DIR:-${HOME}/.virtualenvs/prithi-voice}"
PYTHON="${VENV_DIR}/bin/python"
SOURCE="${1:-}"
DESTINATION_DB="${PRITHI_MEMORY_DB:-${PROJECT_ROOT}/runtime/prithi_memory/prithi_memory.db}"

[[ -n "${SOURCE}" ]] || { echo "Usage: ./scripts/restore_prithi.sh BACKUP_DIRECTORY" >&2; exit 2; }
SOURCE_DB="$(cd "${SOURCE}" 2>/dev/null && pwd)/memory/prithi_memory.db" || { echo "Backup directory does not exist." >&2; exit 1; }
[[ -f "${SOURCE_DB}" ]] || { echo "Backup does not contain memory/prithi_memory.db." >&2; exit 1; }
[[ -x "${PYTHON}" ]] || { echo "Prithi Python environment is missing." >&2; exit 1; }
mkdir -p "$(dirname "${DESTINATION_DB}")"
chmod 700 "$(dirname "${DESTINATION_DB}")"
TEMP_DB="${DESTINATION_DB}.restore.$$"
trap 'rm -f "${TEMP_DB}"' EXIT

"${PYTHON}" - "${SOURCE_DB}" "${TEMP_DB}" <<'PY'
import sqlite3
import sys
source, destination = sys.argv[1:]
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as incoming:
    if incoming.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Source database integrity check failed")
    with sqlite3.connect(destination) as outgoing:
        incoming.backup(outgoing)
        if outgoing.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Restored database integrity check failed")
PY

if [[ -f "${DESTINATION_DB}" ]]; then
  cp -p "${DESTINATION_DB}" "${DESTINATION_DB}.pre-restore"
  chmod 600 "${DESTINATION_DB}.pre-restore"
fi
mv -f "${TEMP_DB}" "${DESTINATION_DB}"
chmod 600 "${DESTINATION_DB}"
trap - EXIT

if [[ -f "${SOURCE}/custom_models/manifest.json" ]]; then
  mkdir -p "${PROJECT_ROOT}/runtime/custom_models"
  cp -p "${SOURCE}/custom_models/manifest.json" "${PROJECT_ROOT}/runtime/custom_models/manifest.json"
fi
echo "Restore complete: SQLite memory restored safely."
echo "Restart the Prithi web process to load restored relationship state."
