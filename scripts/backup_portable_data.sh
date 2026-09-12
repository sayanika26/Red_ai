#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST="${1:-}"
[[ -n "${DEST}" ]] || { echo "Usage: ./scripts/backup_portable_data.sh /path/to/backup" >&2; exit 2; }
DEST="$(mkdir -p "${DEST}" && cd "${DEST}" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${DEST}/prithi-portable-data-${STAMP}.tar.gz"
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
mkdir -p "${TMP}/runtime/prithi_memory"
if [[ -f "${PROJECT_ROOT}/runtime/prithi_memory/prithi_memory.db" ]]; then
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${PROJECT_ROOT}/runtime/prithi_memory/prithi_memory.db" ".backup '${TMP}/runtime/prithi_memory/prithi_memory.db'"
  else
    cp "${PROJECT_ROOT}/runtime/prithi_memory/prithi_memory.db" "${TMP}/runtime/prithi_memory/"
  fi
fi
[[ -f "${PROJECT_ROOT}/app/.env" ]] && { mkdir -p "${TMP}/app"; cp "${PROJECT_ROOT}/app/.env" "${TMP}/app/.env"; chmod 600 "${TMP}/app/.env"; }
printf '%s\n' "Prithi portable private data backup ${STAMP}" >"${TMP}/BACKUP_INFO.txt"
tar -C "${TMP}" -czf "${ARCHIVE}" .
chmod 600 "${ARCHIVE}"
echo "Created private backup: ${ARCHIVE}"
echo "Excluded Google credentials, microphone recordings, temporary files, model caches, and checkpoints."
