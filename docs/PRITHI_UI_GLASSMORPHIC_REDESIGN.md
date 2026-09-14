# Prithi glassmorphic UI redesign

## What changed

Prithi now uses a wide two-column companion layout with a liquid-glass control rail and a conversation-first main surface. The existing profile, language, manual/conversation voice modes, microphone controls, adult-mode gate, memories, relationship reset, diagnostics, authentication and health behavior remain in place.

The main experience adds a lightweight CSS neural orb. Its glow and motion are driven by the existing body status state: idle breathes gently, recording brightens, thinking rotates faster, and speaking pulses. Reduced-motion preferences disable the animation. Adult mode changes only the orb's accent warmth; it does not alter gating.

## Text chat

`POST /api/text-turn` accepts authenticated form fields `text`, `language`, and `voice_reply`. It reuses the same browser identity, session pipeline, model router, memory prompt, relationship state, adult-mode state and optional TTS path as voice turns. It does not expose local paths. Generated speech is served through the existing short-lived safe audio-ID route.

The composer supports Enter to send, Shift+Enter for a newline, a text-only/text-plus-voice toggle, a microphone shortcut, multiline auto-sizing, and starter suggestions. Typed and spoken turns render in the same conversation feed.

## Responsive behavior

Desktop keeps a full-width control rail plus conversation workspace. On narrow screens the conversation becomes the first section, controls stack below it, the orb compacts, and the composer remains touch-friendly and sticky above the safe-area inset. No horizontal scrolling is required.

## Files

- `app/web/index.html`: orb, shared composer, suggestion actions.
- `app/web/styles.css`: glass tokens, state animations, composer and responsive rules.
- `app/web/app.js`: typed-message interaction, audio option, status/orb synchronization.
- `app/prithi_web.py`: minimal typed-message endpoint using existing services.
- `app/test_prithi_web.py`: endpoint, auth, safe audio and UI contract coverage.

## Limitations

- Text replies are request/response rather than token-streamed.
- The orb reacts to application states and voice meter state, not audio-frequency particles.
- Conversation history remains in the existing in-memory/session design; no new persistence is introduced.
