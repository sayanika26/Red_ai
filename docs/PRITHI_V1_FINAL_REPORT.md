# Prithi v1 Final Report

**Version:** 1.0.0  
**Validation date:** 2026-09-10  
**Project:** `~/prithi-voice` on Lightning Studio  
**Release status:** **BLOCKED pending the manual browser acceptance and source-control publication listed below.**

## 1. Architecture

```text
Browser microphone
  -> temporary upload and PCM conversion
  -> faster-whisper on NVIDIA L4
  -> Prithi Brain
  -> local Ollama gemma3:12b
  -> strict reply/language/emotion/style validation
  -> Google Chirp or Gemini TTS (Leda)
  -> short-lived audio URL
  -> browser playback
```

Conversation history is per browser session and limited to eight complete exchanges in RAM. Stable approved memories and relationship state are stored separately in SQLite.

## 2. Models and providers

- Local LLM: Ollama with `gemma3:12b`, using `http://127.0.0.1:11434/v1`.
- Bengali STT: faster-whisper `large-v3`, forced `bn`, GPU `float16`.
- Other/backup STT: faster-whisper `large-v3-turbo`.
- Neutral TTS: Google Chirp 3 HD Leda (`bn-IN`, `hi-IN`, `en-IN`).
- Expressive TTS: Google Gemini TTS Leda for supported emotion/locale combinations; Bengali expressive mode uses `bn-BD`.
- Python: 3.10.20.
- FastAPI: 0.141.1; Uvicorn: 0.52.4.
- faster-whisper: 1.2.1; CTranslate2: 4.8.2.
- Google Cloud Text-to-Speech client: 2.37.0.

## 3. Languages and conversational behavior

Supported browser selections are Bengali, Hindi, English, and automatic STT detection. Bengali mode deliberately forces Whisper language `bn` and the Brain reply language to Bengali, while allowing moderate English code-switching. The Brain supports neutral, warm, caring, playful, affectionate, intimate, flirtatious, attraction, pleasure, and aroused routing with validated voice-style values.

The five-turn live LLM validation followed the intended emotional route:

`warm -> caring -> playful -> affectionate -> flirtatious`

It produced Bengali replies, no duplicate responses, and no repeated counselor phrase. However, four of five replies in the first run and five of five in the repeat contained questions. One first-run reply also contained a stray non-Bengali token. A strict experimental runtime rejection was tested and then removed because it could fail an otherwise valid Brain turn when the local model repeated the behavior on its one retry. No personality redesign was retained.

## 4. Memory design

- Browser JavaScript keeps an opaque, high-entropy stable identity in local storage and sends it as `X-Prithi-User`.
- The server stores only a SHA-256 digest of that identity.
- SQLite holds profile fields, bounded relationship metrics, and conservative stable-memory candidates.
- Secrets, raw microphone recordings, access tokens, and entire transcripts are not used as identity data.
- The database is `runtime/prithi_memory/prithi_memory.db`, with private directory/file permissions.
- User-scoped reset and delete operations do not affect other identities.

Final restart validation seeded a harmless user with three preferences and relationship state, verified them through the authenticated web API, restarted both Ollama and the web process, verified them again, verified a second identity saw zero memories and no relationship, and removed the test data. Result: **PASS**.

## 5. Browser voice validation

Four real STT -> Brain -> TTS requests were run through the authenticated FastAPI voice endpoint using existing audition WAVs. Each response audio URL returned a valid non-empty WAV.

| Case | Transcript | Reply language / emotion | STT | LLM | TTS | Total | Audio |
|---|---|---:|---:|---:|---:|---:|---:|
| Bengali | হালো আজকে তুমার দিনটা কেমন গালো? এক্টু আমার সাথে গল্পো করবে? | Bengali / warm | 1.94s | 8.44s | 5.69s | 18.72s | 9.77s, valid |
| Banglish | আজকে ঵োক কেমন ছিলো? খুব বিজি ছিলে না কি? টেল মি ঵াট হাপন্ড? | Bengali / neutral | 1.61s | 3.44s | 0.91s | 6.09s | 4.15s, valid |
| Hindi | आज तुम्हारा दिन कैसा रहा? थोड़ा मेरे साथ बात करोगे? | Hindi / warm | 0.34s | 3.24s | 4.14s | 8.90s | 5.61s, valid |
| English | Hey, tell me how your day went. I would really like to hear about it. | English / neutral | 0.26s | 3.13s | 0.70s | 4.23s | 2.66s, valid |

Median across these four requests: STT **0.97s**, LLM **3.34s**, TTS **2.52s**, total **7.49s**. The first Bengali request included cold-model cost and was slower. Expressive Gemini synthesis was slower than neutral Chirp synthesis.

Bengali and Banglish stayed Bengali-dominant and did not switch to Hindi. The Banglish English words were phonetically transcribed into Bengali script rather than preserved in Latin script, so code-switch fidelity is only partial.

This automated validation proves server-side audio acceptance, STT, language routing, LLM generation, TTS synthesis, safe audio retrieval, and valid WAV output. It cannot prove a fresh local microphone permission flow or audible playback on the user's device. Those browser checks remain pending.

## 6. Persistence and restart recovery

- Ollama models: `runtime/ollama/models/`
- Whisper models: `runtime/whisper/models/`
- Ollama logs: `runtime/ollama/logs/`
- SQLite memory: `runtime/prithi_memory/prithi_memory.db`
- Short-lived web audio: `runtime/web/audio/`
- Private configuration: `app/.env`
- Google service-account file: `secrets/google-tts.json`
- Private backups: `~/prithi-backups/`

A controlled stop/start of Prithi-managed web and Ollama processes passed. `gemma3:12b`, `large-v3`, and `large-v3-turbo` were reused from persistent storage. No model was re-downloaded. The web service returned healthy with version `1.0.0` afterward.

## 7. Backup and restore

`scripts/backup_prithi.sh` uses SQLite's online backup API and integrity-checks the output. It stores the database plus safe templates and an optional custom-model reference manifest. It intentionally excludes `app/.env`, Google credentials, audio, and model weights.

`scripts/restore_prithi.sh` validates the source and restored SQLite databases, preserves the previous database as `prithi_memory.db.pre-restore`, restores mode `0600`, and requires a web restart afterward.

An isolated round-trip preserved logical table counts and contained no `.env`, Google credential, WAV, or model weight. Result: **PASS**.

## 8. Security summary

- Required Git ignore checks passed for `app/.env`, `secrets/google-tts.json`, runtime databases, generated audio, private reference recordings, model caches, and backup directories.
- The repository secret scan passed without printing credential contents.
- Access-token comparison uses a constant-time comparison.
- Tokens and credentials are not embedded in frontend source or health output.
- Upload filenames are not trusted, upload type/size/duration is bounded, and source microphone audio is temporary.
- Generated audio is retrieved through safe identifiers rather than arbitrary paths; traversal tests pass.
- A new regression test confirms unexpected server exceptions return only `{"detail":"Internal Prithi service error"}` and expose neither a stack trace nor private exception text.
- Memory is identity-scoped, and the database stores the identity digest rather than the raw browser identifier.

## 9. Tests and final validation

- Unit/integration suite: **134 passed, 0 failed**.
- Shell syntax validation for setup/runtime/backup scripts: **PASS**.
- `git diff --check`: **PASS**.
- Ollama healthy: **yes**.
- Configured LLM present: **gemma3:12b, yes**.
- Whisper `large-v3` present: **yes**.
- NVIDIA GPU: **NVIDIA L4, available**.
- STT GPU readiness: **yes**.
- FastAPI web process: **running and healthy on port 8000**.
- SQLite memory: **available and integrity checked**.
- Google TTS credential configuration: **present** (contents not read or printed by reporting tools).
- Secret scan: **PASS**.
- Backup/restore: **PASS**.
- Memory restart restoration: **PASS**.
- User isolation: **PASS**.
- Empty STT blocked before Brain: **PASS**.
- Wrong-language Brain output corrected once or safely rejected: **PASS**.
- TTS failure retains text reply: **PASS**.
- Missing/invalid auth rejected: **PASS**.
- Stack traces hidden: **PASS**.

Non-fatal dependency warnings:

- Google client libraries warn that Python 3.10 reaches upstream end of life on 2026-10-04; plan a controlled Python upgrade after v1 stabilization, not during this finalization.
- FastAPI's test client reports a Starlette deprecation warning concerning the current `httpx` integration.

## 10. Commands

Start everything:

```bash
cd ~/prithi-voice && ./scripts/start_prithi_all.sh
```

Stop only Prithi-managed services:

```bash
cd ~/prithi-voice && ./scripts/stop_prithi_all.sh
```

Check status:

```bash
cd ~/prithi-voice && ./scripts/status_prithi_runtime.sh
```

Back up private persistent memory:

```bash
cd ~/prithi-voice && ./scripts/backup_prithi.sh
```

Restore a selected backup and restart:

```bash
cd ~/prithi-voice
./scripts/restore_prithi.sh ~/prithi-backups/PRITHI_BACKUP_DIRECTORY
./scripts/stop_prithi_all.sh
./scripts/start_prithi_all.sh
```

## 11. Fresh Studio restoration

The documented path is:

```bash
git clone https://github.com/sayanika26/Red_ai.git prithi-voice
cd prithi-voice
./setup.sh
./scripts/bootstrap_models.sh
# Add secrets/google-tts.json privately and configure app/.env.
./scripts/start_prithi_all.sh
```

The scripts are ready, but the current Lightning worktree contains modified and untracked v1 files that have not been committed or pushed. Therefore a fresh clone of the current GitHub branch will not yet reproduce this validated state.

## 12. Known limitations

- Bengali STT is not perfect; short, quiet, or code-switched speech can be misspelled.
- Banglish English words may be rendered phonetically in Bengali script rather than preserved in Latin script.
- Expressive Gemini TTS remains the primary latency bottleneck.
- The first turn after a process/model restart can be much slower than warm turns.
- Gemma 3 may remain conservative in some adult/flirty contexts and may ask questions too often despite prompt guidance.
- Gemini Bengali expressive speech uses `bn-BD`, while the desired character direction is Indian Bengali.
- This is Prithi v1, not a fine-tuned custom Prithi foundation model.
- Server-side tests cannot verify local browser microphone permission or audible client playback.

## 13. Remaining blockers

1. In a fresh browser session, manually complete one Bengali, one Banglish, one Hindi, and one English microphone turn and confirm the returned audio plays audibly. The automated endpoint/WAV checks pass, but they do not substitute for device-side acceptance.
2. Review and publish the current v1 source changes to the configured Git remote. Until they are committed and pushed, the documented fresh-clone recovery path cannot reproduce this exact build.
3. Accept or address the qualitative five-turn finding that Gemma asks a question in most replies. Emotion continuity, language, non-repetition, and counselor-phrase checks pass, but the requested question-frequency gate does not yet pass consistently.

## Final status

**PRITHI V1 STATUS: BLOCKED**

The runtime itself is healthy and all automated safety, persistence, backup, restart, multilingual pipeline, and regression tests pass. The status remains blocked only because the specified manual browser acceptance, reproducible Git publication, and qualitative question-frequency acceptance are not complete.
