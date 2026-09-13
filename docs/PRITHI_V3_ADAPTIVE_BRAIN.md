# Prithi v3 Adaptive Brain

## Architecture

Prithi v3 wraps the existing STT → routed LLM → TTS pipeline. It does not replace STT, Google TTS, memory, adult gating, or Gemma/Qwen routing.

Before the LLM call, deterministic context analysis derives intent, emotion, need, subtext, relationship/intimacy/boundary signals, and language. A strategy selector chooses one compact response strategy. Persistent per-user mood is loaded, decayed toward a safe baseline, and changed in bounded increments. Only the top relevant factual memories and learned behavior preferences are included. Session-only roleplay state is explicitly marked fictional.

The orchestrator supplies a compact observable-state prompt. No chain-of-thought is requested, stored, or exposed. The existing `reply`, `language`, `emotion`, and `voice_style` schema remains unchanged. After a valid reply, mood softly blends into TTS voice style and is persisted.

## State boundaries

- Real memory remains in the existing memory tables.
- Mood uses a per-user `mood_states` table.
- Learned response preferences use a separate `learned_behaviors` table.
- Roleplay is session-only and never enters real memory.
- Adult roleplay requires both persistent 18+ confirmation and current-session opt-in.
- Stop/boundary signals reset roleplay and select immediate de-escalation.
- Adult/sensitive details and credentials are excluded from automatic learning.

## Continual learning

Level 1 is immediate session context and mood. Level 2 is confidence-weighted, per-user response preference learning. Positive repetitions raise confidence; negative feedback lowers it. Level 3 uses explicit `export_candidate` calls to write pending-review JSONL under `training/data/learned_candidates/`; nothing is promoted to training automatically and model weights never change live.

## UI and operations

The existing Advanced details disclosure now contains a safe Adaptive Brain summary: selected model, emotion, strategy, bounded mood values, relationship values, roleplay status, and counts of relevant memories/learned behaviors. It excludes secrets, prompts, raw user identifiers, and hidden reasoning.

Production remains configured for normal Gemma and gated adult Qwen. Rejected LoRA v0.1 is not referenced or loaded.

## Validation on Lightning L4

- NVIDIA L4: available, 23,034 MiB total.
- Ollama: healthy; `gemma3:12b` and the existing gated Qwen adult model are available.
- Web health: authenticated HTTP 200-equivalent JSON status `ok`; STT ready; TTS configured.
- SQLite: integrity check `ok`; adaptive tables created without altering existing memory tables.
- Adaptive orchestration: approximately 0.128 ms per deterministic context/mood/strategy/prompt pass (5,000-pass measurement).
- Live normal-mode Bengali: Gemma returned valid Bengali JSON with `caring` emotion and `reassurance` strategy.
- Live post-start LLM generation: 14.159 seconds. Adaptive orchestration is not the material latency source.
- Automated regression: 201 tests passed, including 20 new adaptive tests.

Known limitation: roleplay state is intentionally session-only and its scene summary is application-managed; no additional LLM summarization call is made. Learned behaviors currently require explicit positive/negative feedback language before persistence, favoring precision over aggressive learning.
