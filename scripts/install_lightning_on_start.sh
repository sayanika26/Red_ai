#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
START_FILE="${HOME}/.lightning_studio/on_start.sh"
BEGIN="# >>> PRITHI RUNTIME >>>"
END="# <<< PRITHI RUNTIME <<<"
mkdir -p "$(dirname "${START_FILE}")"
if [[ -f "${START_FILE}" ]] && grep -Fq "scripts/start_prithi_runtime.sh" "${START_FILE}"; then
  echo "Prithi on-start block already installed: ${START_FILE}"; exit 0
fi
if [[ -f "${START_FILE}" ]]; then
  cp -p "${START_FILE}" "${START_FILE}.backup.$(date -u +%Y%m%dT%H%M%SZ)"
else
  printf '%s\n' '#!/usr/bin/env bash' 'set -u' >"${START_FILE}"
fi
printf '\n%s\n%s\n%s\n' "${BEGIN}" "\"${PROJECT_ROOT}/scripts/start_prithi_runtime.sh\" >>\"${PROJECT_ROOT}/runtime/ollama/logs/on-start.log\" 2>&1 || true" "${END}" >>"${START_FILE}"
chmod u+x "${START_FILE}"
echo "Installed safe user-level Lightning on-start block: ${START_FILE}"
