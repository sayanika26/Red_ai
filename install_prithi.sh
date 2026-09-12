#!/usr/bin/env bash
set -euo pipefail

REPO=""
BRANCH="main"
WITH_ADULT=false
WITH_TRAINING=false
SKIP_MODELS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --with-adult-model) WITH_ADULT=true; shift ;;
    --with-training) WITH_TRAINING=true; shift ;;
    --skip-model-download) SKIP_MODELS=true; shift ;;
    -h|--help) echo "Usage: bash install_prithi.sh --repo <git-url> [--branch main] [--with-adult-model] [--with-training] [--skip-model-download]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ -f "./bootstrap_prithi_studio.sh" && -d .git ]]; then
  PROJECT_ROOT="$(pwd)"
else
  [[ -n "${REPO}" ]] || { echo "--repo is required outside an existing Prithi clone." >&2; exit 2; }
  TARGET="${HOME}/prithi-voice"
  [[ ! -e "${TARGET}" ]] || { echo "Refusing to overwrite existing ${TARGET}. Enter that clone and run bootstrap directly." >&2; exit 1; }
  git clone --branch "${BRANCH}" --single-branch "${REPO}" "${TARGET}"
  PROJECT_ROOT="${TARGET}"
fi

ARGS=()
${WITH_ADULT} && ARGS+=(--with-adult-model)
${WITH_TRAINING} && ARGS+=(--with-training)
${SKIP_MODELS} && ARGS+=(--skip-model-download)
cd "${PROJECT_ROOT}"
exec ./bootstrap_prithi_studio.sh "${ARGS[@]}"
