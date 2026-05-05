# Weatherstation Local Server

FastAPI server for ESP8266 weather station uploads. It stores data in a local SQLite file and keeps a rolling 7-day history.

## Features

- Compatible with original Wettermonster upload format (`GET /speichern.php`)
- Supports modern JSON ingest (`POST /api/weather`)
- Local SQLite file storage
- Automatic retention cleanup (7 days default)
- REST endpoints for latest and history
- Built-in dashboard for local Wi-Fi access

## Requirements

- Python 3.11+
- uv (https://docs.astral.sh/uv/)

## Setup

1. Open terminal in this folder:

```powershell
cd c:\Users\user\Wetterstation\server
```

2. Create virtual environment and install dependencies:

```powershell
uv sync
```

3. Optional: create `.env` from `.env.example` and adjust values.

## Run

```powershell
$env:WEATHER_SERVER_HOST="0.0.0.0"
$env:WEATHER_SERVER_PORT="8000"
$env:WEATHER_API_KEY="46885206"
uv run weather-server
```

Then open from your LAN:

- Dashboard: `http://<PC-LAN-IP>:8000/`
- Health: `http://<PC-LAN-IP>:8000/health`
- API docs: `http://<PC-LAN-IP>:8000/docs`

## API

### Legacy GET ingest (ESP-compatible)

`GET /speichern.php?id=...&schluessel=...&temperatur=...&luftfeuchtigkeit=...&luftdruck=...&niederschlag=...&windgeschwindigkeit=...&windrichtung=...&helligkeit=...`

### JSON ingest

`POST /api/weather`

```json
{
  "station_id": "1356599",
  "key": "46885206",
  "temperatur": 20.3,
  "luftfeuchtigkeit": 54.1,
  "luftdruck": 1012.8,
  "niederschlag": 0.0,
  "windgeschwindigkeit": 2.4,
  "windrichtung": "N",
  "helligkeit": 3200.0
}
```

### Read endpoints

- `GET /api/weather/latest`
- `GET /api/weather/latest?station_id=1356599`
- `GET /api/weather/history?hours=24`
- `GET /api/weather/history?hours=24&station_id=1356599`

## Data file

SQLite database path is controlled by `WEATHER_DB_PATH` (default `./data/weather.db`).

## Firewall note (Windows)

Allow inbound TCP on the configured port (default `8000`) for private networks, otherwise other devices on Wi-Fi cannot access the dashboard/API.
