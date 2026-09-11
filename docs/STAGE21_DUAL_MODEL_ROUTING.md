# Stage 21 — Dual-model routing

Date: 2026-09-10

## Production routing

| Conversation mode | Exact Ollama model | Activation rule |
|---|---|---|
| Normal | `gemma3:12b` | Default for every user and new session |
| Adult | `richardyoung/qwen3-14b-abliterated:Q4_K_M` | Only after persisted 18+ confirmation **and** a separate opt-in in the current browser session |

`PRITHI_LLM_MODEL=gemma3:12b` remains the legacy/default configuration. The router reads `PRITHI_LLM_NORMAL_MODEL` and `PRITHI_LLM_ADULT_MODEL`, while all model decisions remain server-side.

## State model

- `off`: no age confirmation; Gemma is authoritative.
- `available`: the user previously confirmed 18+, but adult mode is not enabled in this session; Gemma remains authoritative.
- `enabled`: age confirmation and current-session opt-in are both true; Qwen is selected for eligible turns.

Only the boolean age confirmation is stored in the existing per-user SQLite profile. Adult opt-in is held in the in-memory browser session and is cleared by session expiry, application restart, explicit disable, full memory deletion, or a safety exit. Flirting, affection, loneliness, nighttime language, or relationship state never turns adult mode on.

The browser presents age confirmation and adult-mode activation as two distinct actions. It always shows the current mode and selected model and provides a one-click return to normal mode.

## Routing and safety

`app/prithi_model_router.py` owns model selection, model availability, transition serialization, and Ollama unloading. On a model transition, any other Prithi candidate resident in Ollama is unloaded before the target request. This avoids intentionally loading Gemma and Qwen together.

The following behavior is backend-authoritative:

- “Stop”, “normal mode”, and language-equivalent commands route the current reply through Gemma and disable adult mode immediately.
- “No”, “not now”, “change topic”, “uncomfortable”, and “slow down” de-escalate the current turn to normal behavior.
- Prohibited adult contexts involving minors or ambiguous age, non-consent, incest, coercion, or exploitation are routed to the safety response path.
- Adult mode permits stronger consensual romantic, sensual, suggestive, and mature conversation without automatic sexual escalation.
- The production JSON contract remains `reply`, `language`, `emotion`, and `voice_style`. Stage 16 relationship state is application-managed; there is no active `relationship_delta` field in the production LLM schema, so none was invented in Stage 21.

## Memory and relationship continuity

The same browser identity, in-memory conversation history, persistent user profile, and relationship state are shared across model changes. Switching models does not reset history. Relationship updates continue through the existing bounded increments.

Explicit adult conversation details, sexual preferences, and sensitive intimate content are excluded from persistent memory. Adult-mode turns can still update the established gradual relationship metrics, but their transcript is not extracted into saved memory items.

## Provider compatibility

Gemma continues through the existing OpenAI-compatible Ollama interface. Qwen uses Ollama's native chat request with JSON mode and `think=false`; this prevents reasoning tokens from exhausting Prithi's concise 160-token response budget and returning an empty content field. No external or paid LLM API is involved.

## Live model-switch validation

The fixed live sequence was normal Gemma → adult Qwen → normal Gemma. No STT or paid TTS was used for this routing validation.

| Turn | Mode/model | Emotion | Switch + response | Ollama model VRAM | Total GPU memory |
|---|---|---:|---:|---:|---:|
| Normal | `gemma3:12b` | warm | 7.68 s | 8.04 GB | 14,998 MiB / 23,034 MiB |
| Adult opt-in | `richardyoung/qwen3-14b-abliterated:Q4_K_M` | flirtatious | 8.56 s | 9.37 GB | 15,184 MiB / 23,034 MiB |
| Stop / normal | `gemma3:12b` | warm | 7.75 s | 8.04 GB | 14,998 MiB / 23,034 MiB |

Ollama `/api/ps` showed exactly one Prithi LLM loaded after each turn. No OOM occurred. The earlier Stage 20 warm medians remain representative: Gemma 3.28 s and Qwen 6.07 s. Switching costs roughly 7.7–8.6 seconds on this L4 because the target model must be loaded from persistent storage; ordinary same-mode turns avoid that load.

The live authenticated mode API passed `off → available → enabled → available`, selecting Gemma → Gemma → Qwen → Gemma. The page was visually verified on the Lightning port-8000 URL with the adult action hidden until age confirmation.

A final authenticated Bengali audio-file turn exercised the unchanged production path after routing was deployed: STT 1.25 s, warm Gemma reply 3.47 s, Google TTS 4.04 s, total 8.91 s, no fallback, and `gemma3:12b` remained the only loaded Ollama model. This was not represented as a browser-microphone test; physical microphone acceptance remains a user action.

## Tests and security review

- Full regression suite: 165 passed, 0 failed.
- New coverage includes default routing, both-gate enforcement, no inference from flirting, de-escalation, explicit exit, prohibited contexts, model unloading, mode states, legacy configuration, relationship/history preservation, memory filtering, age persistence, API authentication, session isolation, restart reset, delete behavior, and separate browser controls.
- Web access-token authentication remains required for every mode endpoint.
- The backend, not JavaScript, chooses the model.
- The browser never receives an API key, Google credential, system prompt, local path, or hidden backend error.
- Mode state is scoped by both authenticated browser identity and secure session cookie.
- Existing STT, TTS routing, audio handling, and database architecture were not replaced.

## Operations

The normal production default remains:

```text
PRITHI_LLM_MODEL=gemma3:12b
PRITHI_LLM_NORMAL_MODEL=gemma3:12b
PRITHI_LLM_ADULT_MODEL=richardyoung/qwen3-14b-abliterated:Q4_K_M
```

Start or recover the existing service with:

```bash
cd ~/prithi-voice && ./scripts/start_prithi_all.sh
```

The live health endpoint returned HTTP 200 with Ollama, STT, and TTS configuration healthy. The manual speech-content acceptance pass still requires the user's own browser microphone; it does not affect the completed backend routing and automated safety validation.

## Final status

**STAGE 21 STATUS: COMPLETE**
