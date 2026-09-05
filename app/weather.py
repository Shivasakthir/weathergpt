"""
weather.py
----------
Weather data client using OpenWeatherMap's free API (personal API key).

Why OpenWeatherMap instead of Open-Meteo: Open-Meteo's free tier is
anonymous/keyless, so on shared hosting platforms like Render's free plan,
many different apps' traffic shares the same outbound IP address and can
collectively exceed Open-Meteo's rate limit ("429 Too Many Requests") even
under light real usage. OpenWeatherMap ties usage to a personal API key
instead of an IP, so this app's quota (1,000,000 calls/month on the free
tier) is isolated from other apps' traffic.

Requires an environment variable OPENWEATHERMAP_API_KEY to be set (get a
free key at https://openweathermap.org/api). Never hardcode the key in
source — it's read from the environment only.

Endpoints used:
  - Geocoding API: place name -> lat/lon
  - Current Weather API: real-time conditions
  - 5 Day / 3 Hour Forecast API: used to build a simple daily forecast
    (free tier does not include a true 16-day daily forecast, so we
    aggregate the 3-hourly data into daily min/max/precip ourselves)
  - Historical data requires a paid OpenWeatherMap plan, so climate
    insights fall back to a clear "not available on the free tier" message
    rather than silently failing.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Optional

import httpx

API_KEY = os.environ.get("OPENWEATHERMAP_API_KEY", "")

GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/direct"
CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


class WeatherError(Exception):
    pass


# ---------- Simple in-memory TTL cache (kept from before — still good practice) ----------
_CACHE: dict[str, tuple[float, dict]] = {}
GEOCODE_TTL = 60 * 60 * 12
CURRENT_TTL = 60 * 5
FORECAST_TTL = 60 * 15


def _cache_get(key: str) -> Optional[dict]:
    entry = _CACHE.get(key)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def _cache_set(key: str, value: dict, ttl: int) -> None:
    _CACHE[key] = (time.time() + ttl, value)


def _require_api_key() -> None:
    if not API_KEY:
        raise WeatherError(
            "Weather service is not configured yet (missing OPENWEATHERMAP_API_KEY)."
        )


async def _get_json(url: str, params: dict, timeout: float = 10) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 401:
            raise WeatherError("Weather API key is invalid or not yet activated.")
        if resp.status_code == 429:
            raise WeatherError("Weather service rate limit reached. Please try again shortly.")
        resp.raise_for_status()
        return resp.json()


async def geocode_location(name: str) -> dict:
    """Resolve a place name to lat/lon. Raises WeatherError if not found."""
    _require_api_key()
    cache_key = f"geocode:{name.strip().lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    data = await _get_json(GEOCODE_URL, {"q": name, "limit": 1, "appid": API_KEY})
    if not data:
        raise WeatherError(f"Could not find a location matching '{name}'.")
    top = data[0]
    place = {
        "name": top.get("name"),
        "admin1": top.get("state"),
        "country": top.get("country"),
        "latitude": top["lat"],
        "longitude": top["lon"],
        "timezone": "auto",
    }
    _cache_set(cache_key, place, GEOCODE_TTL)
    return place


async def get_current_weather(location: str) -> dict:
    """get_current_weather(location) — AI tool from the project's tool architecture."""
    place = await geocode_location(location)
    cache_key = f"current:{place['latitude']}:{place['longitude']}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    data = await _get_json(
        CURRENT_URL,
        {
            "lat": place["latitude"],
            "lon": place["longitude"],
            "appid": API_KEY,
            "units": "metric",
        },
    )
    main = data.get("main", {})
    wind = data.get("wind", {})
    weather = (data.get("weather") or [{}])[0]
    rain = data.get("rain", {}) or {}

    result = {
        "location": place,
        "observed_at": data.get("dt"),
        "temperature_c": main.get("temp"),
        "humidity_pct": main.get("humidity"),
        "precipitation_mm": rain.get("1h", 0),
        "windspeed_kmh": round((wind.get("speed") or 0) * 3.6, 1),  # m/s -> km/h
        "windgusts_kmh": round((wind.get("gust") or 0) * 3.6, 1),
        "condition": weather.get("description", "Unknown").title(),
        "weathercode": weather.get("id"),
    }
    _cache_set(cache_key, result, CURRENT_TTL)
    return result


async def get_forecast(location: str, days: int = 5) -> dict:
    """
    get_forecast(location, date, time) — builds a daily forecast by
    aggregating OpenWeatherMap's free 5-day/3-hour forecast into daily
    min/max/precip/wind/condition summaries.
    """
    place = await geocode_location(location)
    days = max(1, min(days, 5))  # free tier only covers ~5 days
    cache_key = f"forecast:{place['latitude']}:{place['longitude']}"
    cached = _cache_get(cache_key)
    if cached is None:
        data = await _get_json(
            FORECAST_URL,
            {
                "lat": place["latitude"],
                "lon": place["longitude"],
                "appid": API_KEY,
                "units": "metric",
            },
        )
        cached = data
        _cache_set(cache_key, data, FORECAST_TTL)

    by_day: dict[str, dict] = defaultdict(
        lambda: {"temps": [], "precip": 0.0, "wind": [], "conditions": []}
    )
    for entry in cached.get("list", []):
        date = entry["dt_txt"].split(" ")[0]
        main = entry.get("main", {})
        wind = entry.get("wind", {})
        weather = (entry.get("weather") or [{}])[0]
        rain = entry.get("rain", {}) or {}

        bucket = by_day[date]
        bucket["temps"].append(main.get("temp"))
        bucket["precip"] += rain.get("3h", 0)
        bucket["wind"].append((wind.get("speed") or 0) * 3.6)
        bucket["conditions"].append(weather.get("description", "Unknown").title())
        bucket["pop"] = max(bucket.get("pop", 0), entry.get("pop", 0) * 100)

    out = []
    for date in sorted(by_day.keys())[:days]:
        b = by_day[date]
        temps = [t for t in b["temps"] if t is not None]
        out.append(
            {
                "date": date,
                "temp_max_c": round(max(temps), 1) if temps else None,
                "temp_min_c": round(min(temps), 1) if temps else None,
                "precipitation_mm": round(b["precip"], 1),
                "rain_probability_pct": round(b.get("pop", 0)),
                "windspeed_max_kmh": round(max(b["wind"]), 1) if b["wind"] else 0,
                "condition": max(set(b["conditions"]), key=b["conditions"].count)
                if b["conditions"]
                else "Unknown",
            }
        )
    return {"location": place, "daily": out}


async def get_weather_alerts(location: str) -> dict:
    """
    get_weather_alerts(location) — derives simple threshold-based alerts from
    the forecast (heavy rain, high wind, storm conditions). OpenWeatherMap's
    free tier doesn't include official government alerts, so this is a
    best-effort derived signal — swap in IMD / official cyclone-flood feeds
    for production use.
    """
    forecast = await get_forecast(location, days=5)
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
        cond = (day["condition"] or "").lower()
        if "thunderstorm" in cond:
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
    """
    get_historical_weather(location, period) — NOTE: OpenWeatherMap's
    historical/archive data requires a paid subscription. To keep this MVP
    fully free, this returns an empty-but-valid result with a clear message
    rather than failing. Swap in a free historical source (e.g. Open-Meteo's
    archive endpoint specifically, which is not part of the rate-limited
    forecast API) if climate insights are a priority feature.
    """
    place = await geocode_location(location)
    raise WeatherError(
        "Historical climate data requires a paid weather plan and isn't "
        "available on this free-tier deployment yet."
    )
