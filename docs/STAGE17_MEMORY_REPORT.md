# Stage 17 persistent memory

Prithi now stores compact per-browser-user memory in SQLite at `runtime/prithi_memory/prithi_memory.db`. The database and directory are covered by the existing `runtime/` Git ignore rule. The directory is mode `0700` and the database is mode `0600`.

## Schema

- `profiles`: preferred language, optional user-provided display name and timezone, timestamps.
- `relationships`: familiarity, trust, affection, playfulness, romantic tension, current/previous emotion, timestamp.
- `memory_items`: isolated user key, category, concise content, normalized deduplication value, importance, creation and last-used timestamps.

All user values use parameterized SQL. Relationship values are clamped to 0–1. Memory categories are limited to `preference`, `personal_fact`, `relationship_context`, and `conversation_summary`. Each user is limited to 100 items; low-importance/old items are pruned first. Obvious credentials, passwords, payment data, and tokens are rejected. Raw microphone audio and complete raw conversations are not stored by this module.

## Identity and isolation

The browser creates a high-entropy, non-secret identity in local storage and mirrors it into a one-year HTTP-only, SameSite=Strict cookie. Authenticated same-origin API calls send the identity in `X-Prithi-User`; this survives Lightning proxy cookie loss. Only its SHA-256 digest is used as the database user key, and neither value is returned by the public memory API. The existing access-token authentication remains required for every memory API. Session conversation history remains isolated in RAM and expires normally.

## User controls

- Clear conversation: removes only the rolling in-memory conversation and retains relationship/profile/memories.
- Reset relationship: resets only relationship metrics/emotion continuity and retains profile/preferences.
- Delete saved memories: deletes the profile, relationship and memory items for the current browser identity, then creates a clean empty profile. Application configuration and credentials are untouched.
- View memories: shows only the current browser identity's profile, relationship status, count and saved items.

## Validation

- Full suite: 132 tests passed.
- Actual web-process restart: a test identity restored its preferred language, relationship values and three harmless memories after restart.
- Isolation: a different browser identity saw zero memories and no relationship row.
- Cleanup: all synthetic restart-test data was deleted.
- Real Ollama callback (text-only): with `Prefers tea over coffee.` stored, the later coffee message produced: `উফ, কফি? তুমি তো চা খেতে ভালোবাসো, তাই না? আচ্ছা, কি ভাবছো এখন?`
- Health after restart: HTTP 200; Ollama, STT and TTS configuration all healthy.

## Limitations

Memory extraction is deliberately conservative and deterministic. It recognizes only clear stable-preference/name patterns and may miss valid facts; this is safer than saving every utterance. Clearing browser cookies creates a new identity and therefore cannot reconnect to the old memory. Rolling eight-turn dialogue does not survive a server restart. A final human browser microphone callback check remains manual because the server cannot speak into the user's local microphone.
