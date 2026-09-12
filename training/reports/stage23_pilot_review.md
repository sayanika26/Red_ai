# Stage 23 pilot review

## Scope and safeguards

- Source: `training/data/raw/prithi_pilot_v1.jsonl` (SHA-256 `f4175c2d566561f872551b4cc4f41dd89358b56298d807118eeb68ce1d0deb44`)
- Golden evaluation set: `evals/prithi_golden_v2.jsonl` (SHA-256 `d8e876a4bb598b5ae3c8e105e9e957cc4bc0609d180b4a41549bc1bdfb06b88e`)
- The raw source and golden set were not modified.
- The golden set is excluded by file separation and normalized final-user-prompt overlap checking.
- No explicit sex-act/intercourse examples are permitted by the review rules.

## Validator and duplicate results

The existing Stage 22 validator completed with 200 valid rows, zero schema/content errors, zero length warnings, zero exact prompt duplicates, zero exact reply duplicates, and 18 high-confidence near-duplicate pairs at the validator's 0.92 threshold.

The broader deduplication pass found 65 pairs at the 0.88 threshold. These pairs form connected components. A deterministic lowest-ID representative was retained only when it passed every other check; 54 redundant variants were excluded. No source row was deleted.

## Automated review checks

Every row was checked for malformed role order, language/script mismatch, awkward Banglish structure, excessive length, repeated questions, repeated n-grams, formal/counselor boilerplate, unsupported memory claims, inappropriate normal-mode escalation, adult-mode context without confirmed-adult opt-in, prohibited themes, explicit sex-act terms, and overlap with the golden evaluation prompts.

Rows with any unresolved flag were excluded. The review did not rewrite dialogue or guess at ambiguous edits. Native-speaker review remains recommended before growing beyond this pilot.

## Curation result

| Metric | Count |
|---|---:|
| Starting candidates | 200 |
| High-confidence auto-approved | 146 |
| Excluded | 54 |
| Exact duplicate groups | 0 |
| Near-duplicate pairs reviewed | 65 |
| Redundant near-duplicate variants excluded | 54 |
| Golden prompt overlaps | 0 |

### Curated language distribution

| Language | Count |
|---|---:|
| Bengali | 56 |
| Banglish | 32 |
| Hindi | 29 |
| English | 29 |

### Curated mode distribution

| Mode | Count |
|---|---:|
| Normal | 126 |
| Adult opt-in | 20 |

All 20 retained adult-mode examples include the required confirmed-adult and explicit opt-in system context. The detailed per-row decision and flag record is stored in `training/reports/stage23_curation.json`.

