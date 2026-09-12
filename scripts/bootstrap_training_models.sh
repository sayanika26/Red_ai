#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
echo "Training model downloads are intentionally opt-in and are not started automatically."
echo "Review training/reports/base_model_license.md and training/scripts/train_stage23_qlora.py first."
echo "Recommended private cache root: ${PROJECT_ROOT}/training/hf_cache"
echo "Set HF_HOME to that directory before an explicitly authorized download."
