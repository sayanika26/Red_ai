# Lightning Studio clone report

## Repository

- Remote: `https://github.com/sayanika26/Red_ai.git`
- Branch: `main`
- Source project: `~/prithi-voice`
- Version: `1.0.0`
- Local portability commits before this report update: `3064341`, `aed1384`, and `48f6119`

## Commands

```bash
./bootstrap_prithi_studio.sh                     # application only
./bootstrap_prithi_studio.sh --with-adult-model  # application + adult model
./bootstrap_prithi_studio.sh --with-training     # application + training environment
./scripts/verify_fresh_install.sh
./scripts/start_prithi_all.sh
```

Git restores source, web UI, tests, safe configuration templates, manifests, training/evaluation tooling and safe text data. Bootstrap recreates virtual environments, dependencies and runtime directories, installs Ollama, and downloads the required production LLM and STT model only when absent.

Restore `secrets/google-tts.json`, private `app/.env`, optional SQLite memory, and private LoRA adapters separately. Normal Git excludes credentials, user data, recordings, generated audio, runtime caches and checkpoints.

## Current Studio audit

- Ollama storage: `runtime/ollama/models/`, 32 GB currently across production and evaluation models.
- Whisper storage: `runtime/whisper/models/`, 4.4 GB currently including large-v3 and an existing turbo model.
- Private ignored training checkpoints: 1019 MB.
- Application environment: Python 3.10.20; package versions are recorded in `config/environment_manifest.json`.
- Production/web: health passed with `gemma3:12b`; the optional adult model was detected.
- Regression suite: 178 tests passed.
- Secret scan: passed; it reports paths/types only, never values.
- Portable data: backup/restore round-trip passed with database and `.env` restored as mode `0600`.

The minimum planned download is about 8.1 GB for production Ollama plus 3.1 GB for large-v3. The optional adult model adds about 9 GB. Budget at least 18 GB for app-only or 29 GB with the adult model, plus package caches and working headroom.

## Simulated fresh-install result

A no-hardlink clone was created at `/tmp/prithi-fresh-test`. Dry-run and `--skip-model-download` bootstrap modes passed. The simulation verified executable modes, shell syntax, requirements installation logic, runtime directory creation, private `.env` generation with mode `0600`, model-download suppression, and a clean Git worktree. It did not download Ollama or Whisper models.

## Repository synchronization

The local `main` branch was fetched and confirmed based on `origin/main` before committing. A normal, non-force push was attempted. It is blocked because this Studio has no GitHub authentication: `gh auth status` reports no authenticated host and SSH authentication has no usable key. The branch is ahead locally until the owner authenticates and pushes. No remote history was rewritten.

## Known limitations

- This SSH session does not expose `nvidia-smi` or PyTorch CUDA, although the Studio is the known NVIDIA L4 target and the existing Ollama/web services are healthy. Repeat GPU verification from an active GPU-backed Studio session.
- Google credentials must be restored separately.
- Large download time depends on Lightning/provider bandwidth.
- Bootstrap deliberately cannot embed private-repository authentication.

LIGHTNING CLONE SYSTEM STATUS: BLOCKED

Blocker: authenticate GitHub in this Studio and push the local commits. Then a strict remote-URL clone simulation can be run if required.
