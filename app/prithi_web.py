import os
import asyncio
import json
import inspect
import logging
from logging.handlers import RotatingFileHandler
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from llm_provider import OpenAICompatibleBackend
from prithi_brain import PrithiBrain, RelationshipState
from prithi_chat import load_local_env
from prithi_memory import (
    DEFAULT_DB_PATH,
    MemoryStore,
    extract_display_name,
    extract_memory_candidates,
    save_candidates,
    stable_user_id,
)
from prithi_model_router import (
    ADULT_MODE,
    DEFAULT_ADULT_MODEL,
    DEFAULT_NORMAL_MODEL,
    NORMAL_MODE,
    PrithiModelRouter,
    adult_mode_status,
)
from prithi_stt import MODEL_PATH, SUPPORTED_LANGUAGES, language_code
from prithi_transcript_quality import assess_transcript, RETRY_MESSAGE
from prithi_voice_chat import PrithiVoicePipeline
from prithi_stt_diagnostics import register_diagnostics
from prithi_context import TurnContext, analyze_context
from prithi_learning import LearningStore, learning_signal, prompt_for_behaviors
from prithi_mood import MoodState, MoodStore, blend_voice_style, update_mood
from prithi_roleplay import RoleplayState
from prithi_strategy import compose_adaptive_prompt, select_strategy


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
VERSION_FILE = PROJECT_DIR / "VERSION"
WEB_DIR = APP_DIR / "web"
WEB_AUDIO_DIR = PROJECT_DIR / "runtime" / "web" / "audio"
SESSION_COOKIE = "prithi_session"
USER_COOKIE = "prithi_user"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
AUDIO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,128}$")
TIMING_LOG = PROJECT_DIR / "runtime" / "web" / "timings.jsonl"
ALLOWED_AUDIO_TYPES = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
}


@dataclass(frozen=True)
class WebConfig:
    access_token: str
    max_upload_bytes: int = 25 * 1024 * 1024
    max_recording_seconds: float = 60.0
    audio_ttl_seconds: float = 30 * 60
    session_ttl_seconds: float = 4 * 60 * 60

    @classmethod
    def from_environment(cls) -> "WebConfig":
        return cls(access_token=os.environ.get("PRITHI_WEB_ACCESS_TOKEN", "").strip())


@dataclass
class SessionState:
    pipeline: PrithiVoicePipeline
    lock: threading.Lock
    last_used: float
    user_id: str
    relationship_restored: bool = False
    adult_opt_in: bool = False
    mood: MoodState | None = None
    roleplay: RoleplayState | None = None
    adaptive_debug: dict[str, Any] | None = None


@dataclass
class AudioState:
    path: Path
    session_id: str
    expires_at: float


def _timing_logger() -> logging.Logger:
    logger = logging.getLogger("prithi.web.timings")
    if not logger.handlers:
        TIMING_LOG.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(TIMING_LOG, maxBytes=2_000_000, backupCount=2)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_timing(**values: Any) -> None:
    _timing_logger().info(json.dumps(values, ensure_ascii=False, separators=(",", ":")))


def _default_pipeline_factory(model_router: PrithiModelRouter | None = None) -> PrithiVoicePipeline:
    router = model_router or PrithiModelRouter.from_environment()
    router.normal_backend.verify_model_available()
    return PrithiVoicePipeline(
        PrithiBrain(router.normal_backend, history_turns=8),
        model_router=router,
    )


def _default_health() -> dict[str, bool]:
    base_url = os.environ.get("PRITHI_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
    api_key = os.environ.get("PRITHI_LLM_API_KEY", "")
    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=3.0,
        )
        ollama = response.is_success
    except httpx.HTTPError:
        ollama = False
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    return {
        "ollama": ollama,
        "stt": (MODEL_PATH / "model.bin").is_file(),
        "tts_configured": bool(credentials and Path(credentials).is_file()),
    }


def convert_to_pcm_wav(source: Path, destination: Path, max_seconds: float) -> tuple[float, float]:
    started = time.perf_counter()
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
            check=True,
            capture_output=True,
            timeout=90,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise ValueError("Uploaded audio could not be decoded") from exc
    try:
        with wave.open(str(destination), "rb") as wav_file:
            duration = wav_file.getnframes() / wav_file.getframerate()
    except (wave.Error, OSError, ZeroDivisionError) as exc:
        raise ValueError("Converted recording is not a valid WAV") from exc
    if duration <= 0:
        raise ValueError("Recording is empty")
    if duration > max_seconds:
        raise ValueError(f"Recording exceeds the {int(max_seconds)} second limit")
    return time.perf_counter() - started, duration


def create_app(
    config: WebConfig | None = None,
    pipeline_factory: Callable[[], PrithiVoicePipeline] = _default_pipeline_factory,
    health_checker: Callable[[], dict[str, bool]] = _default_health,
    converter: Callable[[Path, Path, float], tuple[float, float]] = convert_to_pcm_wav,
    memory_store: MemoryStore | None = None,
    model_router: PrithiModelRouter | None = None,
) -> FastAPI:
    web_config = config or WebConfig.from_environment()
    app = FastAPI(title="Prithi Voice", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions: dict[str, SessionState] = {}
    app.state.audio_files: dict[str, AudioState] = {}
    app.state.state_lock = threading.Lock()
    app.state.memory = memory_store or MemoryStore(DEFAULT_DB_PATH)
    app.state.moods = MoodStore(app.state.memory.db_path)
    app.state.learning = LearningStore(app.state.memory.db_path)
    if pipeline_factory is _default_pipeline_factory:
        app.state.model_router = model_router
        def create_default_pipeline() -> PrithiVoicePipeline:
            if app.state.model_router is None:
                app.state.model_router = PrithiModelRouter.from_environment()
            return _default_pipeline_factory(app.state.model_router)
        app.state.pipeline_factory = create_default_pipeline
    else:
        app.state.model_router = model_router
        app.state.pipeline_factory = pipeline_factory
    WEB_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    def cleanup_expired() -> None:
        now = time.time()
        with app.state.state_lock:
            old_sessions = [key for key, value in app.state.sessions.items() if now - value.last_used > web_config.session_ttl_seconds]
            for key in old_sessions:
                app.state.sessions.pop(key, None)
            old_audio = [key for key, value in app.state.audio_files.items() if value.expires_at <= now]
            for key in old_audio:
                record = app.state.audio_files.pop(key, None)
                if record:
                    record.path.unlink(missing_ok=True)

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not web_config.access_token:
            raise HTTPException(status_code=503, detail="Web access token is not configured")
        scheme, _, supplied = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not supplied or not secrets.compare_digest(supplied, web_config.access_token):
            raise HTTPException(status_code=401, detail="Valid access token required", headers={"WWW-Authenticate": "Bearer"})

    def current_session(request: Request, response: Response) -> str:
        session_id = request.cookies.get(SESSION_COOKIE, "")
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            session_id = secrets.token_urlsafe(32)
            response.set_cookie(
                SESSION_COOKIE,
                session_id,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
                max_age=int(web_config.session_ttl_seconds),
            )
        return session_id

    def browser_identity(request: Request, supplied_identity: str | None = None) -> tuple[str, bool]:
        identity = (supplied_identity or "").strip() or request.cookies.get(USER_COOKIE, "")
        if not SESSION_ID_PATTERN.fullmatch(identity):
            return secrets.token_urlsafe(32), True
        return identity, identity != request.cookies.get(USER_COOKIE, "")

    def set_user_cookie(response: Response, request: Request, identity: str) -> None:
        response.set_cookie(
            USER_COOKIE,
            identity,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            max_age=365 * 24 * 60 * 60,
        )

    def current_user(
        request: Request,
        response: Response,
        x_prithi_user: str | None = Header(default=None, alias="X-Prithi-User"),
    ) -> str:
        identity, created = browser_identity(request, x_prithi_user)
        if created:
            set_user_cookie(response, request, identity)
        user_id = stable_user_id(identity)
        app.state.memory.ensure_profile(user_id)
        return user_id

    def get_session(session_id: str, user_id: str) -> SessionState:
        cleanup_expired()
        with app.state.state_lock:
            state = app.state.sessions.get(session_id)
            if state is None or state.user_id != user_id:
                pipeline = app.state.pipeline_factory()
                restored = app.state.memory.load_relationship(user_id)
                relationship_restored = False
                brain = getattr(pipeline, "brain", None)
                if restored and brain is not None:
                    brain.relationship_state = RelationshipState(**{
                        key: float(restored[key]) for key in (
                            "familiarity", "trust", "affection", "playfulness", "romantic_tension"
                        )
                    })
                    brain.current_emotion = str(restored.get("current_emotion", "neutral"))
                    brain.previous_emotion = str(restored.get("previous_emotion", "neutral"))
                    relationship_restored = True
                state = SessionState(
                    pipeline, threading.Lock(), time.time(), user_id, relationship_restored, False,
                    app.state.moods.load(user_id), RoleplayState(), None,
                )
                app.state.sessions[session_id] = state
            state.last_used = time.time()
            return state

    def prepare_adaptive_turn(state: SessionState, transcript: str, language: str, conversation_mode: str) -> str:
        context = analyze_context(transcript, language if language != "auto" else None)
        if state.roleplay is None:
            state.roleplay = RoleplayState()
        state.roleplay.apply_boundary(context.boundary_signal)
        memories = app.state.memory.relevant_memories(state.user_id, transcript, limit=6)
        tags = [context.user_intent, context.user_emotion, context.user_need, context.language]
        learned = app.state.learning.relevant(state.user_id, tags, limit=3)
        strategy = select_strategy(
            context,
            adult_mode=conversation_mode == ADULT_MODE,
            has_relevant_memory=bool(memories),
        )
        state.mood = state.mood or app.state.moods.load(state.user_id)
        next_mood = update_mood(state.mood, context, strategy, adult_mode=conversation_mode == ADULT_MODE)
        state.adaptive_debug = {
            "context": context.as_dict(), "response_strategy": strategy,
            "mood": next_mood.as_dict(), "roleplay_active": bool(state.roleplay.active),
            "relevant_memory_count": len(memories), "learned_behavior_count": len(learned),
            "_transcript": transcript,
        }
        brain = getattr(state.pipeline, "brain", None)
        relationship = brain.relationship_state.as_dict() if brain is not None else {}
        return compose_adaptive_prompt(
            context=context, strategy=strategy, mood=next_mood.as_dict(), relationship=relationship,
            roleplay_prompt=state.roleplay.prompt(), learned_prompt=prompt_for_behaviors(learned),
            adult_mode=conversation_mode == ADULT_MODE,
        )

    def finalize_adaptive_turn(state: SessionState, brain: dict[str, Any]) -> None:
        debug = state.adaptive_debug or {}
        mood_values = debug.get("mood")
        if mood_values:
            state.mood = MoodState(**mood_values)
            app.state.moods.save(state.user_id, state.mood)
            brain["voice_style"] = blend_voice_style(brain.get("voice_style", {}), state.mood)
        context_values = debug.get("context")
        if context_values:
            context = TurnContext(**context_values)
            signal = learning_signal(str(debug.get("_transcript", "")), context, str(debug.get("response_strategy", "quiet_companionship")))
            if signal:
                kind, example_style, positive = signal
                app.state.learning.learn(
                    state.user_id, type=kind,
                    tags=[context.user_intent, context.user_emotion, context.language],
                    strategy=str(debug.get("response_strategy")), example_style=example_style,
                    positive=positive,
                )
        if state.roleplay and state.roleplay.active and not state.roleplay.paused:
            event = str(brain.get("reply", "")).strip()[:300]
            state.roleplay.last_event = event
            prior = state.roleplay.scene_summary.strip()
            state.roleplay.scene_summary = (prior + " " + event).strip()[-800:]
        brain["adaptive"] = {key: value for key, value in debug.items() if not key.startswith("_")}

    def persist_successful_turn(
        state: SessionState,
        language: str,
        transcript: str,
        conversation_mode: str = NORMAL_MODE,
    ) -> dict[str, int | bool]:
        try:
            brain = getattr(state.pipeline, "brain", None)
            if brain is None:
                return {"candidate_count": 0, "saved_count": 0, "persistence_ok": False}
            if language != "auto":
                app.state.memory.update_profile(state.user_id, preferred_language=language)
            if conversation_mode != ADULT_MODE:
                if display_name := extract_display_name(transcript):
                    app.state.memory.update_profile(state.user_id, display_name=display_name)
            app.state.memory.save_relationship(
                state.user_id,
                brain.relationship_state.as_dict(),
                brain.current_emotion,
                brain.previous_emotion,
            )
            candidates = [] if conversation_mode == ADULT_MODE else extract_memory_candidates(transcript)
            saved = save_candidates(app.state.memory, state.user_id, candidates)
            return {"candidate_count": len(candidates), "saved_count": saved, "persistence_ok": True}
        except Exception as exc:
            logging.getLogger("prithi.memory").warning("Memory persistence skipped after %s", type(exc).__name__)
            return {"candidate_count": 0, "saved_count": 0, "persistence_ok": False}

    def register_audio(source_audio: Path, session_id: str) -> tuple[str, Path]:
        cleanup_expired()
        while True:
            audio_id = secrets.token_urlsafe(24)
            destination = WEB_AUDIO_DIR / f"{audio_id}.wav"
            with app.state.state_lock:
                if audio_id not in app.state.audio_files and not destination.exists():
                    shutil.move(str(source_audio), destination)
                    app.state.audio_files[audio_id] = AudioState(
                        destination, session_id, time.time() + web_config.audio_ttl_seconds
                    )
                    return audio_id, destination

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[..., Any]) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(status_code=500, content={"detail": "Internal Prithi service error"})
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "microphone=(self)"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:"
        return response

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, response: Response) -> HTMLResponse:
        session_id = current_session(request, response)
        identity, _ = browser_identity(request)
        user_id = stable_user_id(identity)
        app.state.memory.ensure_profile(user_id)
        page = HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))
        page.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            max_age=int(web_config.session_ttl_seconds),
        )
        set_user_cookie(page, request, identity)
        return page

    @app.get("/app.js")
    def javascript() -> FileResponse:
        return FileResponse(WEB_DIR / "app.js", media_type="application/javascript")

    @app.get("/styles.css")
    def stylesheet() -> FileResponse:
        return FileResponse(WEB_DIR / "styles.css", media_type="text/css")

    @app.get("/api/health", dependencies=[Depends(require_token)])
    def health() -> dict[str, Any]:
        checks = health_checker()
        version = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.is_file() else "unknown"
        return {"status": "ok", "version": version, **checks}

    def adult_mode_payload(state: SessionState, user_id: str) -> dict[str, Any]:
        age_confirmed = app.state.memory.adult_age_confirmed(user_id)
        enabled = bool(age_confirmed and state.adult_opt_in)
        router = app.state.model_router or getattr(state.pipeline, "model_router", None)
        normal_model = (
            router.config.normal_model if router is not None
            else os.environ.get("PRITHI_LLM_NORMAL_MODEL", "").strip()
            or os.environ.get("PRITHI_LLM_MODEL", "").strip()
            or DEFAULT_NORMAL_MODEL
        )
        adult_model = (
            router.config.adult_model if router is not None
            else os.environ.get("PRITHI_LLM_ADULT_MODEL", "").strip() or DEFAULT_ADULT_MODEL
        )
        return {
            "status": adult_mode_status(age_confirmed, enabled),
            "conversation_mode": ADULT_MODE if enabled else NORMAL_MODE,
            "age_confirmed": age_confirmed,
            "adult_opt_in": enabled,
            "selected_model": adult_model if enabled else normal_model,
            "normal_model": normal_model,
            "adult_model": adult_model,
        }

    def turn_mode_options(state: SessionState, user_id: str) -> dict[str, Any]:
        mode = adult_mode_payload(state, user_id)
        return {
            "conversation_mode": mode["conversation_mode"],
            "age_confirmed": mode["age_confirmed"],
            "adult_opt_in": mode["adult_opt_in"],
        }

    def apply_safety_exit(state: SessionState, routing: dict[str, Any]) -> bool:
        if routing.get("disable_adult_mode"):
            state.adult_opt_in = False
            return True
        return False

    @app.get("/api/adult-mode", dependencies=[Depends(require_token)])
    def get_adult_mode(
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> dict[str, Any]:
        return adult_mode_payload(get_session(session_id, user_id), user_id)

    @app.post("/api/adult-mode/confirm-age", dependencies=[Depends(require_token)])
    def confirm_adult_age(
        payload: dict[str, Any],
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> dict[str, Any]:
        if payload.get("confirmed") is not True:
            raise HTTPException(status_code=400, detail="Explicit 18+ confirmation is required")
        app.state.memory.set_adult_age_confirmed(user_id, True)
        return adult_mode_payload(get_session(session_id, user_id), user_id)

    @app.post("/api/adult-mode/enable", dependencies=[Depends(require_token)])
    def enable_adult_mode(
        payload: dict[str, Any],
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> dict[str, Any]:
        if payload.get("enabled") is not True:
            raise HTTPException(status_code=400, detail="Explicit adult-mode opt-in is required")
        if not app.state.memory.adult_age_confirmed(user_id):
            raise HTTPException(status_code=403, detail="Confirm that you are 18+ before enabling adult mode")
        state = get_session(session_id, user_id)
        router = app.state.model_router or getattr(state.pipeline, "model_router", None)
        if router is not None:
            try:
                router.adult_backend.verify_model_available()
            except Exception:
                raise HTTPException(status_code=503, detail="Adult conversation model is unavailable")
        state.adult_opt_in = True
        return adult_mode_payload(state, user_id)

    @app.post("/api/adult-mode/disable", dependencies=[Depends(require_token)])
    def disable_adult_mode(
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> dict[str, Any]:
        state = get_session(session_id, user_id)
        state.adult_opt_in = False
        return adult_mode_payload(state, user_id)

    @app.get("/api/brain-state", dependencies=[Depends(require_token)])
    def brain_state(
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> dict[str, Any]:
        state = get_session(session_id, user_id)
        brain = getattr(state.pipeline, "brain", None)
        debug = dict(state.adaptive_debug or {})
        debug.pop("_transcript", None)
        return {
            "model": getattr(getattr(brain, "backend", None), "model", None),
            "emotion": getattr(brain, "current_emotion", "neutral"),
            "relationship": brain.relationship_state.as_dict() if brain else {},
            "roleplay": (state.roleplay or RoleplayState()).as_dict(),
            **debug,
        }

    @app.post("/api/roleplay/start", dependencies=[Depends(require_token)])
    def start_roleplay(
        scenario: str = Form(...), role: str = Form(default="Prithi"), tone: str = Form(default="natural"),
        adult_scene: bool = Form(default=False), session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> dict[str, Any]:
        state = get_session(session_id, user_id)
        roleplay = state.roleplay or RoleplayState()
        try:
            roleplay.start(scenario, role=role, tone=tone, adult_scene=adult_scene,
                           age_confirmed=app.state.memory.adult_age_confirmed(user_id),
                           adult_opt_in=state.adult_opt_in)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        state.roleplay = roleplay
        return roleplay.as_dict()

    @app.post("/api/roleplay/{action}", dependencies=[Depends(require_token)])
    def change_roleplay(
        action: str, session_id: str = Depends(current_session), user_id: str = Depends(current_user),
    ) -> dict[str, Any]:
        if action not in {"pause", "resume", "reset"}:
            raise HTTPException(status_code=404, detail="Unsupported roleplay action")
        state = get_session(session_id, user_id)
        roleplay = state.roleplay or RoleplayState()
        getattr(roleplay, action)()
        state.roleplay = roleplay
        return roleplay.as_dict()

    def clear_session_conversation(session_id: str, user_id: str) -> None:
        with app.state.state_lock:
            state = app.state.sessions.get(session_id)
        if state and state.user_id == user_id:
            with state.lock:
                clear = getattr(state.pipeline, "clear_conversation", None)
                if clear:
                    clear()
                else:
                    state.pipeline.reset()
                state.last_used = time.time()

    @app.post("/api/reset", dependencies=[Depends(require_token)])
    @app.post("/api/memory/reset-conversation", dependencies=[Depends(require_token)])
    def reset(
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> dict[str, str]:
        clear_session_conversation(session_id, user_id)
        return {"status": "reset"}

    @app.get("/api/memory", dependencies=[Depends(require_token)])
    def get_memory(user_id: str = Depends(current_user), session_id: str = Depends(current_session)) -> dict[str, Any]:
        profile = app.state.memory.ensure_profile(user_id)
        relationship = app.state.memory.load_relationship(user_id)
        memories = app.state.memory.list_memories(user_id)
        state = get_session(session_id, user_id)
        public_memories = [
            {key: item[key] for key in ("category", "content", "importance", "created_at", "last_used_at")}
            for item in memories
        ]
        return {
            "persistent_memory_enabled": True,
            "saved_memory_count": len(memories),
            "relationship_restored": bool(state and state.user_id == user_id and state.relationship_restored),
            "profile": profile,
            "relationship": relationship,
            "memories": public_memories,
        }

    @app.post("/api/memory/reset-relationship", dependencies=[Depends(require_token)])
    def reset_persistent_relationship(
        user_id: str = Depends(current_user),
        session_id: str = Depends(current_session),
    ) -> dict[str, str]:
        app.state.memory.reset_relationship(user_id)
        with app.state.state_lock:
            state = app.state.sessions.get(session_id)
        if state and state.user_id == user_id:
            with state.lock:
                reset_relationship = getattr(state.pipeline, "reset_relationship", None)
                if reset_relationship:
                    reset_relationship()
                state.relationship_restored = False
        return {"status": "relationship_reset"}

    @app.delete("/api/memory", dependencies=[Depends(require_token)])
    def delete_memory(
        user_id: str = Depends(current_user),
        session_id: str = Depends(current_session),
    ) -> dict[str, str]:
        app.state.memory.delete_user_memory(user_id)
        app.state.memory.ensure_profile(user_id)
        with app.state.state_lock:
            state = app.state.sessions.get(session_id)
        if state and state.user_id == user_id:
            with state.lock:
                reset_relationship = getattr(state.pipeline, "reset_relationship", None)
                if reset_relationship:
                    reset_relationship()
                state.relationship_restored = False
                state.adult_opt_in = False
        return {"status": "memory_deleted"}

    @app.post("/api/voice-turn", dependencies=[Depends(require_token)])
    async def voice_turn(
        audio: UploadFile = File(...),
        language: str = Form(default="bengali"),
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> Response:
        request_started = time.perf_counter()
        request_id = secrets.token_hex(8)
        normalized_language = language.strip().lower()
        if normalized_language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail="Unsupported language")
        log_timing(request_id=request_id, status="LANGUAGE_ROUTING", requested_browser_language=language, backend_resolved_language=normalized_language, whisper_language=language_code(normalized_language), forced=language_code(normalized_language) is not None)
        content_type = (audio.content_type or "").split(";", 1)[0].lower()
        suffix = ALLOWED_AUDIO_TYPES.get(content_type)
        if suffix is None:
            raise HTTPException(status_code=415, detail="Unsupported audio file type")

        try:
            state = get_session(session_id, user_id)
        except Exception:
            raise HTTPException(status_code=503, detail="Prithi brain is unavailable")

        with tempfile.TemporaryDirectory(prefix="prithi_web_input_") as directory:
            temp_dir = Path(directory)
            source = temp_dir / f"upload{suffix}"
            converted = temp_dir / "input.wav"
            size = 0
            upload_started = time.perf_counter()
            try:
                with source.open("xb") as output:
                    while chunk := await audio.read(1024 * 1024):
                        size += len(chunk)
                        if size > web_config.max_upload_bytes:
                            raise HTTPException(status_code=413, detail="Recording upload is too large")
                        output.write(chunk)
            finally:
                await audio.close()
            if size == 0:
                raise HTTPException(status_code=400, detail="Recording is empty")
            upload_time = time.perf_counter() - upload_started
            try:
                conversion_time, recording_duration = await run_in_threadpool(
                    converter, source, converted, web_config.max_recording_seconds
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))

            def process() -> dict[str, Any]:
                with state.lock:
                    state.last_used = time.time()
                    memory_context = app.state.memory.build_prompt(user_id, "")
                    options: dict[str, Any] = {"memory_context": memory_context}
                    if getattr(state.pipeline, "model_router", None) is not None:
                        options.update(turn_mode_options(state, user_id))
                    mode = str(options.get("conversation_mode", NORMAL_MODE))
                    process_parameters = inspect.signature(state.pipeline.process_audio).parameters
                    if "adaptive_context_factory" in process_parameters:
                        options["adaptive_context_factory"] = lambda text: prepare_adaptive_turn(state, text, normalized_language, mode)
                        options["adaptive_finalize"] = lambda value: finalize_adaptive_turn(state, value)
                    return state.pipeline.process_audio(converted, normalized_language, **options)

            result = await run_in_threadpool(process)

        status = result.get("status")
        if status == "STT_EMPTY":
            raise HTTPException(status_code=422, detail=RETRY_MESSAGE)
        if status == "STT_FAILED":
            raise HTTPException(status_code=422, detail="Speech recognition failed")
        if status == "BRAIN_FAILED":
            raise HTTPException(status_code=502, detail="Prithi could not generate a reply")

        stt = result.get("stt", {})
        brain = result.get("brain", {})
        voice = result.get("voice", {})
        routing = brain.get("routing", {})
        adult_mode_disabled = apply_safety_exit(state, routing)
        if status in {"SUCCESS", "TTS_FAILED"} and brain.get("reply"):
            memory_result = persist_successful_turn(
                state,
                normalized_language,
                result.get("transcript", ""),
                routing.get("conversation_mode", NORMAL_MODE),
            )
        else:
            memory_result = {"candidate_count": 0, "saved_count": 0, "persistence_ok": False}
        payload: dict[str, Any] = {
            "request_id": request_id,
            "requested_browser_language": language,
            "resolved_stt_language": language_code(normalized_language),
            "whisper_model": stt.get("model"),
            "raw_transcript": stt.get("raw_transcript", result.get("transcript", "")),
            "preferred_reply_language": normalized_language if normalized_language != "auto" else None,
            "brain_returned_language": brain.get("language"),
            "validated_reply_language": brain.get("language"),
            "tts_locale": voice.get("locale"),
            "transcript": result.get("transcript", ""),
            "detected_language": stt.get("detected_language", ""),
            "reply": brain.get("reply", ""),
            "language": brain.get("language", ""),
            "emotion": brain.get("emotion", ""),
            "voice_style": brain.get("voice_style", {}),
            "upload_time": upload_time,
            "conversion_time": conversion_time,
            "recording_duration": recording_duration,
            "stt_time": stt.get("transcription_time", 0.0),
            "stt_model_load_time": stt.get("model_load_time", 0.0),
            "llm_time": brain.get("generation_time", 0.0),
            "tts_time": voice.get("generation_time", 0.0),
            "total_time": time.perf_counter() - request_started,
            "response_duration": voice.get("duration", 0.0),
            "audio_url": None,
            "fallback": voice.get("fallback_occurred", False),
            "memory_saved_count": memory_result["saved_count"],
            "memory_candidate_count": memory_result["candidate_count"],
            "conversation_mode": routing.get("conversation_mode", NORMAL_MODE),
            "age_confirmed": routing.get("age_confirmed", app.state.memory.adult_age_confirmed(user_id)),
            "adult_opt_in": routing.get("adult_opt_in", False),
            "selected_model": routing.get("selected_model"),
            "model_switch_occurred": routing.get("switch_occurred", False),
            "model_switch_latency": routing.get("switch_latency", 0.0),
            "adult_mode_disabled": adult_mode_disabled,
            "adaptive": brain.get("adaptive", {}),
        }
        if status == "TTS_FAILED":
            log_timing(request_id=request_id, endpoint="voice-turn", status=status, total=payload["total_time"])
            payload["error"] = "Voice generation failed; the text reply is still available"
            return JSONResponse(status_code=502, content=payload)
        if status != "SUCCESS":
            raise HTTPException(status_code=500, detail="Unexpected pipeline result")

        source_audio = Path(str(voice["output_path"])).resolve()
        if not source_audio.is_file():
            raise HTTPException(status_code=500, detail="Generated response audio is unavailable")
        audio_id, destination = register_audio(source_audio, session_id)
        payload["audio_url"] = f"/api/audio/{audio_id}"
        payload["response_bytes"] = destination.stat().st_size
        log_timing(
            request_id=request_id,
            endpoint="voice-turn",
            status="SUCCESS",
            stt=payload["stt_time"],
            llm=payload["llm_time"],
            tts=payload["tts_time"],
            total=payload["total_time"],
            language=payload["language"],
            emotion=payload["emotion"],
            fallback=payload["fallback"],
            upload_bytes=size,
            response_bytes=payload["response_bytes"],
            conversation_mode=payload["conversation_mode"],
            selected_model=payload["selected_model"],
            model_switch_occurred=payload["model_switch_occurred"],
            model_switch_latency=payload["model_switch_latency"],
        )
        return payload

    @app.post("/api/voice-turn-stream", dependencies=[Depends(require_token)])
    async def voice_turn_stream(
        audio: UploadFile = File(...),
        language: str = Form(default="bengali"),
        session_id: str = Depends(current_session),
        user_id: str = Depends(current_user),
    ) -> StreamingResponse:
        request_started = time.perf_counter()
        request_id = secrets.token_hex(8)
        normalized_language = language.strip().lower()
        if normalized_language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail="Unsupported language")
        log_timing(request_id=request_id, status="LANGUAGE_ROUTING", requested_browser_language=language, backend_resolved_language=normalized_language, whisper_language=language_code(normalized_language), forced=language_code(normalized_language) is not None)
        content_type = (audio.content_type or "").split(";", 1)[0].lower()
        suffix = ALLOWED_AUDIO_TYPES.get(content_type)
        if suffix is None:
            raise HTTPException(status_code=415, detail="Unsupported audio file type")
        try:
            state = get_session(session_id, user_id)
        except Exception:
            raise HTTPException(status_code=503, detail="Prithi brain is unavailable")

        temp_dir = Path(tempfile.mkdtemp(prefix="prithi_web_stream_"))
        source = temp_dir / f"upload{suffix}"
        converted = temp_dir / "input.wav"
        size = 0
        upload_started = time.perf_counter()
        try:
            with source.open("xb") as output:
                while chunk := await audio.read(1024 * 1024):
                    size += len(chunk)
                    if size > web_config.max_upload_bytes:
                        raise HTTPException(status_code=413, detail="Recording upload is too large")
                    output.write(chunk)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        finally:
            await audio.close()
        if size == 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Recording is empty")
        upload_time = time.perf_counter() - upload_started
        try:
            conversion_time, recording_duration = await run_in_threadpool(
                converter, source, converted, web_config.max_recording_seconds
            )
        except ValueError as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(exc))

        def event(name: str, **data: Any) -> str:
            return "data: " + json.dumps({"event": name, "request_id": request_id, **data}, ensure_ascii=False) + "\n\n"

        async def progress():
            acquired = False
            try:
                await run_in_threadpool(state.lock.acquire)
                acquired = True
                state.last_used = time.time()
                yield event("language", requested_language=language, resolved_language=normalized_language, whisper_language=language_code(normalized_language), forced=language_code(normalized_language) is not None)
                try:
                    stt = await run_in_threadpool(state.pipeline.transcribe_only, converted, normalized_language)
                except Exception:
                    yield event("error", stage="stt", message="Speech recognition failed")
                    return
                transcript = str(stt.get("text", "")).strip()
                gate = assess_transcript(stt, normalized_language)
                log_timing(request_id=request_id, status="STT_QUALITY", model=stt.get("model"), forced_language=language_code(normalized_language), quality_gate=gate, segment_count=stt.get("segment_count"), text_length=len(transcript), stt_time=stt.get("transcription_time"))
                if not gate["passed"]:
                    yield event("error", stage="stt", message=RETRY_MESSAGE)
                    return
                transcript_visible = time.perf_counter() - request_started
                yield event(
                    "transcript",
                    text=transcript,
                    detected_language=stt.get("detected_language", ""),
                    stt_time=stt.get("transcription_time", 0.0),
                    stt_model_load_time=stt.get("model_load_time", 0.0),
                    stt_model_reused=stt.get("model_reused", False),
                    model=stt.get("model"), quality_gate=gate, fallback_used=False,
                    elapsed=transcript_visible,
                )
                yield event("thinking")
                try:
                    memory_context = await run_in_threadpool(app.state.memory.build_prompt, user_id, transcript)
                    response_options: dict[str, Any] = {
                        "preferred_reply_language": normalized_language if normalized_language != "auto" else None,
                        "memory_context": memory_context,
                    }
                    if getattr(state.pipeline, "model_router", None) is not None:
                        response_options.update(turn_mode_options(state, user_id))
                    mode = str(response_options.get("conversation_mode", NORMAL_MODE))
                    adaptive_prompt = prepare_adaptive_turn(state, transcript, normalized_language, mode)
                    if "adaptive_context" in inspect.signature(state.pipeline.respond_only).parameters:
                        response_options["adaptive_context"] = adaptive_prompt
                    brain = await run_in_threadpool(state.pipeline.respond_only, transcript, **response_options)
                    finalize_adaptive_turn(state, brain)
                except Exception:
                    yield event("error", stage="llm", message="Prithi could not generate a reply")
                    return
                routing = brain.get("routing", {})
                adult_mode_disabled = apply_safety_exit(state, routing)
                memory_result = await run_in_threadpool(
                    persist_successful_turn,
                    state,
                    normalized_language,
                    transcript,
                    routing.get("conversation_mode", NORMAL_MODE),
                )
                reply_visible = time.perf_counter() - request_started
                yield event(
                    "reply",
                    text=brain["reply"],
                    language=brain["language"],
                    emotion=brain["emotion"],
                    voice_style=brain["voice_style"],
                    llm_time=brain["generation_time"],
                    preferred_reply_language=brain.get("preferred_reply_language"),
                    brain_returned_language=brain["language"],
                    validated_reply_language=brain["language"],
                    relationship_state=brain.get("relationship_state", {}),
                    current_emotion=brain.get("current_emotion"),
                    previous_emotion=brain.get("previous_emotion"),
                    question_used=brain.get("question_used", False),
                    memory_saved_count=memory_result["saved_count"],
                    memory_candidate_count=memory_result["candidate_count"],
                    memory_persistence_ok=memory_result["persistence_ok"],
                    conversation_mode=routing.get("conversation_mode", NORMAL_MODE),
                    age_confirmed=routing.get("age_confirmed", app.state.memory.adult_age_confirmed(user_id)),
                    adult_opt_in=routing.get("adult_opt_in", False),
                    selected_model=routing.get("selected_model"),
                    model_switch_occurred=routing.get("switch_occurred", False),
                    model_switch_latency=routing.get("switch_latency", 0.0),
                    adult_mode_disabled=adult_mode_disabled,
                    adaptive=brain.get("adaptive", {}),
                    elapsed=reply_visible,
                )
                try:
                    voice = await run_in_threadpool(state.pipeline.synthesize_only, brain)
                except Exception:
                    yield event("error", stage="tts", message="Voice generation failed; the text reply is still available")
                    return
                source_audio = Path(str(voice["output_path"])).resolve()
                if not source_audio.is_file():
                    yield event("error", stage="tts", message="Generated response audio is unavailable")
                    return
                audio_id, destination = register_audio(source_audio, session_id)
                total = time.perf_counter() - request_started
                payload = {
                    "audio_url": f"/api/audio/{audio_id}",
                    "upload_time": upload_time,
                    "conversion_time": conversion_time,
                    "recording_duration": recording_duration,
                    "stt_time": stt.get("transcription_time", 0.0),
                    "llm_time": brain["generation_time"],
                    "tts_time": voice["generation_time"],
                    "total_time": total,
                    "response_duration": voice["duration"],
                    "fallback": voice["fallback_occurred"],
                    "tts_locale": voice.get("locale"),
                    "upload_bytes": size,
                    "response_bytes": destination.stat().st_size,
                    "conversation_mode": routing.get("conversation_mode", NORMAL_MODE),
                    "selected_model": routing.get("selected_model"),
                    "model_switch_occurred": routing.get("switch_occurred", False),
                    "model_switch_latency": routing.get("switch_latency", 0.0),
                    "adult_mode_disabled": adult_mode_disabled,
                }
                log_timing(
                    request_id=request_id,
                    endpoint="voice-turn-stream",
                    status="SUCCESS",
                    stt=payload["stt_time"],
                    llm=payload["llm_time"],
                    tts=payload["tts_time"],
                    total=total,
                    transcript_visible=transcript_visible,
                    reply_visible=reply_visible,
                    audio_ready=total,
                    language=brain["language"],
                    emotion=brain["emotion"],
                    fallback=payload["fallback"],
                    upload_bytes=size,
                    response_bytes=payload["response_bytes"],
                    preferred_reply_language=normalized_language if normalized_language != "auto" else None,
                    validated_reply_language=brain["language"],
                    tts_locale=voice.get("locale"),
                    conversation_mode=payload["conversation_mode"],
                    selected_model=payload["selected_model"],
                    model_switch_occurred=payload["model_switch_occurred"],
                    model_switch_latency=payload["model_switch_latency"],
                )
                yield event("audio_ready", **payload)
            except asyncio.CancelledError:
                log_timing(request_id=request_id, endpoint="voice-turn-stream", status="CLIENT_CANCELLED")
                raise
            finally:
                if acquired:
                    state.lock.release()
                shutil.rmtree(temp_dir, ignore_errors=True)

        return StreamingResponse(
            progress(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    @app.get("/api/audio/{audio_id}", dependencies=[Depends(require_token)])
    def response_audio(
        audio_id: str,
        session_id: str = Depends(current_session),
    ) -> FileResponse:
        cleanup_expired()
        if not AUDIO_ID_PATTERN.fullmatch(audio_id):
            raise HTTPException(status_code=404, detail="Audio not found")
        with app.state.state_lock:
            record = app.state.audio_files.get(audio_id)
        if not record or record.session_id != session_id or not record.path.is_file():
            raise HTTPException(status_code=404, detail="Audio not found")
        return FileResponse(
            record.path,
            media_type="audio/wav",
            filename="prithi-response.wav",
            headers={"Cache-Control": "no-store"},
        )

    register_diagnostics(app, require_token, current_session, converter, ALLOWED_AUDIO_TYPES, web_config)
    return app


load_local_env()
app = create_app()
