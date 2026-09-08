#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="${HOME}/prithi-voice"
"${PROJECT_ROOT}/scripts/start_prithi_runtime.sh" >>"${PROJECT_ROOT}/runtime/ollama/logs/on-start.log" 2>&1
