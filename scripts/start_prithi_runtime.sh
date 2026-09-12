#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${PROJECT_ROOT}/runtime/ollama"
BIN_DIR="${RUNTIME_DIR}/bin"; MODEL_DIR="${RUNTIME_DIR}/models"; LOG_DIR="${RUNTIME_DIR}/logs"
LIB_DIR="${RUNTIME_DIR}/lib/ollama"; OLLAMA_BIN="${BIN_DIR}/ollama"; PID_FILE="${RUNTIME_DIR}/ollama.pid"
if [[ -f "${PROJECT_ROOT}/app/.env" ]]; then set -a; source "${PROJECT_ROOT}/app/.env"; set +a; fi
export OLLAMA_MODELS="${MODEL_DIR}" OLLAMA_HOST="127.0.0.1:11434"
export OLLAMA_KEEP_ALIVE="${PRITHI_OLLAMA_KEEP_ALIVE:-10m}"
export PRITHI_LLM_BASE_URL="${PRITHI_LLM_BASE_URL:-http://127.0.0.1:11434/v1}"
export PRITHI_LLM_API_KEY="${PRITHI_LLM_API_KEY:-ollama}" PRITHI_LLM_MODEL="${PRITHI_LLM_MODEL:-gemma3:12b}"
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-${PROJECT_ROOT}/secrets/google-tts.json}"
export PATH="${BIN_DIR}:${PATH}" LD_LIBRARY_PATH="${LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
mkdir -p "${BIN_DIR}" "${MODEL_DIR}" "${LOG_DIR}" "${RUNTIME_DIR}/lib"

if [[ ! -x "${OLLAMA_BIN}" ]]; then
  echo "Persistent Ollama binary missing; restoring project-managed runtime."
  if command -v ollama >/dev/null 2>&1; then
    cp "$(command -v ollama)" "${OLLAMA_BIN}"
    for candidate in /usr/local/lib/ollama /usr/lib/ollama; do
      [[ -d "${candidate}" && ! -d "${LIB_DIR}" ]] && cp -a "${candidate}" "${RUNTIME_DIR}/lib/"
    done
  else
    TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
    ARCH="$(uname -m)"; [[ "${ARCH}" == x86_64 ]] && ARCH=amd64
    [[ "${ARCH}" == amd64 || "${ARCH}" == arm64 ]] || { echo "Unsupported Ollama architecture: ${ARCH}" >&2; exit 1; }
    curl -fsSL "https://ollama.com/download/ollama-linux-${ARCH}.tar.zst" -o "${TMP}/ollama.tar.zst"
    tar --zstd -xf "${TMP}/ollama.tar.zst" -C "${TMP}"
    [[ -x "${TMP}/bin/ollama" ]] || { echo "Official Ollama archive did not contain bin/ollama." >&2; exit 1; }
    cp "${TMP}/bin/ollama" "${OLLAMA_BIN}"
    [[ -d "${TMP}/lib/ollama" ]] && cp -a "${TMP}/lib/ollama" "${RUNTIME_DIR}/lib/"
  fi
  chmod u+x "${OLLAMA_BIN}"
fi

if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  if [[ ! -f "${PID_FILE}" ]] || ! kill -0 "$(<"${PID_FILE}")" 2>/dev/null; then
    rm -f "${PID_FILE}"
    nohup "${OLLAMA_BIN}" serve >>"${LOG_DIR}/ollama.log" 2>&1 & echo $! >"${PID_FILE}"
    echo "Started Prithi Ollama process PID $(<"${PID_FILE}")."
  fi
fi
for _ in $(seq 1 90); do curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break; sleep 1; done
curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null

if ! "${OLLAMA_BIN}" list | awk 'NR > 1 {print $1}' | grep -Fxq "${PRITHI_LLM_MODEL}"; then
  if [[ "${PRITHI_SKIP_MODEL_PULL:-false}" == true ]]; then
    echo "Production model is missing; pull skipped by PRITHI_SKIP_MODEL_PULL=true." >&2
  else
    echo "${PRITHI_LLM_MODEL} is missing from ${OLLAMA_MODELS}; pulling it once."
    "${OLLAMA_BIN}" pull "${PRITHI_LLM_MODEL}" 2>&1 | tee -a "${LOG_DIR}/model-pull.log"
  fi
else
  echo "Reusing existing persistent model ${PRITHI_LLM_MODEL}."
fi

if [[ "${PRITHI_SKIP_MODEL_PULL:-false}" != true ]]; then
  curl -fsS "${PRITHI_LLM_BASE_URL}/models" | grep -Fq "${PRITHI_LLM_MODEL}"
fi
command -v nvidia-smi >/dev/null 2>&1 && echo "GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" || echo "GPU check unavailable in this shell."
echo "Prithi runtime ready: ${PRITHI_LLM_BASE_URL} (${PRITHI_LLM_MODEL})"
