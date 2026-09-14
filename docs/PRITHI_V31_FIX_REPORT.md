# Prithi v3.1 fix report

Date: 2026-09-14. No model was trained, no LoRA work was started, and the normal/adult production routing architecture was not changed.

## Result

- Overall score: **4.2/5** (v3: 3.6/5).
- Automated regression: **240 passed, 0 failed** (v3 report: 201 passed).
- Acceptance retest: **35/35 live LLM turns** returned valid structured replies, used the requested script, and followed the expected normal/adult route.
- Full audio recovery turn: the known corrupted Bengali transcript was stopped after STT with a repeat request; the brain and TTS were not called.
- Remaining severity: **P0: 0, P1: 0, P2: 5**.

## Original P1/P2 fixes

| Priority | Original issue | Fix applied | Main files | Result |
|---|---|---|---|---|
| P1 | Bengali STT semantic corruption reached the brain | Added acoustic/semantic confidence scoring, prior-turn continuity checks, decoder-hallucination detection, and conservative কাজ/কাছ plus সারাদিন/শারা দিন confusion signatures. Forced Bengali routing is unchanged. | `app/prithi_transcript_quality.py`, `app/prithi_voice_chat.py`, `app/prithi_web.py` | Known v3 audio now returns the repeat message with HTTP 422 and makes no LLM/TTS call. Context change with strong acoustic confidence remains allowed. |
| P1 | Typed preferences collapsed or skipped adaptive learning | Typed and voice paths now share adaptive preparation/finalization. Added typed extractors for Banglish, teasing intensity, support style, affectionate mirroring, and meta-feedback targeting. | `app/prithi_learning.py`, `app/prithi_web.py` | Five distinct learned types persisted: `language_style`, `teasing_intensity`, `support_style`, `affection_style`, and `response_preference`. |
| P1 | Nickname was not persistent | Added explicit bounded Bengali/Hindi/English nickname extraction and rejected interrogative/unsafe name candidates. | `app/prithi_memory.py`, `app/prithi_web.py` | `রিক` survived rolling-history reset and app/store reopen; the recall question no longer overwrites it. User B remained empty. |
| P1 | Allowed adult opt-in response was vague | Added concrete fulfillment guidance, first-person action/sensory targets, unnecessary-deflection validation, and a third repair attempt only after two invalid outputs. Consent, prohibited-content routing, and Stop/not-now behavior remain authoritative. | `app/prithi_brain.py`, `app/prithi_strategy.py` | Allowed adult turns produced concrete non-explicit reciprocation; Stop/not-now returned immediately to normal routing. Some phrasing remains a P2 quality limitation. |
| P1 | Learned behavior retrieval was too broad | Added a minimum weighted relevance threshold using semantic tag overlap, language, mode, relationship/roleplay tags, recency, confidence, and feedback counts; added type deduplication and strict romantic-context compatibility. | `app/prithi_learning.py`, `app/prithi_web.py` | Irrelevant and mode-mismatched behaviors inject none. Romantic/sensual behavior did not enter unrelated or other-user turns. Global language style is the intentional same-language exception. |
| P2 | Replies contained two questions | Added deterministic validation at a maximum of one `?`/`？`, with repair retry. | `app/prithi_brain.py` | Acceptance maximum: **1**. No two-question reply occurred (v3 had at least four). |
| P2 | Humor requests were not fulfilled | Added `tell_joke` intent, `humorous_answer` strategy, complete-joke instructions, and commentary/deflection validation. | `app/prithi_context.py`, `app/prithi_strategy.py`, `app/prithi_brain.py` | Bengali and Hindi live turns both delivered a setup and punchline. |
| P2 | Roleplay repeated generic questions and failed to progress | Track compact user and assistant events, last question, scene summary, and anti-repeat/progression guidance. Reset now clears fictional rolling history while preserving real relationship state. | `app/prithi_roleplay.py`, `app/prithi_web.py` | Café turns progressed through new scene details; pause/resume worked; reset removed café context. |
| P2 | Prithi claimed rejected sensitive content was remembered | Storage disposition is supplied before generation and validated; sensitive remember requests must explicitly say they cannot be saved/remembered. | `app/prithi_memory.py`, `app/prithi_web.py`, `app/prithi_brain.py` | No memory row was written; targeted live reply explicitly rejected remembering the credential. |
| P2 | Mode switches were slow | Preserved safe one-model-at-a-time L4 residency and added an observable `switching_mode` UI state. No unsafe dual residency/prefetch was introduced. | `app/prithi_web.py`, `app/web/app.js`, `app/web/styles.css` | Transition turns remained about 11–15 seconds, comparable to v3. This remains P2. |

## Retrieval and follow-up scope (sections 11–21)

- Added `local`, `clarify`, `search`, `research_again`, and `unknown` knowledge actions.
- Ambiguous office questions request one clarification; wrong U.S. Prime Minister terminology is corrected before searching.
- Fresh/current, explicit-search, and explicit-verification prompts search; personal conversation and stable questions remain local.
- Search ranks official/primary sources first, retries weak/conflicting evidence, and instructs honest uncertainty when verification fails.
- Query, timestamp, source title/URL, confidence, and compact evidence are stored in a separate TTL cache, never personal memory.
- Streaming UI exposes SEARCHING, READING, THINKING, ANSWERING, and model-switch states while retaining Bengali/Hindi/English status tone.
- Configurable silence follow-up sends at most one gentle message and is cancelled by user activity.

Main files: `app/prithi_retrieval.py`, `app/prithi_search.py`, `app/prithi_followup.py`, `app/prithi_web.py`, `app/web/app.js`, `app/web/styles.css`, and both environment examples.

## Tests

The final automated suite contains 240 tests and covers Bengali semantic recovery, typed nickname and preference persistence, restart persistence, text/voice identity sharing, duplicate prevention, user isolation, behavior thresholding, romantic non-leakage, allowed adult fulfillment, Stop/de-escalation, one-question maximum, humor, roleplay reset/progression, sensitive-memory truthfulness, retrieval classification/retry/conflicts/TTL separation, and one-shot silence follow-up.

The reproducible live runner is `evals/prithi_v31_retest.py`; raw acceptance output is `evals/results/prithi_v31_retest.json`. It uses a temporary SQLite database and does not seed production memory.

## v3 versus v3.1 score

| Area | v3 | v3.1 | Result |
|---|---:|---:|---|
| Naturalness | 3.6 | 4.1 | More direct; no multi-question replies, though questions remain common. |
| Bengali | 3.8 | 4.2 | Correct script and safe semantic recovery; a few awkward phrases remain. |
| Banglish | 3.2 | 3.8 | Typed preference is retained and selectively injected; consistency can improve. |
| Cleverness | 3.8 | 4.3 | Logic/direct answers remained correct. |
| Humor | 2.8 | 4.2 | Both tested languages produced complete jokes. |
| Empathy | 3.8 | 4.2 | Specific, concise support without interrogation. |
| Affection | 3.8 | 4.2 | Warm mirroring without unrelated adult leakage. |
| Romance | 3.3 | 3.9 | More responsive but occasionally generic. |
| Adult-mode quality | 2.4 | 3.7 | Allowed requests are fulfilled non-explicitly; Bengali wording is still uneven. |
| Consent/de-escalation | 4.8 | 5.0 | Stop/not-now remained immediate and authoritative. |
| Memory | 3.0 | 4.8 | Nickname/profile persistence, restart, deduplication, and isolation passed. |
| Continual learning | 2.5 | 4.7 | Five typed preference types persist and retrieve selectively. |
| Mood realism | 3.5 | 3.7 | Existing bounded behavior preserved; signal granularity is unchanged. |
| Roleplay continuity | 3.5 | 4.1 | Both sides are tracked and reset removes fictional context. |
| User isolation | 4.8 | 5.0 | No memory, mood, roleplay, adult opt-in, or behavior leakage. |
| Voice experience | 3.4 | 4.4 | Corrupted Bengali is stopped safely instead of producing an irrelevant reply. |
| Latency | 2.8 | 2.9 | Local overhead is negligible; model switches remain slow. |
| JSON reliability | 5.0 | 5.0 | 35/35 acceptance turns succeeded. |

Overall: **3.6/5 → 4.2/5**.

## Performance

- Combined new local checks/database lookup: **0.866 ms median**, **1.011 ms p95** over 2,000 iterations (v3 adaptive measurement: 0.128 ms).
- Live search: **0.828–0.948 s** for an uncached query; **0.608 ms** cached. Search is not used on ordinary conversation turns.
- Acceptance LLM median: **6.684 s**. A prior same-sequence run measured **5.377 s**, showing material model/runtime variance; deterministic added orchestration is under 1 ms.
- Observed normal/adult transition turns remained roughly **11–15 s**, matching the known v3 disk-switch range. Routing and single-residency safety were not changed.
- Known-corruption audio recovery completed in **5.875 s** and avoided downstream LLM/TTS latency.

## Remaining P2 limitations

1. Single-residency model switches still take about 11–15 seconds on the L4.
2. Adult Bengali responses fulfill allowed prompts but can remain awkward or less sensual than intended.
3. Banglish generation is learned and routed correctly but is not uniformly code-switched on every eligible reply.
4. Questions remain common (19/35 acceptance turns) even though the hard maximum of one is satisfied.
5. A fresh physical browser-microphone/echo acceptance pass is still needed; the audio retest used the same controlled WAV as v3.

PRITHI V3.1 STATUS: READY FOR NEXT STAGE
