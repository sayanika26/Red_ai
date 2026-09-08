#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PRITHI_VENV_DIR:-${HOME}/.virtualenvs/prithi-voice}"; PYTHON="${VENV_DIR}/bin/python"
echo "Project root: ${PROJECT_ROOT}"
[[ -x "${PYTHON}" ]] && { echo "Python version: $("${PYTHON}" --version 2>&1)"; echo "Virtualenv path: ${VENV_DIR}"; } || echo "Python virtualenv: missing"
[[ -x "${PYTHON}" ]] && "${PYTHON}" -m pip --version 2>/dev/null || echo "pip status: unavailable"
if command -v nvidia-smi >/dev/null 2>&1; then echo "NVIDIA GPU detected: yes"; nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader; else echo "NVIDIA GPU detected: no"; fi
if [[ -x "${PYTHON}" ]]; then "${PYTHON}" -c 'import torch; print("CUDA available:", torch.cuda.is_available()); print("CUDA version:", torch.version.cuda)' 2>/dev/null || echo "CUDA check: unavailable"; fi
command -v ffmpeg >/dev/null 2>&1 && echo "FFmpeg: $(ffmpeg -version 2>&1 | head -1)" || echo "FFmpeg: missing"
[[ -x "${PROJECT_ROOT}/runtime/ollama/bin/ollama" ]] && echo "Ollama binary: present" || echo "Ollama binary: missing"
curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && API=yes || API=no; echo "Ollama API healthy: ${API}"
MODEL="${PRITHI_LLM_MODEL:-gemma3:12b}"; echo "Configured model: ${MODEL}"
[[ "${API}" == yes ]] && curl -fsS http://127.0.0.1:11434/v1/models | grep -q "${MODEL}" && echo "Model available: yes" || echo "Model available: no"
CRED="${GOOGLE_APPLICATION_CREDENTIALS:-}"; [[ -n "${CRED}" ]] && echo "Google credential path set: yes" || echo "Google credential path set: no"
[[ -n "${CRED}" && -f "${CRED}" ]] && echo "Google credential file exists: yes" || echo "Google credential file exists: no"
MISSING=0; for f in app/prithi_brain.py app/prithi_chat.py app/prithi_voice.py app/prithi_stt.py; do [[ -f "${PROJECT_ROOT}/${f}" ]] || MISSING=1; done
[[ "${MISSING}" -eq 0 ]] && echo "Prithi source files exist: yes" || echo "Prithi source files exist: no"
if [[ -x "${PYTHON}" ]]; then
  if (cd "${PROJECT_ROOT}" && "${PYTHON}" app/test_prithi_brain.py >/dev/null && "${PYTHON}" app/test_llm_provider.py >/dev/null && "${PYTHON}" app/test_prithi_stt.py >/dev/null); then echo "Unit test status: PASS"; else echo "Unit test status: FAIL"; fi
else echo "Unit test status: NOT RUN"; fi
