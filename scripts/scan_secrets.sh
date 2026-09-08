#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
FOUND=0
while IFS= read -r path; do
  case "${path}" in
    ./app/.env|./.env) echo "${path#./} | environment configuration"; FOUND=1 ;;
    ./secrets/*) echo "${path#./} | secrets directory file"; FOUND=1 ;;
    *.pem|*.key|*.p12) echo "${path#./} | private key/certificate material"; FOUND=1 ;;
    *credentials*.json|*service-account*.json|*google-tts.json) echo "${path#./} | credential JSON"; FOUND=1 ;;
  esac
done < <(find . -path './.git' -prune -o -path './runtime' -prune -o -type f -print)
while IFS= read -r path; do echo "${path#./} | potential embedded private key/token"; FOUND=1; done < <(grep -IlER --exclude-dir=.git --exclude-dir=runtime --exclude-dir=secrets --exclude='.env' --exclude='*.wav' --exclude='*.pyc' 'BEGIN [A-Z ]*PRIVATE KEY|AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z]{20,}' . 2>/dev/null || true)
[[ "${FOUND}" -eq 0 ]] && echo "No potential secrets found."
exit 0
