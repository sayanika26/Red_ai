#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV="${HOME}/.virtualenvs/prithi-voice"
PYTHON="${VENV}/bin/python"
ENV_FILE="${PROJECT_ROOT}/app/.env"
FAIL=0
pass() { echo "PASS: $1"; }
warn() { echo "WARN: $1"; }
fail() { echo "FAIL: $1"; FAIL=1; }

[[ -x "${PYTHON}" ]] && pass "Python environment ($(${PYTHON} --version 2>&1))" || fail "Python environment missing"
if [[ -x "${PYTHON}" ]]; then
  "${PYTHON}" -c 'import fastapi,uvicorn,httpx,faster_whisper,ctranslate2,torch,soundfile' >/dev/null 2>&1 && pass "required application packages" || fail "required application packages"
  "${PYTHON}" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1 && pass "PyTorch CUDA" || warn "PyTorch CUDA unavailable in this session"
fi
command -v nvidia-smi >/dev/null 2>&1 && { pass "nvidia-smi"; nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader; } || warn "nvidia-smi unavailable"
command -v ffmpeg >/dev/null 2>&1 && pass "FFmpeg" || fail "FFmpeg"
[[ -x "${PROJECT_ROOT}/runtime/ollama/bin/ollama" ]] && pass "project Ollama binary" || fail "project Ollama binary"
curl -fsS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && API=true || API=false
${API} && pass "Ollama API" || fail "Ollama API"
MODEL="gemma3:12b"
${API} && curl -fsS --max-time 3 http://127.0.0.1:11434/v1/models | grep -Fq "${MODEL}" && pass "production model ${MODEL}" || fail "production model ${MODEL}"
ADULT="richardyoung/qwen3-14b-abliterated:Q4_K_M"
${API} && curl -fsS --max-time 3 http://127.0.0.1:11434/v1/models | grep -Fq "${ADULT}" && pass "optional adult model" || warn "optional adult model not installed"
WHISPER="${PROJECT_ROOT}/runtime/whisper/models/large-v3"
[[ -s "${WHISPER}/model.bin" && -s "${WHISPER}/config.json" ]] && pass "Whisper large-v3 model" || fail "Whisper large-v3 model"
[[ -w "${PROJECT_ROOT}/runtime/prithi_memory" ]] && pass "SQLite directory writable" || fail "SQLite directory not writable"
for f in app/prithi_web.py app/prithi_stt.py app/prithi_brain.py app/prithi_voice.py; do [[ -f "${PROJECT_ROOT}/${f}" ]] || fail "missing ${f}"; done
[[ -f "${ENV_FILE}" ]] && pass "app/.env exists" || fail "app/.env missing"
if [[ -f "${ENV_FILE}" ]]; then set -a; source "${ENV_FILE}"; set +a; fi
CRED="${GOOGLE_APPLICATION_CREDENTIALS:-${PROJECT_ROOT}/secrets/google-tts.json}"
[[ -n "${CRED}" ]] && pass "Google credential path configured" || warn "Google credential path not configured"
[[ -n "${CRED}" && -f "${CRED}" ]] && pass "Google credential file exists" || warn "Google credential file absent"
if [[ -x "${PYTHON}" ]]; then
  (cd "${PROJECT_ROOT}" && "${PYTHON}" -m unittest discover -s app -p 'test_*.py') && pass "test suite" || fail "test suite"
fi
[[ "${FAIL}" -eq 0 ]] && { echo "Fresh-install verification: PASS"; exit 0; }
echo "Fresh-install verification: FAIL"; exit 1
