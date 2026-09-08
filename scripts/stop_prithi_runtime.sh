#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${PROJECT_ROOT}/runtime/ollama"
PID_FILE="${RUNTIME_DIR}/ollama.pid"
EXPECTED="${RUNTIME_DIR}/bin/ollama"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "No Prithi-managed Ollama PID file; nothing stopped."
  exit 0
fi
PID="$(<"${PID_FILE}")"
if ! kill -0 "${PID}" 2>/dev/null; then
  rm -f "${PID_FILE}"
  echo "Removed stale Prithi Ollama PID file."
  exit 0
fi
COMMAND="$(tr '\0' ' ' <"/proc/${PID}/cmdline")"
if [[ "${COMMAND}" != *"${EXPECTED}"* ]]; then
  echo "Refusing to stop PID ${PID}: it was not started from the Prithi runtime."
  exit 1
fi
kill "${PID}"
for _ in $(seq 1 20); do
  kill -0 "${PID}" 2>/dev/null || break
  sleep 0.25
done
rm -f "${PID_FILE}"
echo "Stopped Prithi Ollama runtime PID ${PID}."
