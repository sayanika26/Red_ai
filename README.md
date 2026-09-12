# Prithi Voice AI

Prithi v1 is a Bengali-first, Hindi/English-capable browser voice companion. Browser audio is transcribed locally with faster-whisper on NVIDIA GPU, structured conversational replies come from a local OpenAI-compatible Ollama model, and Google Chirp/Gemini TTS returns spoken audio. SQLite stores only compact, per-browser-user profile, relationship, and approved stable-memory state.

## Prithi v1 — Quick Start

### Fresh Lightning Studio

```bash
git clone https://github.com/sayanika26/Red_ai.git prithi-voice
cd prithi-voice
./setup.sh
./scripts/bootstrap_models.sh
```

Place the Google service-account file at `secrets/google-tts.json`, restrict it, and review the private configuration:

```bash
chmod 600 secrets/google-tts.json
nano app/.env
./scripts/start_prithi_all.sh
```

The setup script creates `app/.env` with a random web access token when it is missing. It never creates or copies Google credentials. Use Lightning's port viewer for the configured port (default `8000`); the start script deliberately does not invent a public URL.

### Existing installation

```bash
cd ~/prithi-voice
./scripts/start_prithi_all.sh
```

## Runtime commands

```bash
# Full safe status (add PRITHI_STATUS_RUN_TESTS=true to run tests)
./scripts/status_prithi_runtime.sh

# Stop only Prithi-managed web and Ollama processes
./scripts/stop_prithi_all.sh

# Start components separately when debugging
./scripts/start_prithi_runtime.sh
./scripts/start_prithi_web.sh
```

## Backup and restore memory

Backups default to the private directory `~/prithi-backups` and deliberately exclude credentials, `app/.env`, recordings, generated audio, and public model weights.

```bash
./scripts/backup_prithi.sh
./scripts/restore_prithi.sh ~/prithi-backups/PRITHI_BACKUP_DIRECTORY
./scripts/start_prithi_all.sh
```

The restore script validates SQLite integrity, preserves the previous database as `prithi_memory.db.pre-restore`, restores mode `0600`, and requires a web restart before restored relationship state is loaded.

## Architecture

`Browser microphone → PCM conversion → forced-language faster-whisper → Prithi Brain → Ollama gemma3:12b → validated language/emotion/style → Google TTS → browser playback`

The browser keeps only an opaque random identity. SQLite stores its SHA-256 digest, not the raw identifier. Eight-turn conversational history stays in RAM; only compact stable facts, profile preferences, and relationship metrics persist.

## Models and providers

- LLM: `gemma3:12b` through local Ollama's OpenAI-compatible endpoint.
- Bengali STT: persistent `large-v3`; other/backup STT: `large-v3-turbo`.
- Neutral TTS: Google Chirp 3 HD Leda (`bn-IN`, `hi-IN`, `en-IN`).
- Expressive TTS: Google Gemini TTS Leda where supported.

## Change the Ollama model

```bash
OLLAMA_MODELS="$PWD/runtime/ollama/models" runtime/ollama/bin/ollama pull NEW_MODEL
```

Then set `PRITHI_LLM_MODEL=NEW_MODEL` in the private `app/.env` and restart Prithi. The configured model must support the existing strict JSON output contract.

## Persistent paths

- Ollama models/runtime: `runtime/ollama/`
- Whisper models: `runtime/whisper/models/`
- SQLite memory: `runtime/prithi_memory/prithi_memory.db`
- Short-lived browser response audio: `runtime/web/audio/`
- Private Google credential: `secrets/google-tts.json`
- Private environment configuration: `app/.env`

Everything under `runtime/`, all secrets/private configuration, model caches, generated audio, and private recordings are excluded from Git.

## Validation and troubleshooting

```bash
source ~/.virtualenvs/prithi-voice/bin/activate
python -m unittest discover -s app -p 'test_*.py'
./scripts/scan_secrets.sh
./scripts/status_prithi_runtime.sh
```

- Port `11434` refused: run `./scripts/start_prithi_runtime.sh`.
- Web page unavailable: run `./scripts/start_prithi_all.sh`, then check the configured port in Lightning.
- Missing models: run `./scripts/bootstrap_models.sh`.
- TTS error: confirm `secrets/google-tts.json` exists with mode `0600`.
- STT CUDA error: run `./scripts/verify_environment.sh` and confirm NVIDIA L4/CUDA availability.

Prithi v1 remains a prototype: Bengali STT can misrecognize words, expressive Gemini TTS is the largest latency component, Gemma 3 can be conservative in adult/flirty contexts, and the voice is not a fine-tuned custom Prithi foundation model.

## Clone Prithi to a New Lightning Studio

1. Create a Lightning Studio with an NVIDIA GPU. The known-good target is an NVIDIA L4 with about 23 GB VRAM.
2. Open the terminal and authenticate to the private GitHub repository using an SSH key, GitHub CLI, or the Git credential helper.
3. Clone and enter the project:

   ```bash
   git clone https://github.com/sayanika26/Red_ai.git prithi-voice
   cd prithi-voice
   ```

4. Choose one setup:

   ```bash
   ./bootstrap_prithi_studio.sh                     # application only
   ./bootstrap_prithi_studio.sh --with-adult-model  # application + optional adult model
   ./bootstrap_prithi_studio.sh --with-training     # application + training environment
   ```

5. Restore Google credentials separately as described in `docs/SECRETS_RESTORE.md`, then run:

   ```bash
   ./scripts/verify_fresh_install.sh
   ./scripts/start_prithi_all.sh
   ```

6. Open Lightning's port viewer for port `8000`, enter the private Prithi web token from `app/.env`, and allow browser microphone access.

The production Ollama model is about 8 GB, faster-whisper large-v3 is about 3 GB, and the optional adult Ollama model is about 9 GB. Budget at least 18 GB for app-only setup or 29 GB with the adult model, plus package caches and headroom. Download time depends on Studio/network speed and commonly dominates setup.

Git restores source, web UI, tests, safe configuration templates, manifests, and safe training/evaluation text artifacts. It never restores secrets, SQLite user memory, recordings, generated audio, model caches, or LoRA checkpoints. See `docs/PORTABILITY_AUDIT.md`, `docs/NEW_LIGHTNING_STUDIO_CHECKLIST.md`, and `docs/MODEL_BACKUP_STRATEGY.md`.

For a one-line-style beginner wrapper downloaded from a trusted source or run inside a clone:

```bash
bash install_prithi.sh --repo https://github.com/sayanika26/Red_ai.git --branch main --with-adult-model
```

Private repository authentication is deliberately not embedded in any installer.
