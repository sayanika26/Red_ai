# Sentence-chunk TTS design

Stage 15 keeps whole-response TTS because Prithi's language, emotion, voice style, and complete reply are delivered inside one structured JSON object. Starting TTS before that object validates could speak malformed or incorrectly routed content.

The future stable interface should accept an already validated `BrainReply`, segment only its `reply`, and return an ordered sequence of audio records:

```text
validated BrainReply
  -> language-aware sentence segmenter
  -> synthesize_chunk(index, text, language, emotion)
  -> session-bound ordered audio IDs
  -> browser playback queue
```

The segmenter must recognize Bengali danda punctuation, Hindi danda punctuation, Latin sentence punctuation, decimal numbers, common abbreviations, and URLs. It must never split an unvalidated JSON stream. The browser queue must play by monotonically increasing index, stop immediately on user cancellation, skip no successful earlier chunk when a later chunk fails, and release object URLs after playback.

This design is intentionally not enabled until it can be tested across Bengali, Hindi, English, and code-switched replies without unnatural gaps.
