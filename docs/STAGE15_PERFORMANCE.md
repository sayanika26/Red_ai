# Stage 15 performance report

Method: five saved real-browser Bengali diagnostic WAVs replayed sequentially through the normal HTTP STT → Brain → TTS endpoint. The first run used the original concise guidance and 192-token cap. The second used stricter concise guidance and a 160-token cap. Both used large-v3, gemma3:12b, the existing TTS routing, and brisk pace. Localhost measurements exclude public-proxy latency, browser decoding, and audible playback startup.

| Metric | Before median | After median | After warm-turn median |
|---|---:|---:|---:|
| STT | 1.278s | 1.282s | 1.283s |
| LLM | 3.361s | 3.361s | 3.259s |
| TTS | 6.231s | 3.869s | 4.221s |
| Server total | 10.933s | 9.465s | 8.852s |
| Transcript visible | 1.410s | 1.420s | 1.358s |
| Reply visible | 4.701s | 4.664s | 4.540s |
| Audio ready event | 10.937s | 9.469s | 8.856s |
| WAV fetched and validated | 10.942s | 9.473s | 8.860s |

First optimized turn: Whisper load 2.128s, STT inference 1.282s, LLM 3.361s, TTS 3.496s, total 10.397s. Turns 2–5 reused Whisper with zero model-load time. Ollama was resident before every turn and remained resident under OLLAMA_KEEP_ALIVE=10m.

The largest variable component is Google TTS. Optimized TTS calls ranged from 0.834s for neutral Chirp to 5.405s for expressive Gemini. Shorter voice replies reduced median TTS time, but one response still reached 106 characters and 8.41 seconds of audio, so the LLM does not obey length guidance perfectly.

Regression suite: 89 tests passed.
