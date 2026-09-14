from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from prithi_search import (
    SearchEvidence,
    SearchHistoryStore,
    SearchSource,
    evidence_from_sources,
    ttl_for_query,
)


KNOWLEDGE_ACTIONS = {"local", "clarify", "search", "research_again", "unknown"}


class SearchProvider(Protocol):
    def search(self, query: str, limit: int = 6) -> list[SearchSource]: ...


@dataclass(frozen=True)
class KnowledgeDecision:
    action: str
    reason: str
    query: str = ""
    clarification: str = ""


@dataclass(frozen=True)
class RetrievalResult:
    decision: KnowledgeDecision
    evidence: SearchEvidence | None = None

    @property
    def confidence(self) -> float:
        return self.evidence.confidence if self.evidence else (1.0 if self.decision.action == "local" else 0.0)

    @property
    def terminology_note(self) -> str:
        """Guidance for questions whose office title does not exist in that country."""
        correction = OFFICE_CORRECTIONS.get(self.decision.reason, "")
        return f"\nTerminology correction: {correction} Correct it gently in your own warm voice, then answer." if correction else ""

    @property
    def retry_note(self) -> str:
        """After a re-check the user still needs the answer, not just 'I looked again'."""
        if self.decision.action != "research_again":
            return ""
        return (
            "\nThis is a re-check the user asked for. Say briefly that you checked again, then state the "
            "verified answer in full, even when it matches your previous reply. Do not reply with only "
            "'I checked' or 'my information was outdated' and no answer."
        )

    def prompt(self) -> str:
        if self.decision.action == "local":
            return "Knowledge action: local. Answer from stable knowledge and conversation context."
        if self.decision.action == "clarify":
            return f"Knowledge action: clarify. Ask exactly this one clarification naturally: {self.decision.clarification}"
        if self.decision.action == "unknown" or not self.evidence or not self.evidence.sources:
            detail = " Conflicting evidence remained after retry." if self.evidence and self.evidence.conflicting else ""
            return "Knowledge action: unknown. No reliable answer was verified." + detail + " Admit uncertainty naturally and do not invent an answer." + self.terminology_note
        return (
            f"Knowledge action: {self.decision.action}. Search confidence={self.evidence.confidence:.2f}; "
            f"searched_at={self.evidence.searched_at}; conflicting={str(self.evidence.conflicting).lower()}.\n"
            "The evidence below was retrieved from the web just now and is more current than anything you remember. "
            "For this factual claim you must follow the evidence even when it contradicts what you believe: if they "
            "disagree, the evidence is right and your own memory is out of date. Never answer a current-affairs "
            "question from memory, and never state a name, number or date that does not appear in the evidence. "
            "Prefer higher-ranked official sources, mention uncertainty when warranted, do not claim you knew it "
            "without checking, and keep the current Prithi language and tone."
            + self.terminology_note
            + self.retry_note
            + "\n"
            + self.evidence.summary
        )


_FRESH = (
    "latest", "current", "today", "right now", "recent", "news", "price", "score", "result",
    "president", "prime minister", " pm ", "chief minister", "ceo", "version", "released",
    "weather", "election", "stock", "crypto", "2025", "2026", "এখন", "আজকের খবর",
    "বর্তমান", "সর্বশেষ", "দাম", "স্কোর", "ফলাফল", "प्रधानमंत्री", "राष्ट्रपति", "ताज़ा",
)
_VERIFY = ("verify", "double check", "check again", "are you sure", "important", "নিশ্চিত", "যাচাই", "আবার দেখ", "पक्का", "जाँच")
_SEARCH = ("search", "look up", "check online", "google", "web-এ", "খুঁজে দেখ", "इंटरनेट पर", "सर्च")


_US = "america|usa|u\\.s\\.a?\\.?|united states|[আএ]মেরিকা|যুক্তরাষ্ট্র|अमेरिका"

OFFICE_CORRECTIONS = {
    "wrong_office_title": "the United States has a President as head of government, not a Prime Minister.",
}


# Country names written in Latin script, so Banglish questions ("USA r president ke?") are
# recognised as already naming a place and never trigger a needless clarification.
# Bare "us" is deliberately excluded: it collides with the English pronoun.
_PLACES = (
    r"ভারত|বাংলাদেশ|[আএ]মেরিকা|যুক্তরাষ্ট্র|ইন্ডিয়া|भारत|अमेरिका|"
    r"\b(?:usa|u\.s\.a?\.?|america|united states|uk|britain|england|india|bangladesh|"
    r"pakistan|nepal|bhutan|sri lanka|canada|australia|japan|china|russia|france|"
    r"germany|italy|spain|brazil|israel|iran|ukraine)\b"
)


# Conversational phrasing makes a poor search query ("Ekhon USA r president ke ache bolo to?"),
# so public-office questions are rewritten into a canonical English lookup instead.
_COUNTRY_NAMES = (
    ("the United States", r"usa|u\.s\.a?\.?|america|united states|[আএ]মেরিকা|যুক্তরাষ্ট্র|अमेरिका"),
    ("India", r"india|ভারত|ইন্ডিয়া|भारत"),
    ("Bangladesh", r"bangladesh|বাংলাদেশ"),
    ("the United Kingdom", r"uk|britain|england|united kingdom|বিলেত|ব্রিটেন"),
    ("Pakistan", r"pakistan|পাকিস্তান"),
    ("Canada", r"canada|কানাডা"),
    ("Australia", r"australia|অস্ট্রেলিয়া"),
    ("Japan", r"japan|জাপান"),
    ("China", r"china|চীন"),
    ("Russia", r"russia|রাশিয়া"),
    ("France", r"france|ফ্রান্স"),
    ("Germany", r"germany|জার্মানি"),
    ("Nepal", r"nepal|নেপাল"),
    ("Sri Lanka", r"sri lanka|শ্রীলঙ্কা"),
)
_OFFICE_NAMES = (
    ("President", r"\bpresident\b|রাষ্ট্রপতি|প্রেসিডেন্ট|राष्ट्रपति"),
    ("Prime Minister", r"\b(?:pm|prime minister)\b|প্রধানমন্ত্রী|प्रधानमंत्री"),
)


def canonical_office_query(low: str) -> str:
    """Return a clean lookup for 'who holds office X in country Y', else an empty string."""
    country = next((name for name, pattern in _COUNTRY_NAMES if re.search(pattern, low)), "")
    office = next((name for name, pattern in _OFFICE_NAMES if re.search(pattern, low)), "")
    return f"current {office} of {country}" if country and office else ""


def merge_clarification(question: str, reply: str) -> str:
    """Fold a short clarification answer back into the question that prompted it."""
    base = re.sub(r"\s*\?+\s*$", "", re.sub(r"\s+", " ", question).strip())
    answer = re.sub(r"\s*[.?!]+\s*$", "", re.sub(r"\s+", " ", reply).strip())
    if not answer or not base:
        return base or answer
    if re.search(r"\b(?:of|in)\s+\S", base.casefold()):
        return base
    return f"{base} of {answer}"


def classify_knowledge(text: str, pending_question: str = "", last_query: str = "") -> KnowledgeDecision:
    clean = re.sub(r"\s+", " ", text).strip()
    if pending_question:
        clean = merge_clarification(pending_question, clean)
    low = f" {clean.casefold()} "
    office = re.search(r"\b(?:pm|prime minister|president)\b|প্রধানমন্ত্রী|রাষ্ট্রপতি|প্রেসিডেন্ট|प्रधानमंत्री|राष्ट्रपति", low)
    has_place = bool(re.search(rf"\b(?:of|in)\s+[a-z][a-z .-]{{1,40}}|{_PLACES}", low))
    if office and not has_place:
        if pending_question:
            # One clarification only: never loop back for a second one.
            return KnowledgeDecision("search", "clarified_still_broad", query=clean)
        return KnowledgeDecision("clarify", "ambiguous_public_office", clarification="Which country or government do you mean?")
    if re.search(rf"\b(?:pm|prime minister)\b[^.?!]{{0,24}}?\b(?:of|in)\s+(?:{_US})\b", low) or (
        re.search(r"প্রধানমন্ত্রী|प्रधानमंत्री", low) and re.search(_US, low)
    ):
        return KnowledgeDecision("search", "wrong_office_title", query="current President of the United States")
    canonical = canonical_office_query(low)
    if any(marker in low for marker in _VERIFY):
        # "Are you sure?" carries no topic of its own: re-research the question it refers to,
        # otherwise the literal phrase becomes the search query and returns nothing useful.
        return KnowledgeDecision("research_again", "verification_requested", query=canonical or last_query or clean)
    if any(marker in low for marker in _SEARCH):
        return KnowledgeDecision("search", "explicit_search", query=canonical or clean)
    if canonical:
        return KnowledgeDecision("search", "public_office_lookup", query=canonical)
    personal_conversation = any(marker in low for marker in (
        "i feel", "i am feeling", "lonely", "sad", "miss you", "মন খারাপ", "একা লাগ", "তোমাকে মিস", "उदास", "अकेला",
    ))
    if personal_conversation:
        return KnowledgeDecision("local", "personal_conversation")
    if any(marker in low for marker in _FRESH):
        return KnowledgeDecision("search", "freshness_required", query=clean)
    return KnowledgeDecision("local", "stable_or_conversational")


def natural_status_line(action: str, language: str, seed: str) -> str:
    choices = {
        "bengali": ("হুম... এটা একবার দেখে নিই।", "একটু দাঁড়াও, ঠিক তথ্যটা যাচাই করছি।", "পুরো নিশ্চিত নই—এক সেকেন্ড দেখি।"),
        "hindi": ("हम्म... इसे एक बार जाँच लेती हूँ।", "एक सेकंड, सही जानकारी देख रही हूँ।", "पूरी तरह यक़ीन नहीं—ज़रा देखती हूँ।"),
        "english": ("Hmm... I should check that.", "Give me a second—I’m verifying it.", "I’m not completely sure, so let me look that up."),
    }
    values = choices.get(language, choices["english"])
    index = int(hashlib.sha256((action + seed).encode("utf-8")).hexdigest()[:8], 16) % len(values)
    return values[index]


class KnowledgeRetriever:
    def __init__(self, provider: SearchProvider, cache: SearchHistoryStore | None = None) -> None:
        self.provider, self.cache = provider, cache

    def retrieve(self, text: str, pending_question: str = "", last_query: str = "") -> RetrievalResult:
        decision = classify_knowledge(text, pending_question, last_query)
        if decision.action in {"local", "clarify"}:
            return RetrievalResult(decision)
        cached = None if decision.action == "research_again" else (self.cache.get(decision.query) if self.cache else None)
        if cached:
            return RetrievalResult(decision, cached)
        try:
            first = evidence_from_sources(decision.query, self.provider.search(decision.query, limit=6))
            evidence = first
            if decision.action == "research_again" or first.confidence < .58 or first.conflicting:
                retry_query = decision.query + " official primary source"
                second_sources = self.provider.search(retry_query, limit=6)
                combined = {source.url: source for source in first.sources + second_sources}
                evidence = evidence_from_sources(decision.query, list(combined.values()), retry_count=1)
            if not evidence.sources or evidence.confidence < .4 or evidence.conflicting:
                unknown = KnowledgeDecision("unknown", "unreliable_or_conflicting_results", query=decision.query)
                result = RetrievalResult(unknown, evidence)
            else:
                result = RetrievalResult(decision, evidence)
            if self.cache and evidence.sources:
                self.cache.put(evidence, ttl_for_query(decision.query, self.cache.ttl_seconds))
            return result
        except Exception:
            return RetrievalResult(KnowledgeDecision("unknown", "search_unavailable", query=decision.query))
