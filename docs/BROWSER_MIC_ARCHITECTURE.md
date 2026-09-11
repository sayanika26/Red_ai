# Prithi browser microphone architecture

The Lightning Studio runs remotely and cannot directly access the microphone attached to the user's computer. The browser must capture audio locally and send it to the existing Stage 12 audio-file pipeline.

## Planned request flow

```text
Browser microphone permission
        ↓
MediaRecorder or Web Audio capture (mono PCM/WAV preferred)
        ↓
HTTPS upload to a small authenticated Lightning endpoint
        ↓
Temporary server-side audio file
        ↓
prithi_stt.transcribe_audio
        ↓
shared PrithiBrain instance and eight-turn RAM history
        ↓
prithi_voice.generate_voice
        ↓
WAV response returned over HTTPS
        ↓
browser Audio playback
```

## Next implementation stage

Build a small authenticated web client and upload endpoint. The page should request microphone permission only after a user gesture, use manual push-to-talk, upload one complete recording per turn, and play the returned WAV. The server should validate file type and size, use per-session in-memory history, delete temporary input files after processing, and never expose Google or LLM credentials to browser JavaScript.

Streaming and automatic end-of-speech detection are intentionally out of scope for this stage.
