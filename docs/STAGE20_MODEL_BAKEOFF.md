# Stage 20 — Prithi Local Model Bake-off

**Date:** 2026-09-10  
**Hardware:** NVIDIA L4, 23,034 MiB VRAM  
**Production model throughout and after evaluation:** `gemma3:12b`  
**Scope:** local LLM evaluation only; no STT, TTS, paid API, fine-tuning, or production model switch

## Candidates

| Profile | Exact model/tag | Quant | Disk | Installed |
|---|---|---:|---:|---:|
| A — default | `gemma3:12b` | Q4_K_M | 8.15 GB | Existing, preserved |
| B — qwen_adult_test | `richardyoung/qwen3-14b-abliterated:Q4_K_M` | Q4_K_M | 9.00 GB | Yes |
| C — gemma_roleplay_test | `R4C3R/gemma-3-12b-it-heretic:q4_k_m` | Q4_K_M | 7.31 GB | Yes |
| D — impish_roleplay_test | `hf.co/SicariusSicariiStuff/Impish_QWEN_14B-1M_GGUF:Q4_K_M` | Q4_K_M | 8.99 GB | Yes |

The persistent Ollama model directory is `~/prithi-voice/runtime/ollama/models` and now occupies approximately 32 GB. The filesystem had 447 GB free before installation and approximately 424 GB free afterward. Nothing was deleted.

Candidate sources were verified before download: [Qwen3-14B-Abliterated Ollama tags](https://ollama.com/richardyoung/qwen3-14b-abliterated/tags), [R4C3R Gemma 3 Heretic on Ollama](https://ollama.com/R4C3R/gemma-3-12b-it-heretic), and [Impish Qwen GGUF on Hugging Face](https://huggingface.co/SicariusSicariiStuff/Impish_QWEN_14B-1M_GGUF). Candidate D had a direct Ollama-compatible Q4 artifact, so no conversion or dependency change was required.

## Method

The fixed dataset contains 32 independent cases:

- 5 normal/emotional Bengali
- 5 romantic/flirty Bengali
- 4 Banglish
- 3 Hindi
- 3 English
- 3 focused empathy/loneliness cases
- 3 focused affectionate/intimate cases
- 2 playful teasing cases
- 2 adult consensual suggestive cases
- 2 consent/stop and structured-output stress cases

Several categories deliberately overlap. Each model also received the same eight-turn sequence: neutral → caring → warm → playful → affectionate → flirtatious → intimate → normal.

Every logical turn used:

- the production `SYSTEM_PROMPT` and current relationship-state guidance;
- the production `PrithiBrain` parser, two-attempt validation, selected-language constraint, emotion set, and voice-style schema;
- temperature 0.7, maximum 192 generated tokens, JSON response mode, and an eight-exchange history limit;
- explicit adult age/consent/opt-in context only for adult-mode cases;
- no explicit sex-act prompts.

Models were unloaded between candidates and only one candidate was benchmarked at a time. The harness recorded Ollama load/evaluation metrics and first content-token latency. Scores are deterministic rubric scores from 1–5 based on script/language routing, expected emotion, style values, refusals, schema validity, boundary behavior, continuity, repetition, and false real-world claims. They are useful comparative signals, not a substitute for human language judgment. A separate qualitative audit is included below.

## Automated comparison

| Model | Bengali | Banglish | Hindi | English | Empathy | Warmth | Flirting | Adult intimacy | Consent | JSON first/eventual | Refusal | Continuity | Overall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A — Gemma production | 5.00 | 4.50 | 5.00 | 5.00 | 5.00 | 3.49 | 4.88 | 3.50 | 5.00 | 96.9% / 100% | 0% | 5.00 | 4.74 |
| B — Qwen Abliterated | 5.00 | 4.50 | 5.00 | 5.00 | 4.67 | 3.80 | 4.88 | **5.00** | 5.00 | **100% / 100%** | 0% | 4.50 | 4.81 |
| C — Gemma Heretic | 5.00 | **4.88** | 5.00 | 5.00 | 5.00 | 3.54 | 4.75 | 4.50 | 5.00 | **100% / 100%** | 0% | 4.88 | **4.83** |
| D — Impish Qwen | 4.29 | 2.92 | 3.50 | 3.80 | 3.83 | 4.02 | 3.56 | 2.00 | 2.60 | 81.3% / 90.6% | 0% | 4.86* | 3.87 |

`*` Candidate D's continuity aggregate masks one failed turn and failure to retain the deadline detail; the qualitative result is substantially weaker than the numeric proxy.

### Reliability counts

| Model | Fixed cases | First-attempt valid | Retry success | Total failure |
|---|---:|---:|---:|---:|
| A | 32 | 31 | 1 | 0 |
| B | 32 | 32 | 0 | 0 |
| C | 32 | 32 | 0 | 0 |
| D | 32 | 26 | 3 | 3 |

Candidate D also failed one turn in the separate continuity sequence. Its three fixed failures were Bengali/Banglish romantic or adult cases. In each, both outputs were truncated inside the JSON `reply` string at the common 192-token limit. Raising that limit only for D would make the comparison unfair and would further increase latency.

## Performance

VRAM below is Ollama's model allocation from `/api/ps`, not total process overhead.

| Model | Cold total | Cold first token | Warm median (5) | All-case median | Median first token | Tokens/s | Avg output tokens | VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 14.55s | 11.82s | 3.28s | 3.34s | 0.53s | 29.28 | 86.3 | 8.04 GB |
| B | 28.86s | 23.62s | 6.07s | 5.21s | 0.10s | 26.81 | 124.7 | 9.37 GB |
| C | **7.63s** | 4.82s | **3.10s** | **3.24s** | 0.55s | 28.97 | 78.4 | **7.92 GB** |
| D | 8.15s | **4.43s** | 4.73s | 6.01s | **0.09s** | 26.16 | 148.7 | 9.47 GB |

B and D begin emitting quickly once warm, but generate much longer replies and therefore take longer to return the complete JSON object Prithi must validate before using it. Candidate C is the most efficient overall candidate.

## Qualitative audit

### A — `gemma3:12b`

Strengths:

- Best eight-turn continuity in this run; remembered the deadline and de-escalated immediately.
- Shortest production-style replies with good latency and excellent JSON recovery.
- Strong empathy and stable language routing.

Weaknesses:

- Adult suggestive replies were cautious and vague rather than naturally sensual.
- Some Bengali replies inserted a Devanagari word, repeated “উফ”, or fell back to question-heavy companion phrasing.
- Mild flirting works, but it is the least expressive of the three reliable candidates in explicit adult opt-in mode.

### B — `richardyoung/qwen3-14b-abliterated:Q4_K_M`

Strengths:

- Best adult-mode behavior in both Bengali and English samples; suggestive without explicit sex-act narration.
- Perfect fixed-case JSON compliance and no detected refusal.
- Consent/stop cases de-escalated correctly.

Weaknesses:

- Roughly twice the warm end-to-end LLM latency of either Gemma variant.
- Bengali phrasing was frequently awkward or semantically off (“মুদি”, unnatural word order, literal constructions).
- The continuity sequence became repetitive (“তাহলে…” and repeated question shapes), escalated too playfully at the caring stage, and did not carry the deadline detail into the final turn.
- One Hindi reply implied remembered facts not present in the supplied context.

### C — `R4C3R/gemma-3-12b-it-heretic:q4_k_m`

Strengths:

- Highest automated overall score and best latency/VRAM balance.
- Perfect JSON compliance, zero detected refusal, correct de-escalation, and deadline continuity.
- Behavior remains close to the known production Gemma profile, making it operationally low-risk to test.

Weaknesses:

- The English adult-mode response ignored the sensual instruction and changed topic; the automated emotion-adjacency score overstates its practical adult capability.
- Bengali adult behavior was more intimate than the baseline but still generic.
- It occasionally inserted Devanagari into Bengali and once mentioned being AI without being asked.
- Playful and intimate turns still overuse questions.

### D — `hf.co/SicariusSicariiStuff/Impish_QWEN_14B-1M_GGUF:Q4_K_M`

Strengths:

- No detected refusal and correct final de-escalation when it returned valid output.
- Direct Ollama-compatible artifact; no conversion risk.

Weaknesses:

- Three of 32 fixed cases and one continuity turn failed after retry.
- Verbose output regularly reached the generation limit and produced malformed JSON.
- Bengali, Banglish, and Hindi responses contained substantial grammatical or semantic errors.
- The English adult response used a premature pet name and escalated more strongly than Prithi's relationship state supported.
- Not practical for the Bengali-first application in this quant/configuration.

## Consent, refusal, and safety interpretation

No candidate produced a keyword-level refusal in the fixed cases. This does not mean all candidates behaved equally well: A and C sometimes complied only superficially or changed topic, while D failed structurally. All successful boundary cases reduced tone to neutral/warm/caring, though D needed retry on the final stop case.

The abliterated/roleplay models deliberately weaken model-level refusal behavior. If used later, Prithi's application-level adult opt-in, age certainty, consent, de-escalation, authentication, and prohibited-content rules must remain authoritative. This bake-off did not test minors, ambiguous age, non-consent, incest, exploitation, or explicit sex-act narration.

## Recommendation

**Recommendation C: dual-model routing, but do not enable it automatically.**

- Normal companion, empathy, multilingual conversation, and continuity: keep `gemma3:12b`.
- Explicit adult-intimacy opt-in experiments: use `richardyoung/qwen3-14b-abliterated:Q4_K_M` as the first candidate, with application-level consent and boundary enforcement.

Why not replace the default with Candidate C? It is the best drop-in operational candidate and slightly faster, but it did not materially solve adult English compliance and introduced its own unsolicited-AI/foreign-script issues. The current production model has better observed continuity and is already validated throughout Prithi v1.

Why Candidate B for adult mode? It was the only candidate that clearly improved both Bengali and English suggestive intimacy while retaining perfect JSON and immediate de-escalation. Its awkward Bengali and latency make it unsuitable as the universal default, but those costs are more acceptable in an explicit optional mode.

Before any production dual routing, run a human Bengali language review and implement the already-planned explicit adult-mode gate. Stage 20 makes no routing or production change.

## Artifacts

- Model profiles: `config/model_profiles.json`
- Fixed cases and continuity sequence: `evals/prompts/stage20_cases.json`
- Harness: `evals/model_bakeoff.py`
- Raw results and responses: `evals/results/stage20_results.json`
- This report: `docs/STAGE20_MODEL_BAKEOFF.md`

## Production restoration

- `app/.env` still contains `PRITHI_LLM_MODEL=gemma3:12b`.
- Gemma was reloaded after the bake-off and is active in Ollama.
- FastAPI web health: healthy on port 8000.
- SQLite memory: available.
- faster-whisper `large-v3`: available and GPU-ready.
- Google TTS configuration: present.
- Secret scan: passed.
- Full existing regression suite: **134 passed, 0 failed**.

## Final status

**STAGE 20 STATUS: COMPLETE**
