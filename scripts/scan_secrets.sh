#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
FAIL=0

for path in app/.env secrets/google-tts.json runtime/prithi_memory/prithi_memory.db app/output/check.wav reference/private.wav; do
  if git check-ignore -q "${path}"; then
    echo "Ignored as required: ${path}"
  else
    echo "NOT IGNORED: ${path}"
    FAIL=1
  fi
done

while IFS= read -r path; do
  case "${path}" in
    app/.env|.env|secrets/*|runtime/*|*.db|*.sqlite|*.sqlite3|*.wav|*.mp3|*.m4a|*.flac)
      echo "Tracked sensitive/runtime artifact: ${path}"
      FAIL=1
      ;;
  esac
done < <(git ls-files)

while IFS= read -r path; do
  [[ "${path}" == "scripts/scan_secrets.sh" ]] && continue
  if grep -Iq . "${path}" 2>/dev/null && grep -Eq 'BEGIN [A-Z ]*PRIVATE KEY|AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z]{20,}' "${path}" 2>/dev/null; then
    echo "Potential embedded credential pattern: ${path}"
    FAIL=1
  fi
done < <(git ls-files --cached --others --exclude-standard)

if [[ "${FAIL}" -eq 0 ]]; then
  echo "Secret scan: PASS (no credential contents printed)"
else
  echo "Secret scan: FAIL"
  exit 1
fi
