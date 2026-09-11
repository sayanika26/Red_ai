#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WEB_PID_FILE="${PROJECT_ROOT}/runtime/web/prithi_web.pid"

if [[ -f "${WEB_PID_FILE}" ]]; then
  PID="$(<"${WEB_PID_FILE}")"
  if kill -0 "${PID}" 2>/dev/null; then
    COMMAND="$(tr '\0' ' ' <"/proc/${PID}/cmdline")"
    if [[ "${COMMAND}" == *"start_prithi_web.sh"* || "${COMMAND}" == *"uvicorn"*"prithi_web:app"* ]]; then
      kill "${PID}"
      for _ in $(seq 1 30); do kill -0 "${PID}" 2>/dev/null || break; sleep 0.2; done
      echo "Stopped Prithi web PID ${PID}."
    else
      echo "Refusing to stop PID ${PID}: it is not the recorded Prithi web process." >&2
      exit 1
    fi
  fi
  rm -f "${WEB_PID_FILE}"
else
  echo "No Prithi-managed web PID file; web process unchanged."
fi

"${SCRIPT_DIR}/stop_prithi_runtime.sh"
