# Lightning Code Sync Report

Verification that the Lightning Studio holds the authoritative, fully updated Prithi codebase.

**Headline finding:** no code needed to be copied. The Windows mirror is a strict *subset* of the
Lightning project and every shared file is byte-identical, so Lightning was already authoritative.
Zero files were overwritten, zero deleted, nothing committed or pushed.

Date: 2026-09-14 · Sync direction: verification only (Windows → Lightning transfers: 0 source files)

---

## 1. Live project

| Item | Value |
| --- | --- |
| Live Lightning path | `/teamspace/studios/this_studio/prithi-voice` (= `~/prithi-voice`) |
| Windows mirror | `D:\SS\prithi-voice` |
| Branch | `main` |
| HEAD | `58bff4c` — Document Prithi v3 real-user evaluation |
| Remote | `origin  https://github.com/sayanika26/Red_ai.git` |
| VERSION | `1.0.0` |

Confirmed as the process serving port 8000:

```
uvicorn prithi_web:app --app-dir /teamspace/studios/this_studio/prithi-voice/app \
        --host 0.0.0.0 --port 8000 --no-access-log
cwd -> /teamspace/studios/this_studio/prithi-voice
```

---

## 2. Comparison result

159 files compared on Lightning, 151 on the Windows mirror (excluding `.git`, `__pycache__`,
`runtime/`, `secrets/`, `*.db`, `.env`, generated audio, models and eval results).

| Bucket | Count | Detail |
| --- | --- | --- |
| IDENTICAL | 151 | every file present on both sides, matching MD5 |
| DIFFERENT | **0** | — |
| LOCAL_ONLY (Windows) | **0** | — |
| LIGHTNING_ONLY | 8 | listed below — preserved untouched |

Because DIFFERENT and LOCAL_ONLY are both empty, no merge decision was required and no Lightning
file was at risk of being overwritten by an older mirror copy.

### LIGHTNING_ONLY — preserved, never touched

```
./.gitignore
./bootstrap_prithi_studio.sh
./install_prithi.sh
./setup.sh
./requirements-training.txt
./dataset/RECORDING_GUIDE.md
./dataset/metadata/google_leda_generation_v1.csv
./dataset/metadata/recording_script_v1.csv
```

---

## 3. Files synced / merged

| Category | Count | Files |
| --- | --- | --- |
| Source files copied Windows → Lightning | **0** | none required |
| Files merged | **0** | no divergence existed |
| Docs corrected on Lightning | 1 | `docs/PRITHI_V32_SEARCH_INTELLIGENCE.md` |
| New files written | 1 | `docs/LIGHTNING_SYNC_REPORT.md` (this file) |

The v3.2 document was corrected because it claimed the `searching` / `reading` UI states were
"backend-only, not yet rendered". The UI session has since wired them (`app/web/app.js:819-823`), so
that limitation was replaced with the accurate one: the states surface on the streaming voice route,
while `/api/text-turn` is single request/response and shows no interim status.

### Checksum verification

| File | Lightning | Windows | Result |
| --- | --- | --- | --- |
| `docs/PRITHI_V32_SEARCH_INTELLIGENCE.md` | `071cb1f548b9b4038cc775d0d93725dc` | `071cb1f548b9b4038cc775d0d93725dc` | MATCH |

All 151 shared files were verified by MD5 across both sides before any action was taken.

---

## 4. Intentionally not copied (Lightning-local)

Excluded from comparison and never written, as required:

```
app/.env                     secrets/google-tts.json
secrets/                     runtime/              (ollama, whisper, web, memory)
*.db / *.sqlite*             runtime/prithi_memory/prithi_memory.db (90 KB)
model caches                 runtime/ollama/models
Whisper models               runtime/whisper/models
generated audio              app/output/
training checkpoints         evals/results/
```

---

## 5. Code verification on Lightning

### v3.2 search intelligence — present

| File | Size | Modified |
| --- | --- | --- |
| `app/prithi_search.py` | 8597 | 07:51 |
| `app/prithi_retrieval.py` | 9148 | 07:54 |
| `app/test_prithi_retrieval.py` | 5028 | 07:54 |
| `app/test_prithi_search_integration.py` | 10374 | 07:56 |
| `docs/PRITHI_V32_SEARCH_INTELLIGENCE.md` | — | 08:1x (corrected) |

Router integration lives in `app/prithi_web.py` (retrieval on both `/api/text-turn` and
`/api/voice-turn-stream`, per-session pending-clarification state, `searching` / `reading` events).

### v3.1 modules — intact

`prithi_context.py`, `prithi_mood.py`, `prithi_strategy.py`, `prithi_roleplay.py`,
`prithi_learning.py`, `prithi_memory.py`, `prithi_brain.py`, `prithi_followup.py` — all present and
unmodified by this sync.

### UI — current work preserved

`app/web/index.html` (17491 B, 07:33), `app/web/styles.css` (49311 B, 07:31),
`app/web/app.js` (50368 B, 07:31) — newer than the v3.1 baseline and **not** replaced.

Feature check: glassmorphism (`backdrop-filter` ×6), animated orb (46 CSS rules + JS),
brain visuals, text chat (`#text-message` textarea → `/api/text-turn`), voice controls,
mobile layout (10 `@media` blocks), adult controls (55 refs), memory controls (58 refs),
and the new SEARCHING / READING states.

---

## 6. Live validation

| Check | Result |
| --- | --- |
| Test suite | **258 tests, OK** (`python -m unittest discover -s app -p "test_*.py"`) |
| `pytest` | not installed in the venv — `unittest` is this project's documented runner (README line 95) |
| `/api/health` | `HTTP 200` — `{"status":"ok","version":"1.0.0","ollama":true,"stt":true,"tts_configured":true}` |
| Frontend `/` | `HTTP 200`, 17491 bytes |
| Ollama | healthy on 11434 — `gemma3:12b` + `richardyoung/qwen3-14b-abliterated:Q4_K_M` both present |
| STT | `stt: true`; GPU NVIDIA L4 detected |
| TTS | `secrets/google-tts.json` present (2365 B), `tts_configured: true` |
| SQLite | `integrity_check: ok`; tables `profiles`, `memory_items`, `relationships`, `mood_states`, `learned_behaviors`, `retrieval_cache` |

`retrieval_cache` sitting beside `memory_items` confirms v3.2 keeps searched facts out of personal
memory.

---

## 7. Running service uses updated code

A stale process was found and replaced.

| | Before | After |
| --- | --- | --- |
| PID | 18778 | 25557 |
| Started | 07:33:33 | **08:10:43** |
| Newest v3.2 source | 07:54:32 | 07:54:32 |
| Verdict | **stale** — predated v3.2 by 21 min | **current** — started after every source file |

The old process served the current UI (static files are read per request) against a pre-v3.2 backend,
so `app.js` was listening for `searching` / `reading` events the running backend could never emit.

Restart was done with the project's own scripts and the scripts' own safety rules:

1. Verified PID 18778's cmdline contained `prithi_web:app` before sending `TERM`.
2. Confirmed clean exit, port 8000 free, no respawn.
3. Removed a stale PID file (`runtime/web/prithi_web.pid` recorded 11157, not running).
4. Ran `./scripts/start_prithi_all.sh`, which reuses an already-running Ollama rather than restarting it.

Ollama PID 14011 was untouched throughout. No unrelated process was signalled.

Post-restart verification:

- cwd → `/teamspace/studios/this_studio/prithi-voice`; `--app-dir` → the same project's `app/`
- interpreter → `.virtualenvs/prithi-voice/bin/python` (CPython 3.10.20)
- process start time is later than every source file's mtime, and the bytecode cache matches current sources
- served assets equal on-disk files byte-for-byte:

```
MATCH  /           == app/web/index.html
MATCH  /app.js     == app/web/app.js
MATCH  /styles.css == app/web/styles.css
```

---

## 8. Git status (nothing committed or pushed)

HEAD remains `58bff4c`. The working tree carries v3.1, v3.2 and the UI redesign as uncommitted work,
by instruction — a concurrent session is still editing the UI.

**Modified (20):** `app/.env.example`, `app/app.env.example`, `app/prithi_brain.py`,
`app/prithi_context.py`, `app/prithi_learning.py`, `app/prithi_memory.py`, `app/prithi_roleplay.py`,
`app/prithi_strategy.py`, `app/prithi_transcript_quality.py`, `app/prithi_voice_chat.py`,
`app/prithi_web.py`, `app/test_prithi_adaptive.py`, `app/test_prithi_behavior.py`,
`app/test_prithi_brain.py`, `app/test_prithi_memory.py`, `app/test_prithi_quality.py`,
`app/test_prithi_web.py`, `app/web/app.js`, `app/web/index.html`, `app/web/styles.css`

**Untracked (12):** `docs/LIGHTNING_SYNC_REPORT.md` (this file),
`app/prithi_followup.py`, `app/prithi_retrieval.py`, `app/prithi_search.py`,
`app/test_prithi_followup.py`, `app/test_prithi_retrieval.py`,
`app/test_prithi_search_integration.py`, `docs/PRITHI_UI_GLASSMORPHIC_REDESIGN.md`,
`docs/PRITHI_V31_FIX_REPORT.md`, `docs/PRITHI_V32_SEARCH_INTELLIGENCE.md`,
`evals/prithi_v31_retest.py`, `evals/results/prithi_v31_retest.json`

`git diff --stat`: 20 files changed, 1384 insertions(+), 75 deletions(-)

**Does the repo match the running code?** The *working tree* does — the running service was restarted
from it and verified above. The *committed* tree does not: every v3.1, v3.2 and UI change is still
uncommitted. Committing is deliberately left for you to trigger once the UI session settles.

---

## 9. What was not done

No training started. No commit, push, reset, clean or force operation. Nothing deleted from
Lightning. No `.env`, secret, database, model or runtime artefact copied from Windows.
