#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
echo "Git commit: $(git rev-parse HEAD 2>/dev/null || echo unavailable)"
echo "VERSION: $(tr -d '[:space:]' <VERSION)"
echo "Model manifest: config/model_manifest.json"
"${HOME}/.virtualenvs/prithi-voice/bin/python" -m json.tool config/model_manifest.json 2>/dev/null || sed -n '1,200p' config/model_manifest.json
echo "Environment manifest: config/environment_manifest.json"
"${HOME}/.virtualenvs/prithi-voice/bin/python" -m json.tool config/environment_manifest.json 2>/dev/null || sed -n '1,200p' config/environment_manifest.json
[[ -f runtime/prithi_memory/prithi_memory.db ]] && echo "Database present: yes" || echo "Database present: no"
if [[ -f app/.env ]]; then set -a; source app/.env; set +a; fi
[[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]] && echo "Secrets configured: yes" || echo "Secrets configured: no"
curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && echo "Ollama health: ok" || echo "Ollama health: unavailable"
PORT="${PRITHI_WEB_PORT:-8000}"
if [[ -n "${PRITHI_WEB_ACCESS_TOKEN:-}" ]] && curl -fsS --max-time 2 -H "Authorization: Bearer ${PRITHI_WEB_ACCESS_TOKEN}" "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then echo "Web health: ok"; else echo "Web health: unavailable"; fi
