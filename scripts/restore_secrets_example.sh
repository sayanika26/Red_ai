#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${1:-}"
TARGET="${PROJECT_ROOT}/secrets/google-tts.json"

[[ -n "${SOURCE}" ]] || { echo "Usage: ./scripts/restore_secrets_example.sh /secure/path/google-service-account.json" >&2; exit 2; }
[[ -f "${SOURCE}" ]] || { echo "Credential source does not exist." >&2; exit 1; }
mkdir -p "${PROJECT_ROOT}/secrets"
[[ ! -e "${TARGET}" ]] || { echo "Refusing to overwrite existing ${TARGET}." >&2; exit 1; }
install -m 600 "${SOURCE}" "${TARGET}"
echo "Credential installed at ${TARGET} with mode 0600. Contents were not displayed."
