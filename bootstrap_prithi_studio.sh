#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
APP_VENV="${HOME}/.virtualenvs/prithi-voice"
TRAINING_VENV="${HOME}/.virtualenvs/prithi-training"
WITH_TRAINING=false
WITH_ADULT=false
SKIP_MODELS=false
DRY_RUN=false

usage() {
  echo "Usage: ./bootstrap_prithi_studio.sh [--with-training] [--with-adult-model] [--skip-model-download] [--dry-run]"
}
for arg in "$@"; do
  case "$arg" in
    --with-training) WITH_TRAINING=true ;;
    --with-adult-model) WITH_ADULT=true ;;
    --skip-model-download) SKIP_MODELS=true ;;
    --dry-run) DRY_RUN=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage; exit 2 ;;
  esac
done

[[ "$(uname -s)" == Linux ]] || { echo "Prithi bootstrap requires Linux." >&2; exit 1; }
[[ -f "${PROJECT_ROOT}/requirements.txt" && -d "${PROJECT_ROOT}/app" ]] || { echo "Run this script from a complete Prithi clone." >&2; exit 1; }

AVAILABLE_GB="$(df -Pk "${PROJECT_ROOT}" | awk 'NR==2 {printf "%d", $4/1024/1024}')"
REQUIRED_GB=18
${WITH_ADULT} && REQUIRED_GB=29
echo "Project root: ${PROJECT_ROOT}"
echo "Free disk: ${AVAILABLE_GB} GB; recommended minimum for selected setup: ${REQUIRED_GB} GB"
if [[ "${AVAILABLE_GB}" -lt "${REQUIRED_GB}" && "${SKIP_MODELS}" == false ]]; then
  echo "Insufficient free disk for the selected model downloads." >&2; exit 1
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
else
  echo "WARNING: nvidia-smi is unavailable. Use an NVIDIA GPU Lightning Studio before inference." >&2
fi

PYTHON_BIN="$(command -v python3.10 || command -v python3 || true)"
[[ -n "${PYTHON_BIN}" ]] || { echo "Python 3 is required." >&2; exit 1; }
echo "Python: $(${PYTHON_BIN} --version 2>&1)"

if ${DRY_RUN}; then
  echo "DRY RUN: validated platform, project root, disk logic, and Python discovery."
  echo "DRY RUN: would prepare app=${APP_VENV}, training=${WITH_TRAINING}, adult=${WITH_ADULT}, skip-models=${SKIP_MODELS}."
  exit 0
fi

mkdir -p "${HOME}/.virtualenvs" \
  "${PROJECT_ROOT}/runtime/ollama/bin" "${PROJECT_ROOT}/runtime/ollama/models" "${PROJECT_ROOT}/runtime/ollama/logs" \
  "${PROJECT_ROOT}/runtime/whisper/models" "${PROJECT_ROOT}/runtime/whisper/logs" \
  "${PROJECT_ROOT}/runtime/prithi_memory" "${PROJECT_ROOT}/runtime/web" \
  "${PROJECT_ROOT}/app/output" "${PROJECT_ROOT}/secrets"

create_venv() {
  local target="$1"
  if [[ -x "${target}/bin/python" ]] && "${target}/bin/python" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    [[ "${target}" == "${HOME}/.virtualenvs/"* ]] || { echo "Unsafe virtualenv target: ${target}" >&2; exit 1; }
    rm -rf "${target}"
    uv venv --seed --python 3.10 "${target}"
  else
    "${PYTHON_BIN}" -m venv "${target}" || {
      echo "Python venv creation failed. Install python3-venv or install uv, then rerun." >&2
      exit 1
    }
  fi
}

create_venv "${APP_VENV}"
"${APP_VENV}/bin/python" -m pip install --upgrade pip
"${APP_VENV}/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements.txt"

if ${WITH_TRAINING}; then
  create_venv "${TRAINING_VENV}"
  "${TRAINING_VENV}/bin/python" -m pip install --upgrade pip
  "${TRAINING_VENV}/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements-training.txt"
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo apt-get update && sudo apt-get install -y ffmpeg
  else
    echo "WARNING: FFmpeg is missing and passwordless package installation is unavailable; install ffmpeg through the Studio package manager." >&2
  fi
fi

if [[ ! -f "${PROJECT_ROOT}/app/.env" ]]; then
  cp "${PROJECT_ROOT}/app/.env.example" "${PROJECT_ROOT}/app/.env"
  TOKEN="$(${APP_VENV}/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed -i "s|^PRITHI_WEB_ACCESS_TOKEN=.*$|PRITHI_WEB_ACCESS_TOKEN=${TOKEN}|" "${PROJECT_ROOT}/app/.env"
  chmod 600 "${PROJECT_ROOT}/app/.env"
  echo "Created private app/.env with a random web token; existing files are never overwritten."
fi

if ${SKIP_MODELS}; then
  echo "Model downloads skipped by request. Runtime/model detection will be completed by verification."
else
  "${PROJECT_ROOT}/scripts/start_prithi_runtime.sh"
  if ${WITH_ADULT}; then
    ADULT_MODEL="richardyoung/qwen3-14b-abliterated:Q4_K_M"
    if ! "${PROJECT_ROOT}/runtime/ollama/bin/ollama" list | awk 'NR > 1 {print $1}' | grep -Fxq "${ADULT_MODEL}"; then
      OLLAMA_MODELS="${PROJECT_ROOT}/runtime/ollama/models" "${PROJECT_ROOT}/runtime/ollama/bin/ollama" pull "${ADULT_MODEL}"
    else
      echo "Reusing existing optional adult model ${ADULT_MODEL}."
    fi
  fi
  WHISPER_DIR="${PROJECT_ROOT}/runtime/whisper/models/large-v3"
  if [[ -s "${WHISPER_DIR}/model.bin" && -s "${WHISPER_DIR}/config.json" ]]; then
    echo "Reusing persistent faster-whisper large-v3."
  else
    mkdir -p "${WHISPER_DIR}"
    "${APP_VENV}/bin/python" -c 'from faster_whisper.utils import download_model; import sys; download_model("large-v3", output_dir=sys.argv[1])' "${WHISPER_DIR}"
  fi
fi

echo "Bootstrap complete. Restore Google credentials separately, then run ./scripts/verify_fresh_install.sh."
