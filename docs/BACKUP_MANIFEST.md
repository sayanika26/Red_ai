# Backup manifest

## Back up separately from Git

- `secrets/google-tts.json` and any future service credentials
- `app/.env` and other private configuration
- Future private trained checkpoints
- Future human voice recordings in `dataset/raw/`
- Processed private datasets and persistent user databases
- Generated audio that must be retained
- Optionally, `runtime/ollama/` and `runtime/whisper/` to avoid large downloads

Use encrypted storage for secrets and private human recordings. Verify file permissions after restoring them.

## Safe to download again

- Public Ollama models such as `gemma3:12b`
- Public faster-whisper models such as `large-v3-turbo`
- Python packages from `requirements.txt`
- Ollama itself from its official installer

Git contains source, tests, documentation, configuration templates, runtime orchestration scripts, and non-sensitive dataset metadata templates.
