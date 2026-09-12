#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
FAIL=0

report_local() {
  local path="$1" type="$2"
  if [[ -e "${path}" ]]; then
    echo "LOCAL_IGNORED: ${path} | ${type}"
    git check-ignore -q "${path}" || { echo "ERROR: local sensitive path is not ignored: ${path}"; FAIL=1; }
    if git ls-files --error-unmatch "${path}" >/dev/null 2>&1; then echo "ERROR: sensitive path is tracked: ${path}"; FAIL=1; fi
  fi
}
report_local "app/.env" "environment configuration"
report_local "secrets/google-tts.json" "Google service-account credential"
report_local "runtime/prithi_memory/prithi_memory.db" "SQLite user memory"

while IFS= read -r path; do
  case "${path}" in
    .env|app/.env|secrets/*|runtime/*|app/output/*|voice_auditions/*|training/checkpoints/*|*.db|*.sqlite|*.sqlite3)
      echo "ERROR: tracked sensitive/runtime artifact: ${path}"; FAIL=1 ;;
  esac
done < <(git ls-files)

while IFS= read -r path; do
  [[ -f "${path}" ]] || continue
  case "${path}" in
    scripts/scan_secrets.sh|docs/SECRETS_RESTORE.md|app/.env.example|app/app.env.example) continue ;;
  esac
  grep -Iq . "${path}" 2>/dev/null || continue
  if grep -Eq 'BEGIN ([A-Z ]+ )?PRIVATE KEY' "${path}"; then echo "POTENTIAL: ${path} | private key"; FAIL=1; fi
  if grep -Eq 'AIza[0-9A-Za-z_-]{20,}' "${path}"; then echo "POTENTIAL: ${path} | Google API key"; FAIL=1; fi
  if grep -Eq '(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}' "${path}"; then echo "POTENTIAL: ${path} | API key"; FAIL=1; fi
  if grep -Eq '"private_key"[[:space:]]*:[[:space:]]*"-----BEGIN' "${path}"; then echo "POTENTIAL: ${path} | service-account private key"; FAIL=1; fi
done < <(git ls-files --cached --others --exclude-standard)

if [[ "${FAIL}" -eq 0 ]]; then echo "Secret scan: PASS (paths/types only; values not printed)"; else echo "Secret scan: FAIL"; exit 1; fi
