# Weatherstation Docker Stack

This project runs a full local weather platform in Docker:

- FastAPI API for ESP8266 uploads
- PostgreSQL for persistence
- Grafana for visualization

The ESP sketch keeps using the legacy query upload format and does not need protocol changes.

## Services

- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Grafana: http://localhost:3000
- PostgreSQL: localhost:5432

## Features

- Legacy ingest route for the ESP sketch: GET /speichern.php
- JSON ingest route for future clients: POST /api/weather
- 7-day rolling retention cleanup
- Latest and history API endpoints
- Pre-provisioned Grafana PostgreSQL datasource
- Preloaded starter Grafana dashboard

## Prerequisites

- Docker Desktop with Compose enabled

## Quick Start

1. Copy environment template:

```bash
cd /c/Users/user/Wetterstation/server
cp .env.docker.example .env
```

2. Start the full stack:

```bash
docker compose up -d --build
```

3. Verify health:

```bash
curl http://127.0.0.1:8000/health
```

4. Open Grafana:

- URL: http://127.0.0.1:3000
- Login with values from .env (default admin/admin)

## ESP8266 Integration

In [Code-Wettermonster.ino](../Code-Wettermonster.ino), set:

- localServerHost to your PC LAN IP (for example 192.168.178.100)
- localServerPort to 8000

Then flash the sketch. Data should appear in:

- API history endpoint
- Grafana dashboard folder Weatherstation

## API Routes

- GET /speichern.php?id=...&schluessel=...&temperatur=...&luftfeuchtigkeit=...&luftdruck=...&niederschlag=...&windgeschwindigkeit=...&windrichtung=...&helligkeit=...
- POST /api/weather
- GET /api/weather/latest
- GET /api/weather/latest?station_id=1356599
- GET /api/weather/history?hours=24
- GET /api/weather/history?hours=24&station_id=1356599
- GET /api/forecast — 1/3/6/12/24 h precipitation-type forecast (none / rain / snow)

## Forecast model

A simple precipitation-type forecaster (3 classes: none / rain / snow) is
trained offline from ERA5 reanalysis data (Open-Meteo Archive) for a grid
point near Sankt Johann in Tirol. The trained model is loaded at startup
and exposed via `GET /api/forecast`.

Re-train (one-off, takes ~1 min):

```bash
# 1. Download ~10 years of hourly history (free, no API key)
uv run python scripts/download_history.py --start 2016-01-01 --end 2025-12-31

# 2. Train model bundle to data/models/forecast_v1.joblib
uv run python scripts/train_forecast.py
```

Override coordinates with `--lat` / `--lon` if you want a different grid
point. Restart the API container after retraining.

The forecast endpoint requires at least 6 h of recent station readings in
the database; otherwise it returns 503.

## Operations

Start:

```bash
docker compose up -d
```

Logs:

```bash
docker compose logs -f api
docker compose logs -f db
docker compose logs -f grafana
```

Stop:

```bash
docker compose down
```

Stop and remove volumes (resets DB and Grafana state):

```bash
docker compose down -v
```

## Simulate a second station

Use the included simulator to push realistic sample data from a virtual second station.

Run a short burst test:

```bash
python scripts/simulate_station.py --station-id sim-station-2 --count 20 --interval 2
```

Run continuously (default 15-second interval):

```bash
python scripts/simulate_station.py --station-id sim-station-2
```

Common options:

- `--base-url` API base URL (default `http://127.0.0.1:8000`)
- `--api-key` shared API key (default `46885206`)
- `--interval` seconds between sends
- `--count` number of messages (`0` means infinite)

This is useful when the physical station is not available and you still want dashboard activity.

## Notes

- This setup is clean-start PostgreSQL. No SQLite import is included.
- Retention is controlled by WEATHER_RETENTION_DAYS (default 7).
- For LAN access, allow inbound ports 8000 and 3000 on private networks.
