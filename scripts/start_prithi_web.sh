#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/app/.env"
VENV_DIR="${HOME}/.virtualenvs/prithi-voice"

if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  echo "Prithi Python environment is missing: ${VENV_DIR}" >&2
  exit 1
fi
source "${VENV_DIR}/bin/activate"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${PRITHI_WEB_ACCESS_TOKEN:-}" ]]; then
  echo "PRITHI_WEB_ACCESS_TOKEN is missing from app/.env." >&2
  exit 1
fi

export PRITHI_WEB_PORT="${PRITHI_WEB_PORT:-8000}"
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-${PROJECT_ROOT}/secrets/google-tts.json}"

"${PROJECT_ROOT}/scripts/start_prithi_runtime.sh"
cd "${PROJECT_ROOT}"
exec uvicorn prithi_web:app \
  --app-dir "${PROJECT_ROOT}/app" \
  --host 0.0.0.0 \
  --port "${PRITHI_WEB_PORT}" \
  --no-access-log
