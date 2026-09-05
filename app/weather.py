"""
weather.py
----------
Thin client around Open-Meteo's free, no-API-key APIs:
  - Geocoding API: turn a place name into lat/lon
  - Forecast API: current conditions + hourly/daily forecast + severe weather flags
  - Archive API: historical daily data for climate trend insights

Open-Meteo is used so the whole MVP runs without any paid keys. In a real
deployment you would swap/augment this with IMD (India Meteorological
Department) data and official cyclone/flood warnings for authoritative
alerts, as called out in the project plan.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "windspeed_10m_max",
    "weathercode",
]
CURRENT_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "weathercode",
    "windspeed_10m",
    "windgusts_10m",
]

WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherError(Exception):
    pass


async def geocode_location(name: str) -> dict:
    """Resolve a place name to lat/lon/timezone. Raises WeatherError if not found."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(GEOCODE_URL, params={"name": name, "count": 1, "language": "en"})
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results")
    if not results:
        raise WeatherError(f"Could not find a location matching '{name}'.")
    top = results[0]
    return {
        "name": top.get("name"),
        "admin1": top.get("admin1"),
        "country": top.get("country"),
        "latitude": top["latitude"],
        "longitude": top["longitude"],
        "timezone": top.get("timezone", "auto"),
    }


async def get_current_weather(location: str) -> dict:
    """get_current_weather(location) — AI tool from the project's tool architecture."""
    place = await geocode_location(location)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": ",".join(CURRENT_VARS),
                "timezone": place["timezone"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    current = data.get("current", {})
    code = current.get("weathercode")
    return {
        "location": place,
        "observed_at": current.get("time"),
        "temperature_c": current.get("temperature_2m"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "windspeed_kmh": current.get("windspeed_10m"),
        "windgusts_kmh": current.get("windgusts_10m"),
        "condition": WEATHER_CODE_MAP.get(code, "Unknown"),
        "weathercode": code,
    }


async def get_forecast(location: str, days: int = 5) -> dict:
    """get_forecast(location, date, time) — simplified to a multi-day daily forecast."""
    place = await geocode_location(location)
    days = max(1, min(days, 16))
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": ",".join(DAILY_VARS),
                "forecast_days": days,
                "timezone": place["timezone"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    daily = data.get("daily", {})
    out = []
    for i, date in enumerate(daily.get("time", [])):
        out.append(
            {
                "date": date,
                "temp_max_c": daily["temperature_2m_max"][i],
                "temp_min_c": daily["temperature_2m_min"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "rain_probability_pct": daily.get("precipitation_probability_max", [None])[i]
                if i < len(daily.get("precipitation_probability_max", []))
                else None,
                "windspeed_max_kmh": daily["windspeed_10m_max"][i],
                "condition": WEATHER_CODE_MAP.get(daily["weathercode"][i], "Unknown"),
            }
        )
    return {"location": place, "daily": out}


async def get_weather_alerts(location: str) -> dict:
    """
    get_weather_alerts(location) — Open-Meteo has no dedicated warnings feed, so
    this derives simple threshold-based alerts from the forecast (heavy rain,
    high wind, storm codes). Swap this out for IMD / official cyclone-flood
    warning feeds for production-grade alerts, as noted in the project plan.
    """
    forecast = await get_forecast(location, days=3)
    alerts = []
    for day in forecast["daily"]:
        if day["precipitation_mm"] and day["precipitation_mm"] >= 50:
            alerts.append(
                {
                    "date": day["date"],
                    "severity": "High",
                    "type": "Heavy Rainfall",
                    "message": f"Heavy rainfall expected ({day['precipitation_mm']} mm).",
                }
            )
        if day["windspeed_max_kmh"] and day["windspeed_max_kmh"] >= 50:
            alerts.append(
                {
                    "date": day["date"],
                    "severity": "High",
                    "type": "High Wind",
                    "message": f"Strong winds expected (up to {day['windspeed_max_kmh']} km/h).",
                }
            )
        if day["condition"] and "Thunderstorm" in day["condition"]:
            alerts.append(
                {
                    "date": day["date"],
                    "severity": "Moderate",
                    "type": "Thunderstorm",
                    "message": "Thunderstorm activity expected.",
                }
            )
    return {"location": forecast["location"], "alerts": alerts}


async def get_historical_weather(location: str, days_back: int = 365) -> dict:
    """get_historical_weather(location, period) — daily archive for climate insights."""
    place = await geocode_location(location)
    end = dt.date.today() - dt.timedelta(days=3)  # archive has a short lag
    start = end - dt.timedelta(days=days_back)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            ARCHIVE_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": place["timezone"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    daily = data.get("daily", {})
    return {
        "location": place,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "dates": daily.get("time", []),
        "temp_max_c": daily.get("temperature_2m_max", []),
        "temp_min_c": daily.get("temperature_2m_min", []),
        "precipitation_mm": daily.get("precipitation_sum", []),
    }
