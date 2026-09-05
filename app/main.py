"""
main.py
-------
WeatherGPT MVP backend (Week 1-3 scope from the project plan):
  - Real-time weather + forecast + alerts (Open-Meteo)
  - Natural language chat endpoint (NLU -> tools -> risk/advisory -> LLM phrasing)
  - Risk scoring and activity advisories ("What Should I Do?" mode)
  - Historical climate insights for the Insights screen
  - Static frontend (chat, map, alerts, insights) served from /

Run with:  uvicorn app.main:app --reload
Then open: http://127.0.0.1:8000
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import weather, risk as risk_engine, advisory as advisory_engine, nlu, llm

app = FastAPI(title="WeatherGPT", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ---------- Request/response models ----------

class ChatRequest(BaseModel):
    message: str
    location_hint: Optional[str] = None
    tamil: bool = False


class ChatResponse(BaseModel):
    reply: str
    intent: str
    location: Optional[str] = None
    data: dict = {}


# ---------- Core weather endpoints (AI tool architecture, exposed as REST) ----------

@app.get("/api/weather/current")
async def api_current_weather(location: str):
    try:
        return await weather.get_current_weather(location)
    except weather.WeatherError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/weather/forecast")
async def api_forecast(location: str, days: int = 5):
    try:
        return await weather.get_forecast(location, days=days)
    except weather.WeatherError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/weather/alerts")
async def api_alerts(location: str):
    try:
        return await weather.get_weather_alerts(location)
    except weather.WeatherError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/weather/historical")
async def api_historical(location: str, days_back: int = 365):
    try:
        return await weather.get_historical_weather(location, days_back=days_back)
    except weather.WeatherError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/risk")
async def api_risk(location: str, days_ahead: int = 0):
    try:
        if days_ahead == 0:
            cur = await weather.get_current_weather(location)
            r = risk_engine.calculate_weather_risk(
                precipitation_mm=cur["precipitation_mm"],
                windspeed_kmh=cur["windspeed_kmh"],
                temperature_c=cur["temperature_c"],
                condition=cur["condition"],
            )
            return {"location": cur["location"], "risk": r, "basis": cur}
        else:
            fc = await weather.get_forecast(location, days=days_ahead + 1)
            day = fc["daily"][min(days_ahead, len(fc["daily"]) - 1)]
            r = risk_engine.calculate_weather_risk(
                precipitation_mm=day["precipitation_mm"],
                windspeed_kmh=day["windspeed_max_kmh"],
                temperature_c=day["temp_max_c"],
                condition=day["condition"],
                rain_probability_pct=day.get("rain_probability_pct"),
            )
            return {"location": fc["location"], "risk": r, "basis": day}
    except weather.WeatherError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/advisory")
async def api_advisory(location: str, activity: str, days_ahead: int = 0):
    try:
        if days_ahead == 0:
            basis = await weather.get_current_weather(location)
            precip, wind, temp, cond, rainprob = (
                basis["precipitation_mm"], basis["windspeed_kmh"],
                basis["temperature_c"], basis["condition"], 0,
            )
            loc = basis["location"]
        else:
            fc = await weather.get_forecast(location, days=days_ahead + 1)
            day = fc["daily"][min(days_ahead, len(fc["daily"]) - 1)]
            precip, wind, temp, cond, rainprob = (
                day["precipitation_mm"], day["windspeed_max_kmh"],
                day["temp_max_c"], day["condition"], day.get("rain_probability_pct"),
            )
            loc = fc["location"]

        r = risk_engine.calculate_weather_risk(precip, wind, temp, cond, rainprob)
        adv = advisory_engine.generate_activity_advisory(
            activity, precip, wind, temp, r["level"], rainprob
        )
        return {"location": loc, "risk": r, "advisory": adv}
    except weather.WeatherError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------- Risk map: batch risk for several locations at once ----------

@app.get("/api/risk_map")
async def api_risk_map(locations: str):
    """locations = comma-separated place names, e.g. 'Chennai,Madurai,Coimbatore'"""
    names = [n.strip() for n in locations.split(",") if n.strip()]
    results = []
    for name in names:
        try:
            cur = await weather.get_current_weather(name)
            r = risk_engine.calculate_weather_risk(
                precipitation_mm=cur["precipitation_mm"],
                windspeed_kmh=cur["windspeed_kmh"],
                temperature_c=cur["temperature_c"],
                condition=cur["condition"],
            )
            results.append({"location": cur["location"], "current": cur, "risk": r})
        except weather.WeatherError:
            continue
    return {"results": results}


# ---------- Conversational chat endpoint (the WeatherGPT AI core) ----------

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    parsed = nlu.parse_query(req.message)
    location = parsed.location or req.location_hint

    if not location:
        reply = await llm.phrase_response({}, tamil=req.tamil)
        return ChatResponse(
            reply="Which location should I check? " + reply,
            intent=parsed.intent,
        )

    try:
        context: dict = {}
        data: dict = {}

        if parsed.intent == nlu.INTENT_ALERTS:
            alerts_data = await weather.get_weather_alerts(location)
            context["alerts"] = alerts_data["alerts"]
            data = alerts_data

        elif parsed.intent == nlu.INTENT_HISTORICAL:
            hist = await weather.get_historical_weather(location, days_back=180)
            avg_temp = (
                sum(hist["temp_max_c"]) / len(hist["temp_max_c"]) if hist["temp_max_c"] else None
            )
            total_rain = sum(hist["precipitation_mm"]) if hist["precipitation_mm"] else 0
            context["current"] = None
            data = {
                "location": hist["location"],
                "avg_high_c": round(avg_temp, 1) if avg_temp else None,
                "total_precipitation_mm": round(total_rain, 1),
                "period_days": len(hist["dates"]),
            }
            context = {
                "forecast_day": None,
            }
            # Build a small custom fact string for historical since it doesn't fit current/forecast shape
            fact_text = (
                f"Over the last {data['period_days']} days in {data['location']['name']}, "
                f"the average daily high was {data['avg_high_c']}°C and total rainfall was "
                f"{data['total_precipitation_mm']} mm."
            )
            reply = await llm.phrase_response({"_raw": fact_text}, tamil=req.tamil) if False else fact_text
            return ChatResponse(reply=reply, intent=parsed.intent, location=location, data=data)

        elif parsed.intent == nlu.INTENT_ADVISORY:
            days_ahead = parsed.days_ahead
            if days_ahead == 0:
                basis = await weather.get_current_weather(location)
                precip, wind, temp, cond, rainprob = (
                    basis["precipitation_mm"], basis["windspeed_kmh"],
                    basis["temperature_c"], basis["condition"], 0,
                )
            else:
                fc = await weather.get_forecast(location, days=days_ahead + 1)
                day = fc["daily"][min(days_ahead, len(fc["daily"]) - 1)]
                precip, wind, temp, cond, rainprob = (
                    day["precipitation_mm"], day["windspeed_max_kmh"],
                    day["temp_max_c"], day["condition"], day.get("rain_probability_pct"),
                )
            r = risk_engine.calculate_weather_risk(precip, wind, temp, cond, rainprob)
            activity = parsed.activity or "outdoor"
            adv = advisory_engine.generate_activity_advisory(activity, precip, wind, temp, r["level"], rainprob)
            context["risk"] = r
            context["advisory"] = adv
            data = {"risk": r, "advisory": adv}

        elif parsed.intent == nlu.INTENT_FORECAST:
            days_ahead = max(parsed.days_ahead, 1)
            fc = await weather.get_forecast(location, days=days_ahead + 1)
            day = fc["daily"][min(days_ahead, len(fc["daily"]) - 1)]
            r = risk_engine.calculate_weather_risk(
                precipitation_mm=day["precipitation_mm"],
                windspeed_kmh=day["windspeed_max_kmh"],
                temperature_c=day["temp_max_c"],
                condition=day["condition"],
                rain_probability_pct=day.get("rain_probability_pct"),
            )
            context["forecast_day"] = day
            context["risk"] = r
            data = {"forecast": day, "risk": r}

        else:  # current weather / unknown -> default to current
            cur = await weather.get_current_weather(location)
            r = risk_engine.calculate_weather_risk(
                precipitation_mm=cur["precipitation_mm"],
                windspeed_kmh=cur["windspeed_kmh"],
                temperature_c=cur["temperature_c"],
                condition=cur["condition"],
            )
            context["current"] = cur
            context["risk"] = r
            data = {"current": cur, "risk": r}

        reply = await llm.phrase_response(context, tamil=req.tamil)
        return ChatResponse(reply=reply, intent=parsed.intent, location=location, data=data)

    except weather.WeatherError as e:
        return ChatResponse(reply=str(e), intent=parsed.intent, location=location)


# ---------- Serve frontend ----------

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
