#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == Linux ]] || { echo "Prithi setup currently requires Linux."; exit 1; }
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PRITHI_VENV_DIR:-${HOME}/.virtualenvs/prithi-voice}"
if command -v python3.10 >/dev/null 2>&1; then PYTHON_BIN=python3.10; else PYTHON_BIN=python3; fi
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || { echo "Install Python 3.10 or newer."; exit 1; }
"${PYTHON_BIN}" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then "${PYTHON_BIN}" -m venv "${VENV_DIR}"; fi
"${VENV_DIR}/bin/python" -m ensurepip --upgrade
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements.txt"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg is missing. Install it with your Linux package manager (for Ubuntu: sudo apt-get install ffmpeg)."
fi
mkdir -p "${PROJECT_ROOT}/app/output" "${PROJECT_ROOT}/secrets" \
  "${PROJECT_ROOT}/runtime/ollama/bin" "${PROJECT_ROOT}/runtime/ollama/models" "${PROJECT_ROOT}/runtime/ollama/logs" \
  "${PROJECT_ROOT}/runtime/whisper/models" "${PROJECT_ROOT}/runtime/whisper/logs" \
  "${PROJECT_ROOT}/runtime/prithi_memory" "${PROJECT_ROOT}/runtime/web"
chmod 700 "${PROJECT_ROOT}/secrets" "${PROJECT_ROOT}/runtime/prithi_memory"
if [[ ! -f "${PROJECT_ROOT}/app/.env" ]]; then
  cp "${PROJECT_ROOT}/app/.env.example" "${PROJECT_ROOT}/app/.env"
  WEB_TOKEN="$("${VENV_DIR}/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed -i "s|^PRITHI_WEB_ACCESS_TOKEN=.*$|PRITHI_WEB_ACCESS_TOKEN=${WEB_TOKEN}|" "${PROJECT_ROOT}/app/.env"
  chmod 600 "${PROJECT_ROOT}/app/.env"
  echo "Created private app/.env with a random web access token."
fi
for file in VERSION app/prithi_brain.py app/prithi_memory.py app/prithi_voice.py app/prithi_stt.py app/prithi_web.py scripts/start_prithi_runtime.sh scripts/start_prithi_web.sh; do
  [[ -f "${PROJECT_ROOT}/${file}" ]] || { echo "Missing required source: ${file}"; exit 1; }
done
chmod u+x "${PROJECT_ROOT}/setup.sh" "${PROJECT_ROOT}"/scripts/*.sh
echo "Setup complete. Large models were not downloaded."
echo "Next: ./scripts/bootstrap_models.sh"
echo "Then: configure secrets/google-tts.json and run ./scripts/start_prithi_all.sh"
