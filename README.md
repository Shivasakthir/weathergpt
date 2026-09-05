# WeatherGPT — MVP (Weeks 1–3 of the project plan)

An AI-powered weather decision-support app: real-time weather, natural-language
chat, a risk engine, activity advisories ("What Should I Do?"), a risk map,
severe-weather alerts, Tamil voice interaction, and climate insights — all in
a single Python (FastAPI) backend + browser frontend, with **no API keys required**.

This implements the plan's realistic 4-week MVP scope:
- Week 1: real weather data + NLU chat core ✅
- Week 2: risk engine + activity advisory rules ✅
- Week 3: Tamil voice, risk map, climate insights ✅
- Week 4 (integration/testing/demo) is on you once you're running it locally —
  the codebase is structured to make that easy (see "Project structure" below).

## Why FastAPI + browser frontend, not Flutter?

The original plan calls for a Flutter mobile frontend. Building and packaging
a compiled mobile app isn't something that can be produced as a downloadable
file here. Instead, this MVP ships as a **local web app** you run with one
command — it works in any browser, including on a phone, and every backend
piece (the "AI tool architecture" — `get_current_weather`, `get_forecast`,
`get_weather_alerts`, `get_historical_weather`, `calculate_weather_risk`,
`generate_activity_advisory`) is written as plain, testable Python functions.
If you want a real Flutter app for the demo, these same REST endpoints
(`/api/...`) are exactly what a Flutter frontend would call — porting the
UI logic in `static/index.html` to Flutter widgets is a well-scoped Week 4 task.

## Quick start

```bash
cd weathergpt
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000** in your browser. You need an internet
connection (it calls the free Open-Meteo weather API — no key needed).

## Project structure

```
weathergpt/
├── app/
│   ├── main.py       # FastAPI app + all /api/* endpoints + chat orchestration
│   ├── weather.py    # Weather data client (Open-Meteo: current/forecast/alerts/historical)
│   ├── nlu.py        # Rule-based intent + entity extraction from user text
│   ├── risk.py        # calculate_weather_risk() — Low/Moderate/High/Severe scoring
│   ├── advisory.py    # generate_activity_advisory() — farming/travel/fishing/outdoor/aviation
│   └── llm.py         # Optional LLM phrasing layer (templates by default, no key needed)
├── static/
│   └── index.html     # Frontend: Chat, Advisory, Risk Map, Alerts, Insights screens
├── requirements.txt
└── README.md
```

## Features implemented

- **Chat** (`/api/chat`): ask things like *"Will it rain in Madurai tomorrow evening?"*,
  *"Any alerts for Chennai?"*, *"Climate trend for Coimbatore"*, *"Should I irrigate my
  field tomorrow?"*. Rule-based NLU extracts location/date/activity; real weather data
  answers the question; an optional LLM only rephrases the (already-correct) facts.
- **Tamil voice**: switch the language dropdown to Tamil — the mic button uses your
  browser's built-in speech recognition (`ta-IN`) and replies are read aloud via
  speech synthesis. Works fully offline of any paid voice API (uses the Web Speech API).
- **Risk engine**: deterministic scoring from rainfall, wind, temperature and storm
  conditions into Low / Moderate / High / Severe, with human-readable reasons.
- **"What Should I Do?" advisory mode**: pick an activity (farming, travel, fishing,
  outdoor event, aviation) and a day, and get a concrete, risk-grounded recommendation.
- **Risk map**: plots several cities on a Leaflet map, color-coded by current risk level.
- **Alerts**: threshold-derived heavy-rain / high-wind / thunderstorm alerts per city.
  (Swap in IMD or official cyclone/flood feeds here for production use — see the
  docstring in `app/weather.py::get_weather_alerts`.)
- **Climate insights**: charts of the last ~6 months of daily high/low temperatures
  and total rainfall for any location, using Open-Meteo's historical archive.

## Using a real LLM instead of the built-in templates (optional)

By default, chat replies are phrased with clean, deterministic templates
(no key required, works offline for the wording step — though weather data
itself still needs internet). To use a real LLM to *phrase* replies (it never
generates the underlying facts — see `app/llm.py`), set one of:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...
```

and install the matching optional package from `requirements.txt`.

## Extending for Week 4 (per your plan)

- **Aviation-grade / cyclone-grade alerts**: replace the threshold logic in
  `get_weather_alerts` with a real IMD / official warnings feed.
- **Multilingual beyond Tamil**: the NLU and LLM layer already accept a
  language flag — add more `<option>` entries in `index.html` and language
  codes recognized by the Web Speech API (e.g. `hi-IN`, `te-IN`).
- **Mobile app**: point a Flutter (or React Native) app at these same
  `/api/*` endpoints instead of the bundled HTML frontend.
- **Scalability**: containerize with Docker (a `Dockerfile` is trivial to add:
  `FROM python:3.11-slim`, `pip install -r requirements.txt`, `CMD uvicorn ...`)
  and put behind a reverse proxy for demo day.
