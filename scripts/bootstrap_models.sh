#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
mkdir -p "${PROJECT_ROOT}/runtime/ollama/models" "${PROJECT_ROOT}/runtime/whisper/models"
"${SCRIPT_DIR}/start_prithi_runtime.sh"
WHISPER_MODEL="${PROJECT_ROOT}/runtime/whisper/models/large-v3-turbo/model.bin"
if [[ -f "${WHISPER_MODEL}" ]]; then
  echo "Whisper large-v3-turbo already exists; no download needed."
else
  echo "Whisper large-v3-turbo is optional and has not been downloaded."
  echo "Add it later with: cd app && python -c 'from prithi_stt import ensure_model_downloaded; ensure_model_downloaded()'"
fi
