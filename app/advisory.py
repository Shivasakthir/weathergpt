"""
advisory.py
-----------
generate_activity_advisory(activity, weather_data, risk) — from the project's
AI tool architecture. This is the "What Should I Do?" decision-support mode.

Pure rule-based logic: given an activity + real weather numbers + the risk
level from risk.py, produce a concrete recommendation. The LLM layer (see
app/llm.py / main.py) only rephrases this into natural, conversational text —
it never overrides the recommendation itself.
"""

from __future__ import annotations

from typing import Optional


def generate_activity_advisory(
    activity: str,
    precipitation_mm: float,
    windspeed_kmh: float,
    temperature_c: float,
    risk_level: str,
    rain_probability_pct: Optional[float] = 0,
) -> dict:
    activity = (activity or "").lower()
    rain_probability_pct = rain_probability_pct or 0
    recommendation = "No specific concerns — conditions look normal."
    proceed = True

    if activity in ("farming",):
        if precipitation_mm >= 15 or rain_probability_pct >= 70:
            recommendation = "Delay irrigation — significant rainfall is expected, which should meet crop water needs."
            proceed = False
        elif temperature_c >= 40:
            recommendation = "Irrigate early morning or evening to reduce water loss in extreme heat."
        elif risk_level in ("High", "Severe"):
            recommendation = "Postpone field work and secure equipment — hazardous weather is expected."
            proceed = False
        else:
            recommendation = "Conditions are suitable for normal irrigation and field work."

    elif activity in ("travel",):
        if risk_level == "Severe":
            recommendation = "Avoid travel if possible — conditions are hazardous."
            proceed = False
        elif risk_level == "High":
            recommendation = "Travel with caution, allow extra time, and monitor alerts closely."
        elif precipitation_mm >= 15:
            recommendation = "Expect delays due to rain — carry rain protection and drive carefully."
        else:
            recommendation = "Good conditions for travel."

    elif activity in ("fishing",):
        if windspeed_kmh >= 40 or risk_level in ("High", "Severe"):
            recommendation = "Do not venture into open water — high winds/rough seas expected."
            proceed = False
        elif windspeed_kmh >= 25:
            recommendation = "Fish close to shore and monitor conditions; winds are picking up."
        else:
            recommendation = "Conditions are favorable for fishing."

    elif activity in ("outdoor",):
        if risk_level in ("High", "Severe"):
            recommendation = "Reschedule the outdoor event — unsafe weather is expected."
            proceed = False
        elif precipitation_mm >= 5 or rain_probability_pct >= 50:
            recommendation = "Have a rain backup plan (tent/indoor venue) — rain is likely."
        elif temperature_c >= 38:
            recommendation = "Plan for shade, hydration, and shorter outdoor exposure due to heat."
        else:
            recommendation = "Good conditions for an outdoor event."

    elif activity in ("aviation",):
        if windspeed_kmh >= 50 or risk_level in ("High", "Severe"):
            recommendation = "Expect possible delays/diversions — high winds or severe weather in the area."
            proceed = False
        elif "thunderstorm" in "" :
            pass
        else:
            recommendation = "No major weather concerns for flight operations at this time."

    return {
        "activity": activity or "general",
        "proceed": proceed,
        "recommendation": recommendation,
        "risk_level": risk_level,
    }
