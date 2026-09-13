# Prithi v3.1 fix list

No P0 security or cross-user leakage was found, so no production code was changed during this evaluation.

| Priority | Problem | Root cause | Likely module | Recommended fix | Retest |
|---|---|---|---|---|---|
| P1 | STT corruption causes confident semantic misreply | Transcript quality gate checks emptiness/form, not Bengali semantic uncertainty or likely homophone corruption | `prithi_stt.py`, `prithi_transcript_quality.py`, `prithi_voice_chat.py` | Preserve segment confidence/logprob; retry uncertain Bengali with conservative alternate decoding; ask a short clarification when meaning is low-confidence rather than inventing context | Repeat 20 real mic clips including কাজ/কাছ, সারাদিন/শারা দিন; score WER and semantic reply accuracy |
| P1 | Five taught preferences become only broad generic records | `learning_signal` creates one `response_preference` style from strategy, not a typed extracted preference | `prithi_learning.py` | Add deterministic typed extractors for nickname, language mix, teasing intensity, support style, and affectionate mirroring; store normalized values separately | Teach five preferences, restart, test each independently and inspect rows |
| P1 | Nickname is not persistent | Existing memory extractor has no “call me X” Bengali/Banglish pattern | `prithi_memory.py` | Add validated preferred-name/nickname extraction with length/script limits and explicit-user-statement requirement | Set nickname, clear rolling history/restart, verify recall; test injection and other-user isolation |
| P1 | Adult opt-in response remains vague | Adult prompt/strategy lacks concrete delivery targets; Qwen defaults to acknowledgement | `prithi_brain.py`, `prithi_strategy.py` | Add concise, consent-aware examples and fulfillment rubric for non-explicit sensual reciprocation; keep prohibited content rules | Run fixed 20-case opted-in adult set and compare fulfillment/refusal/consent scores |
| P1 | Unrelated learned behaviors enter prompts | Retrieval sorts by small tag overlap and then confidence, with no minimum relevance or type compatibility | `prithi_learning.py`, `prithi_web.py` | Require weighted tag threshold; match need/intent/type; exclude zero-overlap entries; deduplicate competing records | Teach unrelated humor/support preferences and verify each appears only in matching contexts |
| P2 | Too many questions/two-question replies | Guidance is prompt-only and punctuation validation does not enforce the voice maximum | `prithi_brain.py` | Reject/retry replies with more than one question in concise voice mode; strengthen no-question strategy metadata | Run 50 voice replies; require ≤1 question each and lower overall question rate |
| P2 | Humor requests are not fulfilled | `teasing_answer` is used for joke intent and does not require a complete joke/punchline | `prithi_context.py`, `prithi_strategy.py` | Distinguish `tell_joke` from teasing; add `humorous_answer` strategy and fulfillment check | Bengali/Hindi/English joke set; human-score completeness and naturalness |
| P2 | Roleplay repeats generic prompts | Scene summary is reply concatenation; no event extraction or anti-repeat objective | `prithi_roleplay.py`, `prithi_web.py`, `prithi_strategy.py` | Track compact user event + assistant event; add scene-progress strategy; reject repeated last question | Run 8-turn normal and adult-gated scenes; verify event continuity and no repeated closing question |
| P2 | Prithi says it remembered rejected sensitive content | LLM does not receive storage disposition before reply | `prithi_web.py`, `prithi_brain.py`, `prithi_memory.py` | Detect non-storable request before generation and instruct truthful wording: cannot save sensitive details | Ask to remember passwords/adult details; verify no DB row and no “saved/remembered” claim |
| P2 | Mode switches are slow | One-model-at-a-time L4 safety requires unload/load from disk | `prithi_model_router.py`, runtime scripts | Keep safe single residency; experiment with bounded keep-alive/prefetch only after VRAM measurement; show “switching mode” UI | Measure 10 switches, peak VRAM, OOM, and first-token/total latency |

## Recommended order

1. Bengali STT semantic-confidence recovery.
2. Typed preference and nickname extraction.
3. Relevance-thresholded learned-behavior retrieval.
4. Adult strategy fulfillment calibration.
5. Deterministic concise question limit.
