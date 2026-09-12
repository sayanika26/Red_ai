#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${1:-}"
[[ -n "${SOURCE}" ]] || { echo "Usage: ./scripts/restore_portable_data.sh /path/to/backup-or-archive" >&2; exit 2; }
if [[ -d "${SOURCE}" ]]; then
  ARCHIVE="$(find "${SOURCE}" -maxdepth 1 -type f -name 'prithi-portable-data-*.tar.gz' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
else ARCHIVE="${SOURCE}"; fi
[[ -f "${ARCHIVE}" ]] || { echo "No portable backup archive found." >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
python3 - "${ARCHIVE}" <<'PY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1], "r:gz") as archive:
    for member in archive.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit(f"Unsafe archive member: {member.name}")
PY
tar -xzf "${ARCHIVE}" -C "${TMP}"
mkdir -p "${PROJECT_ROOT}/runtime/prithi_memory"
if [[ -f "${TMP}/runtime/prithi_memory/prithi_memory.db" ]]; then
  python3 - "${TMP}/runtime/prithi_memory/prithi_memory.db" <<'PY'
import sqlite3, sys
db=sqlite3.connect(sys.argv[1]); result=db.execute('PRAGMA integrity_check').fetchone()[0]; db.close()
raise SystemExit(0 if result == 'ok' else 1)
PY
  TARGET="${PROJECT_ROOT}/runtime/prithi_memory/prithi_memory.db"
  [[ ! -f "${TARGET}" ]] || cp -p "${TARGET}" "${TARGET}.pre-restore"
  install -m 600 "${TMP}/runtime/prithi_memory/prithi_memory.db" "${TARGET}"
fi
if [[ -f "${TMP}/app/.env" ]]; then
  mkdir -p "${PROJECT_ROOT}/app"
  [[ ! -f "${PROJECT_ROOT}/app/.env" ]] || cp -p "${PROJECT_ROOT}/app/.env" "${PROJECT_ROOT}/app/.env.pre-restore"
  install -m 600 "${TMP}/app/.env" "${PROJECT_ROOT}/app/.env"
fi
echo "Portable private data restored. Restart Prithi to load restored state."
