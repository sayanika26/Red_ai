# Prithi Voice AI

## 1. What this project is

Prithi is a multilingual Bengali/Hindi/English conversational voice prototype. A configurable OpenAI-compatible LLM produces structured replies and emotional delivery metadata; Google TTS produces speech; faster-whisper provides local file transcription.

## 2. Architecture

`User text → Prithi Brain → OpenAI-compatible LLM → validated reply/emotion/style → Prithi TTS → WAV`

STT is currently a separate reusable file-transcription module and is not connected to live chat or a microphone.

## 3. Requirements

Use Linux, Python 3.10+, FFmpeg, persistent disk, and preferably an NVIDIA GPU. The tested GPU is NVIDIA L4. See `docs/SYSTEM_REQUIREMENTS.md`.

## 4. Fresh installation

```bash
git clone <repo>
cd prithi-voice
./setup.sh
./scripts/bootstrap_models.sh
./scripts/start_prithi_runtime.sh
./scripts/verify_environment.sh
```

Large models are not downloaded by `setup.sh`. Model downloads are isolated in `bootstrap_models.sh`.

## 5. Restore on a new Lightning Studio

Clone into `~/prithi-voice`, run the commands above, then restore private credentials separately. To enable user-level automatic runtime startup:

```bash
mkdir -p ~/.lightning_studio
cp scripts/lightning_on_start_example.sh ~/.lightning_studio/on_start.sh
chmod +x ~/.lightning_studio/on_start.sh
```

Review an existing `on_start.sh` before replacing it; append the command instead if it already has custom actions.

## 6. Setup Google TTS credentials

Place the private JSON at `secrets/google-tts.json`, set permission `600`, and export its path:

```bash
chmod 600 secrets/google-tts.json
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/secrets/google-tts.json"
```

Copy `app/.env.example` to `app/.env` and adjust only local/provider values. Both secrets and `.env` are ignored by Git.

## 7. Start runtime

```bash
./scripts/start_prithi_runtime.sh
```

## 8. Check runtime status

```bash
./scripts/status_prithi_runtime.sh
```

Stop only the project-managed Ollama process with `./scripts/stop_prithi_runtime.sh`.

## 9. Launch Prithi text chat

```bash
source ~/.virtualenvs/prithi-voice/bin/activate
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/secrets/google-tts.json"
python app/prithi_chat.py
```

Commands: `/debug`, `/reset`, `/quit`, `/exit`.

## 10. Run tests

```bash
python app/test_prithi_brain.py
python app/test_llm_provider.py
python app/test_prithi_stt.py
```

## 11. Switch Ollama model

```bash
OLLAMA_MODELS="$PWD/runtime/ollama/models" runtime/ollama/bin/ollama pull NEW_MODEL
```

Then set `PRITHI_LLM_MODEL=NEW_MODEL` in `app/.env`. No application rewrite is needed.

## 12. Where large models are stored

- Ollama: `runtime/ollama/models/`
- Whisper: `runtime/whisper/models/`

These paths are persistent locally and ignored by Git.

## 13. What is not stored in Git

Credentials, `.env`, models/runtime state, private or generated audio, raw/processed/synthetic datasets, caches, logs, and temporary files are excluded. See `docs/BACKUP_MANIFEST.md`.

## 14. Troubleshooting

- Connection refused on port 11434: run `./scripts/start_prithi_runtime.sh`.
- Missing model: run `./scripts/bootstrap_models.sh`.
- TTS credential error: verify `GOOGLE_APPLICATION_CREDENTIALS` points to an existing JSON file.
- CUDA STT error: run `./scripts/verify_environment.sh` and confirm the NVIDIA driver and CUDA libraries.
- Browser on another computer cannot use the server's `127.0.0.1`; use an SSH tunnel rather than exposing Ollama publicly.

## 15. Backup/restore checklist

1. Push committed source and metadata to a private repository.
2. Back up secrets, private datasets, trained checkpoints, and databases using encrypted storage.
3. Optionally archive `runtime/` to avoid downloading public models again.
4. On restore, clone, run setup/bootstrap, restore credentials, verify permissions, and run the environment verifier.
