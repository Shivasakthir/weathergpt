"""
nlu.py
------
Lightweight, dependency-free natural-language query understanding.

Design principle from the project plan: "the LLM should not invent weather
facts." So this module's only job is INTENT + ENTITY extraction (what does
the user want, for which place/time/activity). The actual facts always come
from weather.py, risk.py and advisory.py — never guessed here.

This works fully offline with no API key. If an OPENAI_API_KEY (or similar)
is configured, main.py can optionally use a real LLM for extraction/response
phrasing instead — see app/llm.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

INTENT_ALERTS = "alerts"
INTENT_FORECAST = "forecast"
INTENT_CURRENT = "current"
INTENT_HISTORICAL = "historical"
INTENT_ADVISORY = "advisory"
INTENT_UNKNOWN = "unknown"

ACTIVITIES = ["farming", "irrigat", "crop", "travel", "fishing", "outdoor", "aviation", "flight", "wedding", "event"]

TIME_WORDS = {
    "today": 0,
    "tonight": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
    "this week": 5,
    "next week": 7,
}

ALERT_WORDS = ["alert", "warning", "cyclone", "flood", "storm warning", "severe"]
HISTORY_WORDS = ["trend", "history", "historical", "climate", "average", "last year", "past"]
ADVISORY_WORDS = ["should i", "advisory", "advice", "recommend", "is it safe", "can i"]


@dataclass
class ParsedQuery:
    intent: str = INTENT_UNKNOWN
    location: Optional[str] = None
    activity: Optional[str] = None
    days_ahead: int = 0
    raw_text: str = ""


# A short list of well-known Indian cities/towns to help the naive location
# extractor prefer real places over stray nouns. Not exhaustive — the
# geocoder in weather.py does the real resolution.
KNOWN_PLACES = [
    "chennai", "madurai", "coimbatore", "trichy", "tiruchirapalli", "salem",
    "tirunelveli", "vellore", "erode", "thanjavur", "kanyakumari", "ooty",
    "puducherry", "bangalore", "bengaluru", "hyderabad", "mumbai", "delhi",
    "kolkata", "kochi", "thiruvananthapuram", "pune", "ahmedabad", "jaipur",
]


def _extract_location(text: str) -> Optional[str]:
    lower = text.lower()
    for place in KNOWN_PLACES:
        if place in lower:
            return place.title()
    # Fallback: look for "in <Word>" or "at <Word>" patterns
    m = re.search(r"\b(?:in|at|for|near)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", text)
    if m:
        return m.group(1)
    return None


def _extract_days_ahead(text: str) -> int:
    lower = text.lower()
    for phrase, offset in sorted(TIME_WORDS.items(), key=lambda kv: -len(kv[0])):
        if phrase in lower:
            return offset
    m = re.search(r"in (\d+) days?", lower)
    if m:
        return int(m.group(1))
    return 0


def _extract_activity(text: str) -> Optional[str]:
    lower = text.lower()
    for activity in ACTIVITIES:
        if activity in lower:
            if activity in ("irrigat", "crop"):
                return "farming"
            if activity in ("flight",):
                return "aviation"
            if activity == "event":
                return "outdoor"
            return activity
    return None


def parse_query(text: str) -> ParsedQuery:
    lower = text.lower()
    q = ParsedQuery(raw_text=text)
    q.location = _extract_location(text)
    q.days_ahead = _extract_days_ahead(text)
    q.activity = _extract_activity(text)

    if any(w in lower for w in ALERT_WORDS):
        q.intent = INTENT_ALERTS
    elif any(w in lower for w in ADVISORY_WORDS) or q.activity:
        q.intent = INTENT_ADVISORY
    elif any(w in lower for w in HISTORY_WORDS):
        q.intent = INTENT_HISTORICAL
    elif q.days_ahead and q.days_ahead > 0:
        q.intent = INTENT_FORECAST
    elif any(w in lower for w in ["weather", "temperature", "rain", "forecast", "hot", "cold", "wind"]):
        q.intent = INTENT_CURRENT if q.days_ahead == 0 else INTENT_FORECAST
    else:
        q.intent = INTENT_UNKNOWN

    return q
