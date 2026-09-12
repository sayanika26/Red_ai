# Continuous Conversation Mode

## Scope

This stage adds browser-side, hands-free, turn-based conversation while preserving Manual push-to-talk. It reuses the existing authenticated `/api/voice-turn-stream` pipeline, browser identity, selected language, memory, relationship state, adult-mode state, STT, Brain, and TTS.

It is deliberately half-duplex: the microphone stream remains authorized during a conversation session, but speech detection and recording are inactive while Prithi is processing or speaking.

## Controls and state machine

The Voice panel now has two input modes:

- **Manual** — the existing Start Talking / Stop Talking flow and the default after page load.
- **Conversation** — one Start Conversation action enables automatic turns; Stop Conversation releases the microphone and returns to idle.

The explicit client state machine is:

`IDLE -> WAITING_FOR_SPEECH -> RECORDING_SPEECH -> PROCESSING -> PLAYING_REPLY -> WAITING_FOR_SPEECH`

`PAUSED` and `ERROR` are guarded recovery states. Invalid transitions are ignored. Only one recorder stop and one voice request may be active for a turn.

## Browser VAD

VAD runs locally with `AudioContext`, `AnalyserNode`, and time-domain RMS. No audio is uploaded while waiting in silence. A fresh `MediaRecorder` is created only after three consecutive speech-level frames.

Selected prototype defaults:

| Setting | Value |
|---|---:|
| Speech start RMS | 0.012 |
| Speech continuation/end RMS | 0.007 |
| End silence | 900 ms |
| Minimum voiced duration | 500 ms |
| Maximum turn | 60,000 ms |
| Post-playback guard | 350 ms |

The settings are centralized in `VAD_CONFIG`. A deployment may set `window.PRITHI_VAD_CONFIG` before `app.js` loads to override individual values without scattering magic constants.

The 900 ms silence window intentionally tolerates short pauses inside Bengali sentences. Voiced duration, rather than blob length alone, rejects short noise triggers. The maximum duration closes a turn safely even if silence is never detected.

## Echo and feedback protection

The browser requests these supported media constraints:

- `echoCancellation: true`
- `noiseSuppression: true`
- `autoGainControl: true`
- mono input preference

During `PROCESSING` and `PLAYING_REPLY`, the VAD loop cannot start a recorder. After playback ends, it waits 350 ms before returning to speech detection. **Stop Prithi** interrupts current playback and returns an active conversation to listening after the same guard. True barge-in is intentionally not implemented.

## Failure and lifecycle behavior

- Empty STT, an undersized noise turn, or a turn failure shows “I couldn't catch that. Try again.” and returns to listening without ending Conversation mode.
- One `AbortController` prevents overlapping requests.
- Duplicate recorder completion is blocked by a finishing guard and one-shot stop listener.
- Stopping Conversation aborts the active turn, stops playback, cancels animation/timers, closes the audio context, and stops every microphone track.
- Hiding the browser tab pauses Conversation mode and releases the microphone. Returning to the tab requires an explicit Resume Conversation user gesture.
- An autoplay failure pauses the loop and exposes the existing Play Prithi control. This satisfies mobile browser user-gesture policies.

## Mobile behavior

The existing responsive Voice card is retained. The Manual/Conversation selector and large conversation button are touch-friendly. Android Chrome supports the normal WebM/Opus route. iPhone Safari support depends on its `MediaRecorder` MIME choice; the existing MIME negotiation chooses WebM/Opus, Ogg/Opus, or the browser default. The initial Start Conversation tap resumes `AudioContext` within a user gesture.

## Validation

Automated tests cover:

- Manual mode remains the default and available fallback.
- State inventory and guarded transitions.
- No recorder/upload before speech threshold.
- Minimum speech rejection.
- Silence and maximum-duration completion.
- Single microphone authorization per active conversation.
- Echo-protection constraints.
- Double-submit protection.
- VAD inactivity during playback and guarded return to listening.
- Track/audio-context cleanup.
- Recoverable STT/turn failures.
- Language, browser identity, session, memory, and adult-mode paths remain unchanged.
- Visibility-loss pause behavior.

No automated test calls paid TTS.

## Manual five-turn acceptance test

Use a real browser microphone:

1. Select Bengali and Conversation.
2. Click Start Conversation once.
3. Say “হ্যালো পৃথি, কেমন আছো?” and remain silent; do not press Stop.
4. Wait for playback to finish and the Listening state to return.
5. Say “আজকে সারাদিন অনেক কাজ ছিল।” without touching a control.
6. Continue for at least five turns, then click Stop Conversation.

Record successful turns, false triggers, cutoffs, self-transcriptions, and observed silence-to-submit delay. The expected silence-to-submit delay is approximately 0.9 seconds plus browser recorder-finalization overhead. The target self-transcription count is zero.

## Remaining limitations

- This is browser RMS-based VAD, not semantic or neural endpointing. Very noisy rooms may need threshold tuning.
- The first few tens of milliseconds at speech onset can be lost because continuous pre-roll audio is intentionally not retained.
- There is no barge-in, WebSocket streaming, simultaneous listening, or server-side streaming STT.
- A real five-turn microphone acceptance run requires the user’s browser and voice; it cannot be truthfully simulated by a server-side unit test.

CONTINUOUS CONVERSATION STATUS: IMPLEMENTED — REAL-MIC ACCEPTANCE PENDING
