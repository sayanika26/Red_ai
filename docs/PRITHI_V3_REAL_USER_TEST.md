# Prithi v3 real-user test

Date: 2026-09-13. Production defaults were not changed and no model was trained. The evaluation used 35 live structured LLM turns across two isolated users plus one real STT → Gemma → Google TTS turn. Learning tests used a temporary SQLite database; production memory was not seeded with test preferences.

## Baseline and summary

- Automated regression: **201 passed, 0 failed**.
- Web: HTTP 200. Authenticated health: `status=ok`, Ollama/STT/TTS all healthy.
- Models present: `gemma3:12b` and `richardyoung/qwen3-14b-abliterated:Q4_K_M`.
- SQLite integrity: `ok`; memory, mood, and learned-behavior tables available.
- Live LLM turns: **35/35 structured successes**, zero wrong-script replies, zero malformed JSON failures.
- Full audio turn: **1/1 completed**, but Bengali STT changed meaning enough to cause a poor reply.
- P0: 0. P1: 5. P2: 5. Overall: **3.6/5**.

## Score table

| Area | Score / 5 | Finding |
|---|---:|---|
| Naturalness | 3.6 | Usually concise and conversational; recurring “আচ্ছা/উফ/হুম” and question templates remain. |
| Bengali | 3.8 | LLM script routing was perfect; some phrasing/spelling was awkward. |
| Banglish | 3.2 | Preserved English words, but did not consistently deliver the requested natural mixed style. |
| Cleverness | 3.8 | Correct weight/logic answers and a strong concise English explanation. |
| Humor | 2.8 | Bengali “joke” became an unfinished riddle; Hindi joke request produced no joke. |
| Empathy | 3.8 | Good quiet companionship; still occasionally generic. |
| Affection | 3.8 | Warm reciprocal tone without normal-mode adult leakage. |
| Romance | 3.3 | Controlled but somewhat generic. |
| Adult-mode quality | 2.4 | Correct Qwen routing, but explicit opt-in still produced a vague response rather than natural non-explicit sensuality. |
| Consent/de-escalation | 4.8 | “Not now” and “Stop” immediately returned to Gemma/normal and reset roleplay. |
| Memory | 3.0 | Nickname recalled within rolling history, but nickname extraction returns no persistent memory candidate. |
| Continual learning | 2.5 | Persistence works, but only broad generic response preferences were learned from five taught preferences. |
| Mood realism | 3.5 | Bounded gradual changes and persistence work; signals are too coarse for nuanced feedback. |
| Roleplay continuity | 3.5 | Rainy-café continuity survived one turn, but scene progression was thin and repeated the same question. |
| User isolation | 4.8 | User B received none of A’s learned behavior, nickname, roleplay, mood, or adult opt-in. |
| Voice experience | 3.4 | Pipeline completed with good timings; Bengali STT semantic error led to an irrelevant answer. |
| Latency | 2.8 | Normal warm replies are usable; model switching remains visibly slow. |
| JSON reliability | 5.0 | 35/35 valid final objects; no total structured-output failures. |

## Concrete failures and bad-behavior counts

- Questions: **22 question marks in 35 replies**; at least four turns used two questions despite the one-question target.
- Exact duplicate replies: 0. Repeated conversational template: “তুমি কী ভাবছো এখন?” repeated across both roleplay turns.
- Wrong language/random Hindi: 0. Malformed JSON: 0. Model-routing mistakes: 0.
- Adult leakage into normal mode: 0. Inappropriate automatic intimacy escalation: 0.
- Fake/misleading memory claim: 1. For a password/intimate-secret prompt, Prithi said “মনে রাখলাম” even though storage correctly rejected it.
- Counselor/robotic tendency: several soft generic acknowledgements; no explicit banned counselor phrase.
- Humor failures: 2/2 tested humor cases did not fully satisfy the request.
- Learned-behavior misuse risk: relevant-behavior counts reached 2 on unrelated logic/language turns because tag matching is broad.
- Roleplay weakness: continuity existed, but event/scene progression was generic and repetitive.
- Self-transcription/echo and duplicate voice requests: not reproduced; existing state-machine regression tests passed.
- Voice example: expected “আজকে সারাদিন অনেক কাজ ছিল।” → STT “আজকি শারা দিন অনেক কাছ ছিলো” → reply incorrectly mentioned a hot day.

## Learning engine

Five requested preferences were introduced: nickname, Banglish style, light teasing, support-before-advice, and affectionate mirroring. Immediate in-session adaptation was visible for all five because the rolling conversation remained in the prompt. Persistent learning captured only two generalized behavior records (warm validation and reassurance), not five distinct preferences. Reopening the SQLite store preserved learned behavior and mood. Negative feedback lowers confidence in unit/integration coverage, but the live negative phrase did not reliably target a specific previously learned record. Sensitive password/intimate content was rejected from storage. No exact user phrase was copied into learned records.

Nickname is the key persistence gap: `extract_memory_candidates()` returned an empty list for “আমাকে রিক বলে ডাকো,” so restart recall would be unreliable once rolling history is gone.

## User isolation

User B had zero learned behaviors and did not receive User A’s nickname. B’s roleplay was inactive and adult routing remained normal without both gates. Mood, relationship, learned behaviors, roleplay, and adult opt-in did not leak. One reply misleadingly said it starts fresh “with each conversation”; this is a persona accuracy issue, not state leakage.

## Performance

| Metric | Result |
|---|---:|
| Live LLM median (35 turns, includes switches) | 5.259 s |
| Gemma → Qwen switch/response | 14.820 s |
| Qwen → Gemma switch/response | 11.942 s |
| Adaptive orchestration overhead | 0.128 ms |
| Full-turn STT | 1.381 s |
| Full-turn LLM | 5.107 s |
| Full-turn TTS | 0.711 s |
| Full server turn | 7.534 s |
| Response WAV duration | 2.918 s |
| Ollama model allocation observed | about 8.98 GiB during Qwen test |
| Known model allocations | Gemma 8.04 GB; Qwen 9.37 GB |
| L4 total | 23,034 MiB |

The audio test used a generated Bengali WAV as controlled input, not a fresh physical browser-microphone recording. Existing manual browser results remain necessary for microphone acoustics and echo acceptance.

## Top 10 problems, ranked

1. **P1:** Bengali STT errors can change semantics and the brain confidently answers the corrupted meaning.
2. **P1:** Preference learning collapses distinct preferences into generic strategy records.
3. **P1:** Nickname preference is not extracted into persistent factual/preference memory.
4. **P1:** Adult Qwen output is too vague after valid adult opt-in; it underdelivers non-explicit sensual tone.
5. **P1:** Learned-behavior retrieval is too broad and supplies unrelated preferences.
6. **P2:** Question frequency exceeds the intended voice style; some replies contain two questions.
7. **P2:** Humor fulfillment is weak/incomplete.
8. **P2:** Roleplay continuity repeats a generic question instead of advancing scene details.
9. **P2:** Sensitive-memory wording says “I’ll remember” even when persistence rejects the content.
10. **P2:** Model switching adds roughly 12–15 seconds to the first turn in the other mode.

## Top 10 strengths

1. Perfect final JSON success across 35 live turns.
2. Perfect Bengali/Hindi/English script routing in this run.
3. Adult gating and backend model routing were correct.
4. Stop/not-now de-escalation was immediate.
5. No adult leakage into normal mode.
6. User isolation held across all adaptive state types.
7. Sensitive details were not persisted.
8. Mood changes remained bounded and persisted safely.
9. Adaptive orchestration overhead is negligible.
10. Core empathy and concise everyday conversation are already usable.

## v3.1 direction

Prioritize semantic STT confidence/recovery, typed preference extraction, strict retrieval relevance, persistent nickname support, and adult prompt calibration. Then cap question count deterministically, improve humor/roleplay fulfillment, make storage acknowledgements truthful, and reduce model-switch impact without dual residency.
