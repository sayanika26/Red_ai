const statusEl = document.querySelector("#status");
const talkButton = document.querySelector("#talk");
const resetButton = document.querySelector("#reset");
const memoryViewButton = document.querySelector("#memory-view");
const memoryPanel = document.querySelector("#memory-panel");
const memoryCloseButton = document.querySelector("#memory-close");
const memoryStatus = document.querySelector("#memory-status");
const memoryList = document.querySelector("#memory-list");
const relationshipResetButton = document.querySelector("#relationship-reset");
const memoryDeleteButton = document.querySelector("#memory-delete");
const stopPlaybackButton = document.querySelector("#stop-playback");
const playButton = document.querySelector("#play");
const languageEl = document.querySelector("#language");
languageEl.value = "bengali";
function showSelectedLanguage() {
  const codes = {bengali: "bn", hindi: "hi", english: "en", auto: "auto"};
  document.querySelector("#language-debug").textContent = `Selected: ${languageEl.value} · Whisper: ${codes[languageEl.value]} · Forced: ${languageEl.value === "auto" ? "no" : "yes"}`;
}
window.addEventListener("pageshow", showSelectedLanguage);
languageEl.addEventListener("change", showSelectedLanguage);
const transcriptEl = document.querySelector("#transcript");
const replyEl = document.querySelector("#reply");
const emotionEl = document.querySelector("#emotion");
const latencyEl = document.querySelector("#latency");
const errorEl = document.querySelector("#error");
const conversationFeed = document.querySelector("#conversation-feed");
const currentTurn = document.querySelector("#current-turn");
const emptyState = document.querySelector("#empty-state");
const profileEmotion = document.querySelector("#profile-emotion");
const profilePresence = document.querySelector("#profile-presence");
const recordingTime = document.querySelector("#recording-time");
const micMeterFill = document.querySelector("#mic-meter-fill");
const adultModeStatusEl = document.querySelector("#adult-mode-status");
const adultModeBadgeEl = document.querySelector("#adult-mode-badge");
const adultAgeStepEl = document.querySelector("#adult-age-step");
const adultOptInStepEl = document.querySelector("#adult-opt-in-step");
const adultDisableButton = document.querySelector("#adult-disable");
let adultModeState = null;

let recorder = null;
let stream = null;
let chunks = [];
let stopTimer = null;
let responseAudio = null;
let responseObjectUrl = null;
let activeTurnController = null;
let discardRecording = false;
let diagnosticMode = false;
let diagnosticReferences = [];
let recordingStarted = 0;
let meterContext = null;
let meterFrame = null;
let starting = false;
let currentTurnComplete = false;

const statusStage = {
  recording: "recording",
  transcribing: "transcribing",
  thinking: "thinking",
  speaking: "speaking",
  generating: "thinking",
};

function setTalkState(isRecording) {
  const title = talkButton.querySelector(".talk-copy strong");
  const subtitle = talkButton.querySelector(".talk-copy small");
  if (title) title.textContent = isRecording ? "Stop Talking" : "Start Talking";
  if (subtitle) subtitle.textContent = isRecording ? "Tap to finish your thought" : "Tap when you’re ready";
  talkButton.setAttribute("aria-label", isRecording ? "Stop talking" : "Start talking");
}

function updateStageTrack(state) {
  const order = ["recording", "transcribing", "thinking", "speaking"];
  const active = statusStage[state] || null;
  const activeIndex = active ? order.indexOf(active) : -1;
  document.querySelectorAll(".stage-track [data-stage]").forEach((item) => {
    const index = order.indexOf(item.dataset.stage);
    item.classList.toggle("active", index === activeIndex);
    item.classList.toggle("done", activeIndex > index || (state === "idle" && currentTurnComplete));
  });
}

function scrollConversation() {
  requestAnimationFrame(() => conversationFeed.scrollTo({ top: conversationFeed.scrollHeight, behavior: "smooth" }));
}

function makeArchivedTurn(userText, prithiText, emotion, latency) {
  const wrapper = document.createElement("article");
  wrapper.className = "history-turn";
  const addRow = (role, text, meta = "") => {
    const row = document.createElement("div");
    row.className = `bubble-row ${role === "You" ? "user-row" : "prithi-row"}`;
    const avatar = document.createElement("div");
    avatar.className = `bubble-avatar ${role === "You" ? "user-avatar" : "prithi-avatar"}`;
    avatar.textContent = role[0];
    avatar.setAttribute("aria-hidden", "true");
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role === "You" ? "user-bubble" : "prithi-bubble"}`;
    const heading = document.createElement("div");
    heading.className = "bubble-heading";
    const label = document.createElement("span");
    label.textContent = role;
    const small = document.createElement("small");
    small.textContent = meta;
    const message = document.createElement("p");
    message.className = "message";
    message.textContent = text;
    heading.append(label, small);
    bubble.append(heading, message);
    row.append(avatar, bubble);
    wrapper.append(row);
  };
  addRow("You", userText, "Transcript");
  addRow("Prithi", prithiText, `${emotion || "neutral"} · ${latency || "—"}`);
  return wrapper;
}

function archiveCurrentTurn() {
  if (!currentTurnComplete || transcriptEl.classList.contains("muted") || replyEl.classList.contains("muted")) return;
  conversationFeed.insertBefore(
    makeArchivedTurn(transcriptEl.textContent, replyEl.textContent, emotionEl.textContent, latencyEl.textContent),
    currentTurn,
  );
  currentTurnComplete = false;
}

function beginLiveTurn() {
  archiveCurrentTurn();
  emptyState.classList.add("hidden");
  currentTurn.classList.remove("hidden");
  replyEl.textContent = "Prithi is thinking…";
  replyEl.classList.add("muted");
  emotionEl.textContent = "—";
  latencyEl.textContent = "—";
  document.querySelector("#reply-stage").textContent = "Thinking";
}

function stopMeter() {
  cancelAnimationFrame(meterFrame);
  meterContext?.close();
  meterContext = null;
  micMeterFill.style.width = "4%";
}

function startMeter(mediaStream) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;
  meterContext = new AudioContextClass();
  const analyser = meterContext.createAnalyser();
  analyser.fftSize = 2048;
  meterContext.createMediaStreamSource(mediaStream).connect(analyser);
  const data = new Float32Array(analyser.fftSize);
  function tick() {
    analyser.getFloatTimeDomainData(data);
    const rms = Math.sqrt(data.reduce((sum, value) => sum + value * value, 0) / data.length);
    const level = rms < 0.00316 ? "Low" : rms > 0.25 ? "High" : "Good";
    const elapsed = ((performance.now() - recordingStarted) / 1000).toFixed(1);
    document.querySelector("#mic-level").textContent = `Microphone ${level.toLowerCase()}`;
    recordingTime.textContent = `${elapsed}s`;
    micMeterFill.style.width = `${Math.max(4, Math.min(100, rms * 360))}%`;
    meterFrame = requestAnimationFrame(tick);
  }
  tick();
}

function setStatus(label, state = "idle") {
  statusEl.querySelector(".status-label").textContent = label;
  statusEl.dataset.state = state;
  document.body.dataset.status = state;
  profilePresence.textContent = label;
  document.querySelector("#reply-stage").textContent = label;
  updateStageTrack(state);
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
  setStatus("Error", "error");
  document.querySelector("#retry").classList.remove("hidden");
}

function clearError() {
  errorEl.textContent = "";
  errorEl.classList.add("hidden");
}

function accessToken() {
  let token = sessionStorage.getItem("prithiAccessToken");
  if (!token) {
    token = window.prompt("Enter your Prithi access token:") || "";
    if (token) sessionStorage.setItem("prithiAccessToken", token);
  }
  return token;
}

function browserIdentity() {
  let identity = localStorage.getItem("prithiBrowserIdentity");
  if (!identity || !/^[A-Za-z0-9_-]{32,128}$/.test(identity)) {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    identity = btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
    localStorage.setItem("prithiBrowserIdentity", identity);
  }
  return identity;
}

function authHeaders() {
  const token = accessToken();
  return token ? { Authorization: `Bearer ${token}`, "X-Prithi-User": browserIdentity() } : {};
}

function renderAdultMode(state) {
  adultModeState = state;
  const enabled = state.conversation_mode === "adult" && state.adult_opt_in;
  adultModeBadgeEl.textContent = enabled ? "Adult" : "Normal";
  adultModeBadgeEl.dataset.mode = enabled ? "adult" : "normal";
  document.body.dataset.mode = enabled ? "adult" : "normal";
  adultModeStatusEl.textContent = `${enabled ? "Adult mode" : "Normal mode"} · ${state.selected_model || "model unavailable"}`;
  adultAgeStepEl.classList.toggle("hidden", state.age_confirmed);
  adultOptInStepEl.classList.toggle("hidden", !state.age_confirmed || enabled);
  adultDisableButton.classList.toggle("hidden", !enabled);
}

async function loadAdultMode() {
  const response = await fetch("/api/adult-mode", { headers: authHeaders() });
  if (!response.ok) throw new Error(await apiError(response));
  const state = await response.json();
  renderAdultMode(state);
  return state;
}

async function updateAdultMode(path, body = null) {
  const headers = authHeaders();
  if (body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: "POST",
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(await apiError(response));
  renderAdultMode(await response.json());
}

async function apiError(response) {
  try {
    const body = await response.json();
    if (body.reply) {
      transcriptEl.textContent = body.transcript || "—";
      replyEl.textContent = body.reply;
      emotionEl.textContent = body.emotion || "—";
    }
    return body.detail || body.error || `Request failed (${response.status})`;
  } catch (_) {
    return `Request failed (${response.status})`;
  }
}

async function checkHealth() {
  const token = accessToken();
  if (!token) {
    showError("An access token is required.");
    return;
  }
  try {
    const response = await fetch("/api/health", { headers: authHeaders() });
    if (response.status === 401) sessionStorage.removeItem("prithiAccessToken");
    if (!response.ok) throw new Error(await apiError(response));
    const health = await response.json();
    if (!health.ollama || !health.stt || !health.tts_configured) {
      throw new Error("Prithi runtime is not fully ready. Check Ollama, STT, and TTS configuration.");
    }
    document.querySelector("#version").textContent = health.version ? `v${health.version}` : "v—";
    setStatus("Ready");
    await loadMemory(false);
    await loadAdultMode();
    const diagnostics = await fetch("/api/stt-diagnostics", { headers: authHeaders() });
    if (diagnostics.ok) {
      const settings = await diagnostics.json();
      diagnosticMode = settings.enabled;
      diagnosticReferences = settings.references;
      document.querySelector("#diagnostics").classList.toggle("hidden", !diagnosticMode);
      document.querySelector("#diagnostic-reference").value = diagnosticReferences[settings.saved_samples] || "";
      document.querySelector("#diagnostic-progress").textContent = `Sample ${settings.saved_samples + 1} of 5`;
    }
  } catch (error) {
    showError(error.message);
  }
}

async function loadMemory(showPanel = true) {
  const response = await fetch("/api/memory", { headers: authHeaders() });
  if (!response.ok) throw new Error(await apiError(response));
  const memory = await response.json();
  const preferred = memory.profile?.preferred_language;
  if (preferred && [...languageEl.options].some((option) => option.value === preferred)) {
    languageEl.value = preferred;
    showSelectedLanguage();
  }
  memoryStatus.textContent = `Persistent memory: on · Saved items: ${memory.saved_memory_count} · Relationship restored: ${memory.relationship_restored ? "yes" : "no"}`;
  memoryList.replaceChildren();
  for (const item of memory.memories) {
    const entry = document.createElement("li");
    entry.textContent = `${item.category}: ${item.content}`;
    memoryList.append(entry);
  }
  if (!memory.memories.length) {
    const empty = document.createElement("li");
    empty.textContent = "No saved facts or preferences yet.";
    memoryList.append(empty);
  }
  memoryPanel.classList.toggle("hidden", !showPanel);
  memoryPanel.setAttribute("aria-hidden", showPanel ? "false" : "true");
  document.body.classList.toggle("drawer-open", showPanel);
  return memory;
}

function closeMemory() {
  memoryPanel.classList.add("hidden");
  memoryPanel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("drawer-open");
}

function preferredMimeType() {
  const choices = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm"];
  return choices.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

async function startRecording() {
  clearError();
  if (starting || activeTurnController) return;
  if (diagnosticMode && !document.querySelector("#diagnostic-consent").checked) {
    showError("Check the diagnostic recording consent box before starting.");
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    showError("This browser does not support microphone recording.");
    return;
  }
  try {
    starting = true;
    talkButton.disabled = true;
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = preferredMimeType();
    recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    chunks = [];
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) chunks.push(event.data);
    });
    discardRecording = false;
    recorder.addEventListener("stop", () => {
      stopMeter();
      stream?.getTracks().forEach((track) => track.stop());
      if (discardRecording) {
        chunks = [];
        setStatus("Ready");
        talkButton.disabled = false;
      } else {
        sendRecording();
      }
    }, { once: true });
    recorder.addEventListener("start", () => {
      recordingStarted = performance.now();
      startMeter(stream);
      talkButton.disabled = false;
      starting = false;
    }, { once: true });
    recorder.start();
    setStatus("Recording", "recording");
    setTalkState(true);
    stopTimer = window.setTimeout(stopRecording, 60000);
  } catch (error) {
    starting = false;
    talkButton.disabled = false;
    stream?.getTracks().forEach((track) => track.stop());
    const message = error.name === "NotAllowedError"
      ? "Microphone permission was denied. Allow microphone access and try again."
      : "No usable microphone was found.";
    showError(message);
  }
}

function stopRecording() {
  window.clearTimeout(stopTimer);
  talkButton.disabled = true;
  if (recorder?.state === "recording") recorder.stop();
  setTalkState(false);
  setStatus("Transcribing", "transcribing");
}

async function sendRecording() {
  const mimeType = recorder?.mimeType || "audio/webm";
  const blob = new Blob(chunks, { type: mimeType });
  chunks = [];
  if (!blob.size) {
    showError("The recording was empty. Please try again.");
    talkButton.disabled = false;
    return;
  }
  const form = new FormData();
  form.append("audio", blob, "recording");
  form.append("language", languageEl.value);
  setStatus("Transcribing", "transcribing");
  activeTurnController = new AbortController();
  try {
    if (diagnosticMode) {
      form.set("language", "bengali");
      form.append("consent", "true");
      form.append("reference", document.querySelector("#diagnostic-reference").value);
      const response = await fetch("/api/stt-diagnostics", {
        method: "POST", headers: authHeaders(), body: form, signal: activeTurnController.signal,
      });
      if (!response.ok) throw new Error(await apiError(response));
      const result = await response.json();
      const details = document.createElement("pre");
      const lines = [`Sample ${result.sample_number}`, `Duration: ${result.audio.duration.toFixed(2)}s`,
        `Level: ${result.audio.level} (${result.audio.rms_dbfs} dBFS)`,
        `Browser MIME: ${result.browser_mime}`, `Forced language: ${result.forced_language}`];
      for (const [name, item] of Object.entries(result.results)) {
        lines.push(`${name}: ${item.raw_transcript || "[empty]"}`, `STT: ${item.transcription_time.toFixed(2)}s · Segments: ${item.segment_count} · ${item.text.trim() ? "valid" : "empty"}`);
        if (item.equivalent_to) lines.push(item.equivalent_to);
      }
      details.textContent = lines.join("\n");
      document.querySelector("#diagnostic-results").append(details);
      document.querySelector("#diagnostic-reference").value = diagnosticReferences[result.sample_number] || "";
      document.querySelector("#diagnostic-progress").textContent = result.sample_number >= 5
        ? "Five samples saved. Return to Codex to review the results."
        : `Sample ${result.sample_number + 1} of 5`;
      document.querySelector("#diagnostic-consent").checked = false;
      setStatus("Ready");
      return;
    }
    const response = await fetch("/api/voice-turn-stream", {
      method: "POST",
      headers: authHeaders(),
      body: form,
      signal: activeTurnController.signal,
    });
    if (!response.ok) throw new Error(await apiError(response));
    if (!response.body) throw new Error("This browser cannot read progress events.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const line = block.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        await handleProgress(JSON.parse(line.slice(6)));
      }
      if (done) break;
    }
  } catch (error) {
    if (error.name === "AbortError") setStatus("Ready");
    else showError(error.message);
  } finally {
    activeTurnController = null;
    talkButton.disabled = false;
    setTalkState(false);
  }
}

async function handleProgress(event) {
  if (event.event === "language") {
    document.querySelector("#language-debug").textContent = `Requested: ${event.requested_language} · Resolved: ${event.resolved_language} · Whisper: ${event.whisper_language || "auto"} · Forced: ${event.forced ? "yes" : "no"}`;
  } else if (event.event === "transcript") {
    beginLiveTurn();
    document.querySelector("#language-debug").textContent += ` · Model: ${event.model || "unknown"} · Quality: passed · Fallback: ${event.fallback_used ? "yes" : "no"} · STT: ${Number(event.stt_time).toFixed(2)}s`;
    transcriptEl.textContent = event.text;
    transcriptEl.classList.remove("muted");
    setStatus("Thinking", "thinking");
    scrollConversation();
  } else if (event.event === "thinking") {
    setStatus("Thinking", "thinking");
  } else if (event.event === "reply") {
    setStatus("Generating voice", "thinking");
    document.querySelector("#language-debug").textContent += ` · Preferred reply: ${event.preferred_reply_language || "auto"} · Brain: ${event.brain_returned_language} · Validated: ${event.validated_reply_language}`;
    if (event.relationship_state) {
      const r = event.relationship_state;
      document.querySelector("#relationship-debug").textContent = `Emotion: ${event.current_emotion} · Previous: ${event.previous_emotion} · Familiarity: ${Number(r.familiarity).toFixed(2)} · Trust: ${Number(r.trust).toFixed(2)} · Affection: ${Number(r.affection).toFixed(2)} · Playfulness: ${Number(r.playfulness).toFixed(2)} · Romantic tension: ${Number(r.romantic_tension).toFixed(2)} · Question: ${event.question_used ? "yes" : "no"} · Memory candidates: ${event.memory_candidate_count ?? 0} · Saved: ${event.memory_saved_count ?? 0}`;
    }
    if (!memoryPanel.classList.contains("hidden")) await loadMemory(true);
    replyEl.textContent = event.text;
    replyEl.classList.remove("muted");
    emotionEl.textContent = event.emotion;
    profileEmotion.textContent = event.emotion ? event.emotion[0].toUpperCase() + event.emotion.slice(1) : "Calm";
    scrollConversation();
    if (event.selected_model) {
      const mode = event.conversation_mode === "adult" ? "Adult" : "Normal";
      adultModeStatusEl.textContent = `${mode} mode · ${event.selected_model} · Switch: ${event.model_switch_occurred ? `${Number(event.model_switch_latency).toFixed(2)}s` : "no"}`;
    }
    if (event.adult_mode_disabled) await loadAdultMode();
  } else if (event.event === "audio_ready") {
    document.querySelector("#language-debug").textContent += ` · TTS locale: ${event.tts_locale || "unknown"} · LLM: ${Number(event.llm_time).toFixed(2)}s · TTS: ${Number(event.tts_time).toFixed(2)}s`;
    latencyEl.textContent = `${Number(event.total_time).toFixed(2)}s`;
    currentTurnComplete = true;
    scrollConversation();
    await prepareAndPlay(event.audio_url);
  } else if (event.event === "error") {
    throw new Error(event.message || "Prithi could not complete this turn.");
  }
}

async function prepareAndPlay(audioUrl) {
  const response = await fetch(audioUrl, {
    headers: authHeaders(),
    signal: activeTurnController?.signal,
  });
  if (!response.ok) throw new Error(await apiError(response));
  const blob = await response.blob();
  if (responseObjectUrl) URL.revokeObjectURL(responseObjectUrl);
  responseObjectUrl = URL.createObjectURL(blob);
  responseAudio = new Audio(responseObjectUrl);
  responseAudio.addEventListener("ended", () => setStatus("Ready"), { once: true });
  setStatus("Speaking", "speaking");
  try {
    await responseAudio.play();
    playButton.classList.add("hidden");
  } catch (_) {
    setStatus("Ready");
    playButton.classList.remove("hidden");
    showError("Autoplay was blocked. Tap “Play Prithi” to hear the response.");
  }
}

talkButton.addEventListener("click", () => {
  if (recorder?.state === "recording") stopRecording();
  else startRecording();
});

stopPlaybackButton.addEventListener("click", () => {
  window.clearTimeout(stopTimer);
  if (recorder?.state === "recording") {
    discardRecording = true;
    recorder.stop();
    stream?.getTracks().forEach((track) => track.stop());
    setTalkState(false);
  }
  activeTurnController?.abort();
  if (responseAudio) {
    responseAudio.pause();
    responseAudio.currentTime = 0;
  }
  playButton.classList.add("hidden");
  setStatus("Ready");
});

playButton.addEventListener("click", async () => {
  if (!responseAudio) return;
  clearError();
  setStatus("Speaking", "speaking");
  await responseAudio.play();
});

resetButton.addEventListener("click", async () => {
  clearError();
  try {
    const response = await fetch("/api/memory/reset-conversation", { method: "POST", headers: authHeaders() });
    if (!response.ok) throw new Error(await apiError(response));
    conversationFeed.querySelectorAll(".history-turn").forEach((turn) => turn.remove());
    currentTurn.classList.add("hidden");
    emptyState.classList.remove("hidden");
    currentTurnComplete = false;
    transcriptEl.textContent = "Your words will appear here.";
    transcriptEl.classList.add("muted");
    replyEl.textContent = "Prithi’s reply will appear here.";
    replyEl.classList.add("muted");
    emotionEl.textContent = "—";
    latencyEl.textContent = "—";
    profileEmotion.textContent = "Calm";
    setStatus("Ready");
  } catch (error) {
    showError(error.message);
  }
});

memoryViewButton.addEventListener("click", async () => {
  clearError();
  try {
    if (!memoryPanel.classList.contains("hidden")) {
      closeMemory();
      return;
    }
    await loadMemory(true);
  } catch (error) {
    showError(error.message);
  }
});

memoryCloseButton.addEventListener("click", closeMemory);
memoryPanel.addEventListener("click", (event) => {
  if (event.target === memoryPanel) closeMemory();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !memoryPanel.classList.contains("hidden")) closeMemory();
});

relationshipResetButton.addEventListener("click", async () => {
  if (!window.confirm("Reset Prithi's relationship metrics for this browser identity? Saved preferences will remain.")) return;
  clearError();
  try {
    const response = await fetch("/api/memory/reset-relationship", { method: "POST", headers: authHeaders() });
    if (!response.ok) throw new Error(await apiError(response));
    await loadMemory(true);
    document.querySelector("#relationship-debug").textContent = "Emotion: neutral · Relationship metrics reset.";
  } catch (error) {
    showError(error.message);
  }
});

memoryDeleteButton.addEventListener("click", async () => {
  if (!window.confirm("Delete all saved Prithi memories and relationship state for this browser identity?")) return;
  clearError();
  try {
    const response = await fetch("/api/memory", { method: "DELETE", headers: authHeaders() });
    if (!response.ok) throw new Error(await apiError(response));
    await loadMemory(true);
    await loadAdultMode();
    document.querySelector("#relationship-debug").textContent = "Emotion: neutral · Saved memory deleted.";
  } catch (error) {
    showError(error.message);
  }
});

document.querySelector("#adult-age-submit").addEventListener("click", async () => {
  if (!document.querySelector("#adult-age-confirm").checked) {
    showError("Confirm that you are 18 or older before continuing.");
    return;
  }
  clearError();
  try {
    await updateAdultMode("/api/adult-mode/confirm-age", { confirmed: true });
  } catch (error) {
    showError(error.message);
  }
});

document.querySelector("#adult-enable").addEventListener("click", async () => {
  clearError();
  try {
    await updateAdultMode("/api/adult-mode/enable", { enabled: true });
  } catch (error) {
    showError(error.message);
  }
});

adultDisableButton.addEventListener("click", async () => {
  clearError();
  try {
    await updateAdultMode("/api/adult-mode/disable");
  } catch (error) {
    showError(error.message);
  }
});

checkHealth();
document.querySelector("#retry").addEventListener("click", () => {
  document.querySelector("#retry").classList.add("hidden");
  startRecording();
});
