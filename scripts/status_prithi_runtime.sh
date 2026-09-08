#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${PROJECT_ROOT}/runtime/ollama"
OLLAMA_BIN="${RUNTIME_DIR}/bin/ollama"
export OLLAMA_MODELS="${RUNTIME_DIR}/models"
MODEL="gemma3:12b"

[[ -x "${OLLAMA_BIN}" ]] && INSTALLED=yes || INSTALLED=no
pgrep -f "${RUNTIME_DIR}/bin/ollama serve" >/dev/null 2>&1 && RUNNING=yes || RUNNING=no
curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && HEALTHY=yes || HEALTHY=no
if [[ "${HEALTHY}" == yes ]] && curl -fsS --max-time 2 http://127.0.0.1:11434/v1/models | grep -q "${MODEL}"; then
  AVAILABLE=yes
else
  AVAILABLE=no
fi

echo "Ollama installed: ${INSTALLED}"
echo "Ollama running: ${RUNNING}"
echo "API healthy: ${HEALTHY}"
echo "Model available: ${AVAILABLE}"
echo "Configured model: ${MODEL}"
echo "Model storage location: ${OLLAMA_MODELS}"
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU detected: yes ($(nvidia-smi --query-gpu=name --format=csv,noheader | head -1))"
  VRAM="$(nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader 2>/dev/null | grep -E 'ollama|llama-server' || true)"
  echo "Approximate Ollama GPU VRAM use: ${VRAM:-none (model may not be loaded)}"
else
  echo "GPU detected: no"
  echo "Approximate Ollama GPU VRAM use: unavailable"
fi
echo "Current Ollama processes:"
pgrep -af 'ollama|llama-server' || echo "none"

WHISPER_MODEL_PATH="${PROJECT_ROOT}/runtime/whisper/models/large-v3-turbo"
if [[ -f "${WHISPER_MODEL_PATH}/model.bin" ]]; then
  WHISPER_AVAILABLE=yes
else
  WHISPER_AVAILABLE=no
fi
echo "Whisper model available: ${WHISPER_AVAILABLE}"
echo "Whisper model path: ${WHISPER_MODEL_PATH}"
VENV_PYTHON="${PRITHI_VENV_DIR:-${HOME}/.virtualenvs/prithi-voice}/bin/python"
if [[ -x "${VENV_PYTHON}" ]] && command -v nvidia-smi >/dev/null 2>&1 && "${VENV_PYTHON}" -c 'import ctranslate2; assert "float16" in ctranslate2.get_supported_compute_types("cuda")' >/dev/null 2>&1; then
  echo "STT GPU readiness: yes (CTranslate2 CUDA float16)"
else
  echo "STT GPU readiness: no or not yet verified"
fi
