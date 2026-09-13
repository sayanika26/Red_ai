from __future__ import annotations

from prithi_context import TurnContext
import json


STRATEGIES = {
    "direct_answer", "playful_answer", "teasing_answer", "warm_validation",
    "gentle_challenge", "romantic_reciprocation", "sensual_reciprocation",
    "curious_probe", "quiet_companionship", "reassurance", "boundary_setting",
    "deescalation", "topic_shift", "memory_callback",
}


def select_strategy(context: TurnContext, *, adult_mode: bool = False, has_relevant_memory: bool = False) -> str:
    if context.boundary_signal == "stop":
        return "deescalation"
    if context.boundary_signal != "none":
        return "boundary_setting"
    if context.user_need == "reassurance":
        return "reassurance"
    if has_relevant_memory and context.user_intent in {"connect", "share"}:
        return "memory_callback"
    if context.intimacy_signal == "explicit_invitation":
        return "sensual_reciprocation" if adult_mode else "romantic_reciprocation"
    if context.user_emotion == "playful":
        return "teasing_answer"
    if context.relationship_signal == "positive":
        return "romantic_reciprocation" if adult_mode else "warm_validation"
    if context.user_intent == "ask":
        return "direct_answer"
    return "quiet_companionship"


def strategy_instruction(strategy: str) -> str:
    if strategy not in STRATEGIES:
        raise ValueError("Unsupported response strategy")
    instructions = {
        "direct_answer": "Answer the actual question directly, then add at most one natural reaction.",
        "teasing_answer": "Use one clever, light tease; stay kind and do not over-explain.",
        "warm_validation": "React warmly to the specific detail without counselor language.",
        "reassurance": "Offer grounded reassurance and companionship; do not interrogate.",
        "quiet_companionship": "Stay present with a simple natural response; a question is optional.",
        "romantic_reciprocation": "Reciprocate only the romantic warmth clearly offered by the user.",
        "sensual_reciprocation": "Reciprocate consensual adult sensual tone suggestively, not explicitly.",
        "boundary_setting": "Respect the stated limit immediately and keep the interaction comfortable.",
        "deescalation": "Stop romantic/adult escalation immediately and return to ordinary conversation.",
        "memory_callback": "Use one supplied relevant memory naturally; never invent a memory.",
    }
    return instructions.get(strategy, "Use this strategy naturally and concisely: " + strategy.replace("_", " ") + ".")


def compose_adaptive_prompt(*, context: TurnContext, strategy: str, mood: dict[str, float], relationship: dict[str, float], roleplay_prompt: str, learned_prompt: str, adult_mode: bool) -> str:
    """Compact observable state for response steering; contains no hidden reasoning."""
    state = {
        "context": context.as_dict(),
        "strategy": strategy,
        "mood": {key: round(float(value), 2) for key, value in mood.items()},
        "relationship": {key: round(float(value), 2) for key, value in relationship.items()},
        "adult_mode": bool(adult_mode),
    }
    return (
        "Adaptive response state: " + json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n"
        + "Strategy instruction: " + strategy_instruction(strategy) + "\n"
        + roleplay_prompt + "\n" + learned_prompt
    )
