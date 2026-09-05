"""
llm.py
------
Optional LLM layer for turning grounded weather/risk/advisory data into
natural, conversational language.

By design (per the project plan's "LLM should not invent weather facts"
principle) this module NEVER asks the LLM for facts — only to phrase facts
that were already computed by weather.py / risk.py / advisory.py.

If no ANTHROPIC_API_KEY or OPENAI_API_KEY is set in the environment, it
falls back to clean template-based phrasing so the app fully works offline
/ without any paid key (useful for a demo).
"""

from __future__ import annotations

import os

USE_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
USE_OPENAI = bool(os.environ.get("OPENAI_API_KEY"))


def _template_response(context: dict) -> str:
    """Deterministic, no-LLM fallback phrasing."""
    parts = []
    if "current" in context:
        c = context["current"]
        parts.append(
            f"In {c['location']['name']}, it's currently {c['temperature_c']}°C "
            f"with {c['condition'].lower()}. Humidity is {c['humidity_pct']}% and "
            f"wind speed is {c['windspeed_kmh']} km/h."
        )
    if "forecast_day" in context:
        f = context["forecast_day"]
        parts.append(
            f"On {f['date']}, expect a high of {f['temp_max_c']}°C and a low of "
            f"{f['temp_min_c']}°C, with {f['condition'].lower()} and "
            f"{f['precipitation_mm']} mm of rain expected."
        )
    if "risk" in context:
        r = context["risk"]
        if r["reasons"]:
            reason_text = "; ".join(r["reasons"])
            parts.append(f"Risk level: {r['level']} — due to {reason_text}.")
        else:
            parts.append(f"Risk level: {r['level']}.")
    if "advisory" in context:
        a = context["advisory"]
        parts.append(f"Advisory for {a['activity']}: {a['recommendation']}")
    if "alerts" in context:
        alerts = context["alerts"]
        if alerts:
            for al in alerts:
                parts.append(f"⚠ {al['severity']} {al['type']} alert on {al['date']}: {al['message']}")
        else:
            parts.append("No active weather alerts for this location right now.")
    if not parts:
        parts.append(
            "I can help with current weather, forecasts, alerts, historical trends, "
            "and activity advice (farming, travel, fishing, outdoor events). "
            "Try asking something like 'Will it rain in Madurai tomorrow?'"
        )
    return " ".join(parts)


async def phrase_response(context: dict, tamil: bool = False) -> str:
    """
    Turn a structured context dict (already-computed facts) into a natural
    language reply. Uses a real LLM if configured, otherwise templates.
    `tamil` requests a Tamil-language reply for the voice assistant feature.
    """
    text = _template_response(context)

    if not (USE_ANTHROPIC or USE_OPENAI):
        return text  # offline template mode — fully functional without keys

    prompt = (
        "Rewrite the following grounded weather information into a warm, "
        "concise, natural conversational reply. Do NOT add any new facts, "
        "numbers, or claims not present in the text. "
        + ("Reply in Tamil. " if tamil else "Reply in English. ")
        + f"\n\nFacts:\n{text}"
    )

    try:
        if USE_ANTHROPIC:
            import anthropic

            client = anthropic.AsyncAnthropic()
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in resp.content if hasattr(block, "text"))
        elif USE_OPENAI:
            from openai import AsyncOpenAI

            client = AsyncOpenAI()
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            return resp.choices[0].message.content
    except Exception:
        # Any LLM failure (no network, bad key, etc.) — fall back gracefully.
        return text

    return text
