"""
risk.py
-------
calculate_weather_risk(weather_data) — from the project's AI tool architecture.

Deterministic, explainable rule-based scoring (no ML/LLM involved) so the
result is always grounded in real numbers, per the design principle:
"Weather APIs and official warnings provide the facts; the backend
calculates risk; the LLM explains the result."

Levels: Low / Moderate / High / Severe
"""

from __future__ import annotations

from typing import Optional


def calculate_weather_risk(
    precipitation_mm: Optional[float] = 0,
    windspeed_kmh: Optional[float] = 0,
    temperature_c: Optional[float] = 25,
    condition: Optional[str] = "",
    rain_probability_pct: Optional[float] = 0,
) -> dict:
    precipitation_mm = precipitation_mm or 0
    windspeed_kmh = windspeed_kmh or 0
    temperature_c = temperature_c if temperature_c is not None else 25
    rain_probability_pct = rain_probability_pct or 0
    condition = (condition or "").lower()

    score = 0
    reasons = []

    # Rainfall
    if precipitation_mm >= 100:
        score += 4
        reasons.append(f"extremely heavy rainfall ({precipitation_mm} mm)")
    elif precipitation_mm >= 50:
        score += 3
        reasons.append(f"heavy rainfall ({precipitation_mm} mm)")
    elif precipitation_mm >= 15:
        score += 2
        reasons.append(f"moderate rainfall ({precipitation_mm} mm)")
    elif precipitation_mm >= 2:
        score += 1
        reasons.append(f"light rainfall ({precipitation_mm} mm)")

    # Wind
    if windspeed_kmh >= 90:
        score += 4
        reasons.append(f"destructive wind speeds ({windspeed_kmh} km/h)")
    elif windspeed_kmh >= 60:
        score += 3
        reasons.append(f"very strong winds ({windspeed_kmh} km/h)")
    elif windspeed_kmh >= 40:
        score += 2
        reasons.append(f"strong winds ({windspeed_kmh} km/h)")
    elif windspeed_kmh >= 25:
        score += 1
        reasons.append(f"breezy conditions ({windspeed_kmh} km/h)")

    # Extreme temperature
    if temperature_c >= 42 or temperature_c <= 2:
        score += 3
        reasons.append(f"extreme temperature ({temperature_c}°C)")
    elif temperature_c >= 38 or temperature_c <= 8:
        score += 2
        reasons.append(f"uncomfortable temperature ({temperature_c}°C)")

    # Storm indicators from condition text
    if "thunderstorm" in condition or "hail" in condition:
        score += 3
        reasons.append(f"{condition} activity")

    # Rain probability nudges the score
    if rain_probability_pct >= 80:
        score += 1
        reasons.append(f"very high rain probability ({rain_probability_pct}%)")

    if score >= 8:
        level = "Severe"
    elif score >= 5:
        level = "High"
    elif score >= 2:
        level = "Moderate"
    else:
        level = "Low"

    return {"score": score, "level": level, "reasons": reasons}
