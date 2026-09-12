# Prithi Portability Audit

Audited project: `/teamspace/studios/this_studio/prithi-voice`  
Production model remains `gemma3:12b`; no runtime, model, credential, or user-data file is moved or deleted by this plan.

## A. Commit to Git

- Application source and tests under `app/`, excluding `app/.env`, `app/output/`, and Python caches.
- Browser UI under `app/web/`.
- Safe application template `app/.env.example`.
- Runtime/start/stop/verification/bootstrap scripts under `scripts/` and the root installers.
- Training source, schemas, curated text-only pilot data, deterministic splits, and non-secret reports under `training/`.
- Evaluation harness, safe prompts, golden eval data, and results under `evals/`.
- Documentation, `README.md`, `VERSION`, requirements, and safe JSON manifests under `config/`.
- Dataset recording guide and safe metadata CSV files.

## B. Download or recreate on a new Studio

- Application and optional training virtual environments.
- Python packages from `requirements.txt` and `requirements-training.txt`.
- FFmpeg and the project-managed Ollama runtime.
- Ollama `gemma3:12b` (required) and the adult candidate (optional).
- Faster-whisper `large-v3` model under `runtime/whisper/models/large-v3`.
- Runtime directories, logs, browser response cache, and an empty writable SQLite location.
- Private `app/.env`, generated from the safe example only when absent.

## C. Back up separately

- `runtime/prithi_memory/prithi_memory.db` when relationship/memory continuity is wanted.
- `app/.env` as private configuration; rotate the web token if a backup is exposed.
- `secrets/google-tts.json` in a secure credential store, never in the default portable-data archive.
- LoRA adapters/checkpoints under `training/checkpoints/` through private Hugging Face storage, private cloud storage, or an encrypted archive.
- Any human recordings or private reference audio that the owner explicitly wants to retain.

## D. Do not copy

- Ollama/Whisper/Hugging Face caches when they can be downloaded again.
- Generated auditions, response WAV files, browser audio, diagnostic recordings, temporary files, logs, PIDs, and Python bytecode.
- Synthetic audio as if it were human training data.
- Stale virtual environments and host-specific CUDA/system files.

## Current footprint and safety notes

The working project contains large persistent model/runtime data and private state, explaining most of its disk footprint. Git ignore rules isolate those artifacts. A clone is intentionally small; model downloads dominate fresh-install time and storage. Git restores code and safe text artifacts only.
