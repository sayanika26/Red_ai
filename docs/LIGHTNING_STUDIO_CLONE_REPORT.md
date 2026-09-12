# Lightning Studio clone report

## Repository

- Remote: `https://github.com/sayanika26/Red_ai.git`
- Branch: `main`
- Source project: `~/prithi-voice`
- Version: `1.0.0`

## Commands

```bash
# Application only
./bootstrap_prithi_studio.sh

# Application plus adult model
./bootstrap_prithi_studio.sh --with-adult-model

# Application plus training environment (no training checkpoint download)
./bootstrap_prithi_studio.sh --with-training

# Verify and start
./scripts/verify_fresh_install.sh
./scripts/start_prithi_all.sh
```

Git restores source, web UI, tests, safe configuration templates, manifests, training/evaluation tooling and safe text data. Bootstrap recreates virtual environments, dependencies and runtime directories, installs Ollama, and downloads the required production LLM and STT model only when absent.

Restore `secrets/google-tts.json`, private `app/.env`, optional SQLite memory, and private LoRA adapters separately. The normal Git repository excludes credentials, user data, recordings, generated audio, runtime caches and checkpoints.

Expected download/storage: roughly 8 GB for the production Ollama model, about 3 GB for faster-whisper large-v3, and roughly 9 GB extra for the optional adult model, plus package/working overhead. Setup time depends mainly on Studio network throughput and Python package installation.

The fresh-clone simulation validates repository contents, shell syntax, path discovery, directory/config logic and model detection without downloading tens of gigabytes. GPU inference, Google TTS, browser microphone permission and a live Bengali turn require a running GPU Studio and restored credentials.

Repository synchronization details and the final commit are recorded in Git after this report is committed and pushed.

**LIGHTNING CLONE SYSTEM STATUS: READY**
