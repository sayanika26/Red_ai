# Stage 23 — Prithi pilot LoRA training

## Outcome

One isolated QLoRA pilot adapter was trained and exported successfully. It did **not** pass the promotion bar. The correct recommendation is **KEEP BASE**.

Production routing was not changed. `PRITHI_LLM_MODEL` and `PRITHI_LLM_NORMAL_MODEL` remain `gemma3:12b`; the existing adult Ollama candidate remains configured separately and was not replaced by this adapter.

## Dataset review and curation

The existing validator and deduplication tools were rerun on `training/data/raw/prithi_pilot_v1.jsonl`. The 200 source rows had zero schema errors, zero validator warnings, zero exact prompt/reply duplicates, 18 high-confidence near-duplicate pairs at 0.92, and 65 broader pairs at 0.88.

A conservative review retained one deterministic representative per connected near-duplicate component and excluded every unresolved redundant variant. It also checked language/script consistency, awkward Banglish structure, counselor/assistant phrasing, formality, overlength, repeated questions/n-grams, false-memory risk, relationship escalation, adult opt-in context, forbidden topics, explicit sex-act terms, and golden-prompt overlap.

| Curation metric | Count |
|---|---:|
| Starting | 200 |
| Curated/approved | 146 |
| Excluded | 54 |
| Golden prompt overlaps | 0 |
| Normal-mode retained | 126 |
| Confirmed-adult opt-in retained | 20 |

Curated language distribution: Bengali 56, Banglish 32, Hindi 29, English 29.

Fixed-seed (`2301`) language-stratified splits are 132 train / 7 validation / 7 test. Redundant near-duplicate variants were removed before splitting, so they cannot leak across splits. The separate 50-case `evals/prithi_golden_v2.jsonl` remained evaluation-only.

## Base lineage and license

The installed Ollama candidate `richardyoung/qwen3-14b-abliterated:Q4_K_M` is a 14.8B Qwen3 Q4_K_M inference artifact. Its corresponding Hugging Face GGUF metadata identifies `Qwen/Qwen3-14B` as its upstream base.

Training did not use the Ollama GGUF. It used the official `Qwen/Qwen3-14B` full-precision lineage through a supported 4-bit Transformers loading path. The adapter therefore learns Prithi style on official Qwen3-14B; it does not reproduce the separate abliteration transformation.

Qwen3-14B is Apache-2.0. Fine-tuning and redistribution of adapter derivatives are permitted subject to Apache license, notice, modification-marking, and attribution requirements. Full details are in `training/reports/base_model_license.md`.

## Training environment and configuration

The isolated environment is `/teamspace/studios/this_studio/.virtualenvs/prithi-training`; the production `prithi-voice` environment was not changed.

- NVIDIA L4, BF16 supported
- PyTorch 2.11.0+cu128; Transformers 5.17.0; PEFT 0.20.0; bitsandbytes 0.50.2
- 4-bit NF4 with double quantization and BF16 compute
- LoRA rank 16, alpha 32, dropout 0.05
- Actual Qwen modules: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`
- 512-token maximum based on observed 492-token maximum (p95 312)
- Batch 1, accumulation 8, assistant-only loss, gradient checkpointing
- 1e-4 cosine learning rate
- One epoch, 17 optimizer steps

Training completed in 173.56 seconds after a 77.48-second initial load. Train loss was 1.56837; validation loss declined from 3.14698 to 1.13367. Peak allocated VRAM was 15.45 GiB. The exported adapter is about 256 MiB.

## Golden evaluation

Both variants received the same production Prithi prompt constants, mode context, relationship state, language constraint, golden prompts, greedy decoding, 192-token limit, validation rules, and one retry opportunity. This was direct Transformers inference, not Ollama, STT, TTS, or a paid API. Scores are deterministic screening metrics, not a substitute for native-speaker human judgment.

| Metric | Base Qwen3-14B | Prithi LoRA v0.1 |
|---|---:|---:|
| Overall automated score | **4.340** | 4.100 |
| Bengali | 4.826 | 4.826 |
| Banglish | **3.000** | 2.833 |
| Hindi | 5.000 | 5.000 |
| English | 5.000 | 5.000 |
| Empathy | **4.733** | 4.300 |
| Affection | **3.600** | 3.136 |
| Playful teasing | **4.188** | 3.833 |
| Romantic tone | **4.182** | 3.708 |
| Adult sensual/suggestive | **3.917** | 3.667 |
| Consent/de-escalation | **3.400** | 2.818 |
| Anti-repetition | 4.260 | **4.420** |
| Relationship continuity | **4.920** | 4.840 |
| Controlled normal mode | **4.920** | 4.840 |
| JSON compliance score | **4.840** | 4.560 |
| First-attempt valid JSON | **47/50 (94%)** | 41/50 (82%) |
| Valid after retry | **49/50 (98%)** | 48/50 (96%) |
| Total failures | **1** | 2 |
| Refusals | 0 | 0 |
| Median generation latency | **8.693 s** | 13.885 s |

Evaluation peak allocated VRAM was about 10.11 GiB. Full responses, raw attempts, errors, latencies, and per-case scores are preserved in `training/reports/stage23_golden_evaluation.json`.

## Regression findings

- Bengali script quality did not materially degrade in the automated screen.
- Banglish, empathy, affection, teasing, romantic tone, adult-mode behavior, consent/de-escalation, continuity, and normal-mode control all declined.
- Anti-repetition improved slightly, but not enough to offset the broader regressions.
- First-attempt JSON reliability fell 12 percentage points and total failures doubled.
- Median direct generation latency increased about 60%.
- There were no detected refusals and no evidence of automatic explicit sexual behavior, but the weaker consent/de-escalation score fails the acceptance rule.

The likely cause is pilot mismatch: only 146 curated rows, trained as natural assistant dialogue, are too small and not explicitly balanced to preserve the production JSON contract. A future iteration should add more native-reviewed Bengali/Banglish data and explicit JSON-formatted SFT examples, while up-weighting stop/de-escalation and normal-mode control. That is a future test, not a production change.

## Artifacts

- Review: `training/reports/stage23_pilot_review.md`
- Curation decisions: `training/reports/stage23_curation.json`
- Curated data: `training/data/curated/prithi_pilot_v1_curated.jsonl`
- Splits: `training/data/splits/`
- License: `training/reports/base_model_license.md`
- Metrics: `training/reports/stage23_training_metrics.md`
- Full golden results: `training/reports/stage23_golden_evaluation.json`
- Adapter: `training/checkpoints/prithi-qwen-lora-v0.1/`

## Production verification

- `gemma3:12b` is the active Ollama model.
- Web root and authenticated health return HTTP 200.
- Ollama, STT, memory database, and TTS configuration are healthy.
- Secret scan passed.
- Existing application regression suite: 165 passed, 0 failed.

## Recommendation

**KEEP BASE.** Preserve the adapter only as a research artifact. Do not merge it, route live traffic to it, or promote it without a better dataset and another evaluation stage.

**STAGE 23 STATUS: COMPLETE**
