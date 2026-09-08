#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${PROJECT_ROOT}/runtime/ollama"
BIN_DIR="${RUNTIME_DIR}/bin"; MODEL_DIR="${RUNTIME_DIR}/models"; LOG_DIR="${RUNTIME_DIR}/logs"
LIB_DIR="${RUNTIME_DIR}/lib/ollama"; OLLAMA_BIN="${BIN_DIR}/ollama"; PID_FILE="${RUNTIME_DIR}/ollama.pid"
if [[ -f "${PROJECT_ROOT}/app/.env" ]]; then set -a; source "${PROJECT_ROOT}/app/.env"; set +a; fi
export OLLAMA_MODELS="${MODEL_DIR}" OLLAMA_HOST="127.0.0.1:11434"
export PRITHI_LLM_BASE_URL="${PRITHI_LLM_BASE_URL:-http://127.0.0.1:11434/v1}"
export PRITHI_LLM_API_KEY="${PRITHI_LLM_API_KEY:-ollama}" PRITHI_LLM_MODEL="${PRITHI_LLM_MODEL:-gemma3:12b}"
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-${PROJECT_ROOT}/secrets/google-tts.json}"
export PATH="${BIN_DIR}:${PATH}" LD_LIBRARY_PATH="${LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
mkdir -p "${BIN_DIR}" "${MODEL_DIR}" "${LOG_DIR}" "${RUNTIME_DIR}/lib"
if [[ ! -x "${OLLAMA_BIN}" ]]; then
  echo "Persistent Ollama binary missing; restoring it."
  command -v ollama >/dev/null 2>&1 || curl -fsSL https://ollama.com/install.sh | sh
  cp -n "$(command -v ollama)" "${OLLAMA_BIN}"; chmod u+x "${OLLAMA_BIN}"
  [[ -d "${LIB_DIR}" || ! -d /usr/local/lib/ollama ]] || cp -a /usr/local/lib/ollama "${RUNTIME_DIR}/lib/"
fi
if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  if [[ ! -f "${PID_FILE}" ]] || ! kill -0 "$(<"${PID_FILE}")" 2>/dev/null; then
    rm -f "${PID_FILE}"; nohup "${OLLAMA_BIN}" serve >>"${LOG_DIR}/ollama.log" 2>&1 & echo $! >"${PID_FILE}"
    echo "Started Prithi Ollama process PID $(<"${PID_FILE}")."
  fi
fi
for _ in $(seq 1 60); do curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break; sleep 1; done
curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null
if ! "${OLLAMA_BIN}" list | awk 'NR > 1 {print $1}' | grep -Fxq "${PRITHI_LLM_MODEL}"; then
  echo "${PRITHI_LLM_MODEL} is missing from ${OLLAMA_MODELS}; pulling it once."
  "${OLLAMA_BIN}" pull "${PRITHI_LLM_MODEL}" 2>&1 | tee -a "${LOG_DIR}/model-pull.log"
else echo "Reusing existing persistent model ${PRITHI_LLM_MODEL}."; fi
curl -fsS "${PRITHI_LLM_BASE_URL}/models" | grep -q "${PRITHI_LLM_MODEL}"
command -v nvidia-smi >/dev/null 2>&1 && echo "GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
echo "Prithi runtime ready: ${PRITHI_LLM_BASE_URL} (${PRITHI_LLM_MODEL})"
