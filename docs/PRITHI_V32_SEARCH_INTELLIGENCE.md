# Prithi v3.2 — Internet / Search Intelligence

Prithi can now answer current or unknown factual questions by checking the web, while staying
Prithi: Bengali/Banglish voice, mood, nicknames, relationship state and adult gating are unchanged.
Accuracy outranks personality only where they actually collide — when evidence is thin, Prithi says
so instead of inventing an answer.

Status: **PRITHI V3.2 STATUS: READY FOR BROWSER ACCEPTANCE TEST**

---

## 1. Files changed

| File | Change |
| --- | --- |
| `app/prithi_retrieval.py` | Knowledge router, clarification memory, office-title correction, retry policy, evidence prompt |
| `app/prithi_search.py` | Source ranking, evidence summarisation, conflict detection, tiered-TTL cache |
| `app/prithi_web.py` | Per-session pending-clarification state, retrieval on text + voice turns, `searching`/`reading` stream events, knowledge fields on the text-turn response |
| `app/test_prithi_retrieval.py` | Router/TTL/correction unit tests |
| `app/test_prithi_search_integration.py` | **New** — end-to-end search behaviour over the real HTTP app |
| `docs/PRITHI_V32_SEARCH_INTELLIGENCE.md` | **New** — this report |

Deliberately untouched: `app/web/*` (another session owns the UI), model defaults
(Gemma normal / Qwen adult), memory, mood, learning, roleplay, adult gating and voice.

---

## 2. Search architecture

```
user question (typed or spoken)
        │
        ▼
classify_knowledge(text, pending_clarification)   ← app/prithi_retrieval.py
        │
        ├── local            → answer from the model, no network
        ├── clarify          → ask ONE clarification, remember the question
        ├── search           → DuckDuckGoSearchProvider.search()
        ├── research_again   → forced second, broader/authoritative search
        └── unknown          → admit uncertainty, never invent
                 │
                 ▼
        rank sources (source_quality)
                 ▼
        summarize_sources()  → at most 4 sources, ≤360 chars each
                 ▼
        compact evidence appended to the adaptive prompt
                 ▼
        Prithi answers in her own voice
```

Raw pages are never fetched or pasted into the prompt. Only title + snippet + URL for the top four
ranked sources reach the model, which keeps the prompt small and the latency predictable.

The five router states map onto the spec's vocabulary as:

| Spec | Implementation |
| --- | --- |
| LOCAL_KNOWN | `local` |
| AMBIGUOUS | `clarify` |
| SEARCH_REQUIRED | `search` |
| VERIFY_REQUIRED | `research_again` |
| UNKNOWN | `unknown` |

### When Prithi searches

Freshness markers (`latest`, `current`, `today`, `news`, `price`, `score`, `election`, `president`,
`prime minister`, plus Bengali and Hindi equivalents such as `বর্তমান`, `সর্বশেষ`, `দাম`, `স্কোর`,
`ताज़ा`), explicit requests (`search`, `look up`, `খুঁজে দেখ`, `सर्च`), and verification requests
(`verify`, `are you sure`, `important`, `যাচাই`, `নিশ্চিত`, `जाँच`).

Casual and emotional conversation is routed to `local` before any freshness check, so
"আজ আমার মন খারাপ" or "I feel lonely today" never triggers a network call.

### Ambiguity and wrong titles

"Who is the PM?" has no country, so Prithi asks one clarification — "Which country or government do
you mean?" — and stores the original question on the session. The next reply is folded back into it
(`merge_clarification`), so "America" becomes "Who is the PM of America", which the router recognises
as a wrong office title: it searches for the **President** of the United States and instructs Prithi
to gently correct the terminology before answering. A clarification is asked **once**; if the reply
is still vague the router searches anyway rather than looping.

---

## 3. Confidence and retry logic

Confidence is computed in `evidence_from_sources()` from source count, how many sources are
official, how many are reputable, and domain diversity — capped at 0.95.

| Condition | Action |
| --- | --- |
| `research_again` requested | always run a second search |
| confidence < 0.58 | run a second, broader search (`… official primary source`) |
| sources disagree | confidence capped at 0.48, then a second search |
| no sources, or confidence < 0.40, or still conflicting | `unknown` — admit it honestly |

The second pass merges both result sets by URL and re-scores, so a retry never just repeats the
first answer. `research_again` also bypasses the cache, so "are you sure?" always does fresh work.

Conflict detection (`sources_disagree`) compares token overlap between positively and negatively
phrased snippets (`is not`, `no longer`, `নয়`, `নেই`, `नहीं`); ≥35% overlap between an affirming and
a denying source counts as disagreement.

When the outcome is `unknown`, the prompt tells Prithi to admit uncertainty and explicitly *not*
invent an answer — the intended feel being "Uff… I checked again, but I still can't verify that
properly."

---

## 4. Source ranking

| Quality | Sources |
| --- | --- |
| 1 — official / primary | `.gov`, `.gov.in`, `.nic.in`, `.int`, WHO, UN, europa.eu, whitehouse.gov |
| 2 — reputable major | Reuters, AP, BBC, NASA, Nature, The Hindu, Indian Express, ESPN, Cricbuzz, `.edu`, `.ac.in`, `docs.*` |
| 3 — general web | everything else with a host |
| 4 — unknown | no resolvable host |

Sources are sorted ascending by quality, so official sources lead the evidence block. Verified live:
`current President of the United States official` returns `whitehouse.gov` ranked first.

---

## 5. Cache and freshness

Search results are stored in a `retrieval_cache` table, separate from `memory_items`. They are
**never** written into personal memory, never become part of the relationship profile, and are not
used for learned behaviour. The cache holds query, timestamp, sources, confidence, summary and an
expiry.

| Query kind | TTL |
| --- | --- |
| Fast-moving — score, live, price, stock, crypto, weather, today, news, `দাম`, `স্কোর` | 180 s |
| Default | 900 s (`PRITHI_WEB_SEARCH_TTL_SECONDS`) |
| Slow-moving — president, prime minister, capital, population, CEO | 6 h |

---

## 6. UI states

No frontend files were modified by this work — the UI session owns `app/web/*`. The backend emits the
states over the existing SSE stream on `/api/voice-turn-stream`, and the UI session has since wired
them up (`app/web/app.js:819-823`, which calls `setStatus("Searching", …)` / `setStatus("Reading
sources", …)`):

| Event | Payload | Meaning |
| --- | --- | --- |
| `searching` | `text`, `knowledge_action` | SEARCHING — carries a short spoken interim line |
| `reading` | `knowledge_action`, `search_confidence`, `source_count` | READING |
| `thinking` | *(existing)* | THINKING |
| `answering` | *(existing)* | ANSWERING |

The interim line is language-matched and rotates across three variants per language, seeded by the
transcript so it does not repeat the same phrase every time — e.g. "হুম... এটা একবার দেখে নিই।",
"একটু দাঁড়াও, ঠিক তথ্যটা যাচাই করছি।", "Hmm... I should check that."

`/api/text-turn` now also returns `knowledge_action`, `knowledge_reason`, `search_confidence`,
`search_source_count` and `search_retry_count`.

---

## 7. Tests

Full suite on the Studio: **258 tests, all passing** (240 before v3.2, 18 added).

`app/test_prithi_search_integration.py` (14 tests) drives the real FastAPI app with a scripted
search provider, so no test touches the network:

- current fact triggers a search on a typed turn
- stable question stays local, provider never called
- casual Bengali conversation never searches
- typed turn receives compact evidence, not raw pages
- voice turn searches and streams `searching` → `reading` → `reply`
- ambiguous office asks one clarification, then answers "America" with the President correction
- a second clarification is never requested
- explicit verification runs a second search (`search_retry_count == 1`)
- conflicting sources admit uncertainty instead of answering
- failed search returns honest uncertainty and "do not invent an answer"
- personality, Bengali reply language and mood survive a searched turn
- search results land in the TTL cache and **not** in `memory_items`
- adult mode stays gated (403 without age confirmation) while search works
- silence follow-up is offered at most once

`app/test_prithi_retrieval.py` adds unit coverage for clarification merging, the single-clarification
rule, the office correction reaching the prompt, and the tiered TTL.

Adult de-escalation ("stop", "not now", `থাম`, `बस करो`) remains covered by the existing v3.1 tests
`test_roleplay_stop_deescalates`, `test_07_stop_is_immediate_normal_exit` and
`test_08_not_now_deescalates_without_inference` — unchanged by this work.

---

## 8. Latency overhead

Measured on the Studio against the live provider:

| Path | Overhead |
| --- | --- |
| Local / casual turn | 0 ms — classification is regex only, no network |
| Single search | ~0.75 s |
| Search + retry (low confidence, conflict, or "are you sure?") | ~1.5 s |
| Cache hit | ~1 ms |

Provider timeout is 8 s (`PRITHI_WEB_SEARCH_TIMEOUT`); a timeout or provider error degrades to
`unknown`, never to a fabricated answer. The interim status line is emitted before the search starts,
so the user hears something within the normal response window.

---

## 9. Known limitations

1. **Single provider.** DuckDuckGo HTML scraping has no API key but is fragile — a markup change
   breaks parsing. Failure degrades to honest uncertainty rather than a wrong answer.
2. **Snippet-level evidence.** Prithi reads result snippets, not full pages, so questions whose
   answer is buried inside an article may come back as `unknown`.
3. **Keyword routing.** Classification is regex/keyword-based, not model-based. An unusually phrased
   current-affairs question may stay `local`; the user can always force a check with "search" or
   "are you sure?".
4. **Conflict detection is lexical.** Token-overlap heuristics catch direct contradictions, not
   subtle disagreements about dates or numbers.
5. **Clarification is single-slot.** One pending question per session; a new question replaces it.
6. **Country coverage of title correction.** Only the US President/Prime Minister confusion is
   encoded today (`OFFICE_CORRECTIONS`); other countries search normally without a correction note.
7. **Search states surface only on the streaming voice route.** `/api/voice-turn-stream` emits
   `searching` / `reading` and the UI renders them; `/api/text-turn` is a single request/response, so
   a typed question that needs a search shows no interim status — it simply takes ~0.75 s longer.

---

## 10. Manual browser acceptance steps

Start the stack on the Studio:

```bash
cd ~/prithi-voice
./scripts/start_prithi_web.sh          # serves on PRITHI_WEB_PORT (default 8000)
```

Open the web UI and run these, checking both **typed** and **voice** input:

| # | Say / type | Expect |
| --- | --- | --- |
| 1 | "আজ আমার মন খারাপ" | Warm Bengali reply, no search, no delay |
| 2 | "Why do leaves look green?" | Answered locally, no search |
| 3 | "What is the current cricket score?" | Brief interim line, then an answer citing what she checked |
| 4 | "Who is the PM?" | Asks one clarification — which country |
| 5 | reply "America" | Gently corrects: the US has a President, then answers |
| 6 | "Are you sure?" | Visibly checks again; answer is re-derived, not repeated verbatim |
| 7 | Ask something obscure and current | Admits she could not verify it — no invented answer |
| 8 | Repeat step 3 within 3 minutes | Faster (cache hit), same answer |
| 9 | Speak step 3 into the mic | Same behaviour as typed; `searching`/`reading` events in the network tab |
| 10 | Adult mode without age confirmation | Still blocked (403); search still works |
| 11 | Let Prithi ask a question, stay silent | At most one gentle follow-up, never repeated |

Verify throughout that replies stay in Bengali/Banglish, keep her nickname and mood, and that nothing
retrieved from the web shows up later as a personal memory (`/api/memory`).

---

## 11. Not done, by instruction

No LoRA training, no Stage 24 work, no model default changes, no destructive Git commands, and
nothing committed or pushed — v3.1 and v3.2 changes remain uncommitted in the working tree because
another session is editing the UI.
