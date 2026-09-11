#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/app/.env"
WEB_PID_FILE="${PROJECT_ROOT}/runtime/web/prithi_web.pid"
WEB_LOG="${PROJECT_ROOT}/runtime/web/web.log"

[[ -f "${ENV_FILE}" ]] || { echo "Missing app/.env; run ./setup.sh and configure it." >&2; exit 1; }
set -a; source "${ENV_FILE}"; set +a
PORT="${PRITHI_WEB_PORT:-8000}"
[[ -n "${PRITHI_WEB_ACCESS_TOKEN:-}" ]] || { echo "PRITHI_WEB_ACCESS_TOKEN is not configured." >&2; exit 1; }

"${SCRIPT_DIR}/start_prithi_runtime.sh"
mkdir -p "${PROJECT_ROOT}/runtime/web"

if curl -fsS --max-time 3 -H "Authorization: Bearer ${PRITHI_WEB_ACCESS_TOKEN}" "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
  echo "Prithi web already healthy; no duplicate process started."
else
  if [[ -f "${WEB_PID_FILE}" ]] && kill -0 "$(<"${WEB_PID_FILE}")" 2>/dev/null; then
    echo "A recorded Prithi web process exists but is not healthy; inspect ${WEB_LOG}." >&2
    exit 1
  fi
  rm -f "${WEB_PID_FILE}"
  nohup "${SCRIPT_DIR}/start_prithi_web.sh" >>"${WEB_LOG}" 2>&1 &
  echo $! >"${WEB_PID_FILE}"
  for _ in $(seq 1 120); do
    curl -fsS --max-time 3 -H "Authorization: Bearer ${PRITHI_WEB_ACCESS_TOKEN}" "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
fi

curl -fsS --max-time 3 -H "Authorization: Bearer ${PRITHI_WEB_ACCESS_TOKEN}" "http://127.0.0.1:${PORT}/api/health" >/dev/null
echo "Prithi version: $(tr -d '[:space:]' <"${PROJECT_ROOT}/VERSION")"
echo "Web port: ${PORT}"
echo "Health: ok"
