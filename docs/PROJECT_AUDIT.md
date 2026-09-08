# Project portability audit

No files were deleted during this audit.

## COMMIT

- `app/*.py`: application source and tests
- `app/.env.example` and `app/model_profiles.json`: safe configuration templates/metadata
- `scripts/`: generation, verification, setup, runtime, and maintenance scripts
- `docs/`, `README.md`, `requirements.txt`, `setup.sh`
- `dataset/RECORDING_GUIDE.md` and `dataset/metadata/*.csv`: non-sensitive recording templates and metadata
- `.gitignore`

## DO_NOT_COMMIT

- `secrets/` and `app/.env`
- `runtime/`: Ollama binaries/libraries/models/logs and Whisper models
- `app/output/`, `output/`, `reference/`, and `voice_auditions/`
- `dataset/raw/`, `dataset/processed/`, and `dataset/synthetic_google_leda/`
- WAV/MP3/M4A/FLAC files, caches, bytecode, logs, and temporary files

## OPTIONAL (private backup, not Git)

- Generated audition and application audio
- Reference recordings
- Synthetic datasets
- Public model caches, which may be copied to reduce restoration time or downloaded again
