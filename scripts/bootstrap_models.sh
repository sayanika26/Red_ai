#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
mkdir -p "${PROJECT_ROOT}/runtime/ollama/models" "${PROJECT_ROOT}/runtime/whisper/models"
VENV_DIR="${PRITHI_VENV_DIR:-${HOME}/.virtualenvs/prithi-voice}"
[[ -x "${VENV_DIR}/bin/python" ]] || { echo "Prithi environment is missing; run ./setup.sh first." >&2; exit 1; }
if [[ -f "${PROJECT_ROOT}/app/.env" ]]; then set -a; source "${PROJECT_ROOT}/app/.env"; set +a; fi
"${SCRIPT_DIR}/start_prithi_runtime.sh"
PRIMARY="${PRITHI_STT_BENGALI_PRIMARY:-large-v3}"
[[ "${PRIMARY}" == "large-v3" || "${PRIMARY}" == "large-v3-turbo" ]] || { echo "Unsupported Bengali STT model: ${PRIMARY}" >&2; exit 1; }
"${VENV_DIR}/bin/python" - "${PROJECT_ROOT}/runtime/whisper/models" "${PRIMARY}" <<'PY'
import sys
from pathlib import Path
from faster_whisper.utils import download_model

root = Path(sys.argv[1])
models = ["large-v3-turbo"]
if sys.argv[2] == "large-v3":
    models.append("large-v3")
for name in models:
    destination = root / name
    if (destination / "model.bin").is_file():
        print(f"Whisper {name} already exists; reusing it.")
    else:
        print(f"Downloading Whisper {name} to persistent storage.")
        destination.mkdir(parents=True, exist_ok=True)
        download_model(name, output_dir=str(destination))
PY
echo "Model bootstrap complete."
