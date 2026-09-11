# Stage 22 — Prithi Dataset Design

## Objective

Build a reviewable, multilingual instruction-tuning corpus that strengthens Prithi's Bengali-first companion personality without changing the production runtime. The target is approximately 2,000 approved examples; this stage creates a 200-row pilot and a separate 50-case golden evaluation set. No training is performed.

The intended behavior is natural spoken conversation: emotionally specific, concise, intelligent, affectionate and playful when context supports it. The corpus should reduce counselor boilerplate, repetition, forced questions, false memories, random Hindi drift in Bengali, and premature romantic escalation.

## Canonical format

Training data uses JSONL with one object per conversation. The canonical fields are `id`, `language`, `mode`, `category`, `emotion`, `relationship_context`, `messages`, and `review`. Relationship values are bounded from 0 to 1. Messages begin with `system`, alternate `user` and `assistant`, and end with `assistant`.

Canonical rows remain model-neutral. `convert_chat_template.py` creates derived message-only or ShareGPT files later, leaving source data unchanged.

Review metadata supports `pending`, `approved`, `rejected`, and `edited`. Six 1–5 scores cover naturalness, personality fit, language quality, emotional quality, non-repetition (5 is best), and voice suitability. Generated or authored rows are never treated as human-approved automatically.

## Taxonomy and balance

The full taxonomy is stored in `training/config/taxonomy.json`. It covers everyday conversation, warmth, caring, loneliness, reassurance, affection, teasing, romance, attraction, adult opt-in sensuality, relationship progression, reconciliation, aftercare, boundaries, de-escalation, memory callbacks, humor, disagreement, light playful jealousy, vulnerability, happiness, tiredness and stress.

Target language balance:

- Bengali: 45%
- Banglish: 25%
- Hindi: 15%
- English: 15%

Target behavior balance:

- Normal/friendly/casual: 20%
- Empathy/caring/loneliness: 20%
- Affection/romance: 20%
- Playful/teasing/flirting: 15%
- Adult sensual/suggestive: 10%
- Relationship/memory continuity: 10%
- Boundary/de-escalation: 5%

These are distribution goals, not reasons to keep weak examples. At least 25–30% should be multi-turn. The pilot contains 56 multi-turn rows (28%), including eight longer eight-dialogue-turn continuity arcs (two per language). The canonical schema also supports further 3-, 5-, and 8-turn variations during scaling.

## Adult-mode boundary

Adult-oriented training rows require `mode="adult"` and a system message that explicitly states all participants are confirmed adults and adult mode was opted into. Allowed content includes consensual flirting, romantic attraction, sensual or suggestive language, longing, affectionate closeness, bedtime companionship, consent checks, aftercare and immediate de-escalation.

Exclude minors or ambiguous age, non-consent, coercion, incest, exploitation and explicit sex-act/intercourse narration. Normal mode must not infer adult intent from affection, loneliness, bedtime context or flirting. Boundary examples must stop immediately without persuasion, guilt or pressure.

Explicit adult details and intimate preferences are not intended as persistent user-memory facts. Dataset review should reject examples that encourage such storage.

## Pilot strategy

`training/data/raw/prithi_pilot_v1.jsonl` contains 200 authored candidate rows with exact 90/50/30/30 language counts and 20 adult-mode rows. It is intentionally marked `pending`. Review language by language and category by category before moving approved or edited rows into `training/data/curated/`.

Scale only after reviewing a representative slice from every category. Generate future local candidates in small batches (maximum 25) using `generate_dataset.py`; it accepts only a loopback Ollama endpoint and refuses to overwrite an existing output. It does not call any provider unless a reviewer runs it explicitly.

Example controlled generation command:

```bash
python training/scripts/generate_dataset.py \
  --model gemma3:12b \
  --count 10 \
  --language bengali \
  --category caring \
  --output training/data/raw/bn_caring_batch_01.jsonl
```

## Human review workflow

Run:

```bash
python training/scripts/review_dataset.py training/data/raw/prithi_pilot_v1.jsonl
```

The CLI shows non-system dialogue, accepts approve/reject/edit/skip, collects optional scores and notes, and saves atomically after each reviewed row. Editing replaces only the final assistant response. Reviewers should check spoken naturalness aloud, response specificity, language drift, question frequency, relationship-level fit, consent behavior and whether the reply feels concise enough for TTS.

No bulk approval is provided. A second native-language review is recommended for adult-mode, Banglish and subtle emotional examples.

## Validation and deduplication

Run validation without rewriting content:

```bash
python training/scripts/validate_dataset.py \
  training/data/raw/prithi_pilot_v1.jsonl \
  --report training/reports/pilot_validation.json
```

Validation checks JSON, required fields, taxonomy values, role order, message content, relationship bounds, language/script signals, explicit adult-mode markers, prohibited contexts, secret-like strings, long replies, exact prompt/reply duplicates and near-identical conversations.

Create a separate duplicate report with:

```bash
python training/scripts/deduplicate_report.py \
  training/data/raw/prithi_pilot_v1.jsonl \
  --output training/reports/pilot_duplicates.json
```

Neither tool rewrites or deletes data. Near-duplicate findings require human judgment.

## Split strategy

After human curation, create deterministic 90/5/5 splits with seed `2201`:

```bash
python training/scripts/split_dataset.py \
  training/data/curated/prithi_v1_approved.jsonl \
  --output-dir training/data/splits \
  --seed 2201
```

The splitter accepts approved/edited rows by default and groups near-identical conversations before assigning a split, preventing close variants from leaking across train, validation and test. It refuses to overwrite existing split files unless explicitly requested.

## Golden evaluation set

`evals/prithi_golden_v2.jsonl` contains 50 training-excluded cases for Bengali emotional quality, Banglish, empathy, teasing, romance, explicit adult opt-in sensuality, stop/de-escalation, language routing, memory callbacks, anti-repetition, relationship progression and production JSON-schema expectations. Never concatenate this file into training data.

Deliberately bad responses should remain evaluation criteria or future preference pairs, not ordinary SFT assistant targets.

## Risks

- Template artifacts can make a large synthetic corpus repetitive even when exact strings differ.
- Bengali and Banglish quality requires native review; script checks cannot judge idiom reliably.
- An abliterated generator can weaken consent or safety boundaries, so adult candidates require stricter review.
- Relationship-state examples can accidentally teach false memories unless history is explicit.
- Golden-set leakage would inflate evaluation results.
- A 2,000-row dataset may overfit phrasing if category and opening diversity are not monitored.
- Voice-friendly brevity can reduce nuance if applied mechanically to vulnerable conversations.

## Next training step

Do not train until the pilot has native-language review, adult-boundary review, clean validation, duplicate triage and baseline evaluation results from the untouched production model. Then finalize the target chat template, prepare approved deterministic splits, choose a LoRA configuration in a separate stage, and compare against `prithi_golden_v2.jsonl` before any deployment decision.

## Production isolation

Stage 22 owns only `training/`, `evals/prithi_golden_v2.jsonl`, and this document. It must not edit or restart the production web application, STT, TTS, LLM router, `.env`, SQLite memory database, startup scripts, or active model configuration.
