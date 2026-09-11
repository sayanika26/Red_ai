#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/app/.env"
[[ -f "${ENV_FILE}" ]] && { set -a; source "${ENV_FILE}"; set +a; }

RUNTIME_DIR="${PROJECT_ROOT}/runtime/ollama"
OLLAMA_BIN="${RUNTIME_DIR}/bin/ollama"
export OLLAMA_MODELS="${RUNTIME_DIR}/models"
MODEL="${PRITHI_LLM_MODEL:-gemma3:12b}"
PORT="${PRITHI_WEB_PORT:-8000}"
VERSION="$(tr -d '[:space:]' <"${PROJECT_ROOT}/VERSION" 2>/dev/null || echo unknown)"

[[ -x "${OLLAMA_BIN}" ]] && OLLAMA_INSTALLED=yes || OLLAMA_INSTALLED=no
pgrep -f "${RUNTIME_DIR}/bin/ollama serve" >/dev/null 2>&1 && OLLAMA_RUNNING=yes || OLLAMA_RUNNING=no
curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && OLLAMA_HEALTHY=yes || OLLAMA_HEALTHY=no
if [[ "${OLLAMA_HEALTHY}" == yes ]] && curl -fsS --max-time 2 http://127.0.0.1:11434/v1/models | grep -Fq "${MODEL}"; then MODEL_AVAILABLE=yes; else MODEL_AVAILABLE=no; fi

PRIMARY_STT="${PRITHI_STT_BENGALI_PRIMARY:-large-v3}"
STT_PATH="${PROJECT_ROOT}/runtime/whisper/models/${PRIMARY_STT}"
[[ -f "${STT_PATH}/model.bin" ]] && STT_AVAILABLE=yes || STT_AVAILABLE=no
VENV_PYTHON="${PRITHI_VENV_DIR:-${HOME}/.virtualenvs/prithi-voice}/bin/python"
if [[ -x "${VENV_PYTHON}" ]] && command -v nvidia-smi >/dev/null 2>&1 && "${VENV_PYTHON}" -c 'import ctranslate2; assert "float16" in ctranslate2.get_supported_compute_types("cuda")' >/dev/null 2>&1; then STT_GPU=yes; else STT_GPU=no; fi

if [[ -n "${PRITHI_WEB_ACCESS_TOKEN:-}" ]] && curl -fsS --max-time 3 -H "Authorization: Bearer ${PRITHI_WEB_ACCESS_TOKEN}" "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then WEB_HEALTHY=yes; else WEB_HEALTHY=no; fi
pgrep -f "[u]vicorn prithi_web:app.*--port ${PORT}" >/dev/null 2>&1 && WEB_RUNNING=yes || WEB_RUNNING=no
MEMORY_DB="${PROJECT_ROOT}/runtime/prithi_memory/prithi_memory.db"
if [[ -f "${MEMORY_DB}" ]] && [[ -x "${VENV_PYTHON}" ]] && "${VENV_PYTHON}" - "${MEMORY_DB}" <<'PY' >/dev/null 2>&1
import sqlite3, sys
with sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True) as db:
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
PY
then MEMORY_AVAILABLE=yes; else MEMORY_AVAILABLE=no; fi
CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-${PROJECT_ROOT}/secrets/google-tts.json}"
[[ -n "${CREDENTIALS}" && -f "${CREDENTIALS}" ]] && TTS_CONFIGURED=yes || TTS_CONFIGURED=no

echo "Prithi version: ${VERSION}"
echo "Ollama installed: ${OLLAMA_INSTALLED}"
echo "Ollama running: ${OLLAMA_RUNNING}"
echo "Ollama healthy: ${OLLAMA_HEALTHY}"
echo "Configured LLM model: ${MODEL}"
echo "LLM model available: ${MODEL_AVAILABLE}"
echo "Ollama model storage: ${OLLAMA_MODELS}"
echo "STT model available: ${STT_AVAILABLE}"
echo "STT model: ${PRIMARY_STT}"
echo "STT model path: ${STT_PATH}"
echo "STT GPU readiness: ${STT_GPU}"
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU available: yes ($(nvidia-smi --query-gpu=name --format=csv,noheader | head -1))"
  VRAM="$(nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader 2>/dev/null | grep -E 'ollama|llama-server|python' || true)"
  echo "Approximate active GPU VRAM: ${VRAM:-none}"
else
  echo "GPU available: no"
fi
echo "Web process running: ${WEB_RUNNING}"
echo "Web health: ${WEB_HEALTHY}"
echo "Web port: ${PORT}"
echo "SQLite memory available: ${MEMORY_AVAILABLE}"
echo "TTS credentials configured: ${TTS_CONFIGURED}"
if [[ "${PRITHI_STATUS_RUN_TESTS:-false}" == true && -x "${VENV_PYTHON}" ]]; then
  if (cd "${PROJECT_ROOT}" && "${VENV_PYTHON}" -m unittest discover -s app -p 'test_*.py' >/dev/null); then echo "Test status: PASS"; else echo "Test status: FAIL"; fi
else
  echo "Test status: not run (set PRITHI_STATUS_RUN_TESTS=true)"
fi
