# Wetterstation Local App

## What this app does

This project turns your ESP8266 weather station into a local-first system.

- The station reads temperature, humidity, pressure, rain, wind speed, wind direction, and light.
- The station sends measurements over your local Wi-Fi to your own PC.
- A FastAPI server receives and validates the data.
- Data is saved in a local SQLite file.
- History is kept for 7 days with automatic cleanup.
- Data is available as JSON API endpoints and as a browser dashboard.

## Project structure

- `Code-Wettermonster.ino`
  - Arduino sketch for the ESP8266 weather station.
  - Upload target has been changed from cloud upload to your local server.
- `server/`
  - FastAPI application managed with uv.
  - Includes API, storage layer, retention logic, and dashboard.

## How data flows

1. ESP8266 sensors are read every configured interval.
2. ESP8266 sends data to the local endpoint (`/speichern.php`) on your PC.
3. FastAPI writes each record into SQLite.
4. Background cleanup removes records older than 7 days.
5. Clients on the same Wi-Fi can open the dashboard or call the API.

## Main features

- Local network operation (no external cloud required)
- Legacy-compatible ingest route for the existing ESP sketch
- Optional JSON ingest route for future improvements
- Latest and history API endpoints
- Simple dashboard for desktop and mobile browsers

## Running the server

Use Git Bash (recommended in your setup):

1. `cd /c/Users/user/Wetterstation/server`
2. `uv sync`
3. `export WEATHER_API_KEY=46885206`
4. `uv run weather-server`

Then open:

- Dashboard: `http://<PC-LAN-IP>:8000/`
- Health check: `http://<PC-LAN-IP>:8000/health`

## Important configuration

- Set your real PC LAN IP in `Code-Wettermonster.ino`:
  - `localServerHost`
  - `localServerPort` (default 8000)
- Keep API key in sketch and server aligned.
- Allow inbound traffic on the server port in Windows Firewall for private networks.

## Where data is stored

- Default database file: `server/data/weather.db`
- Retention window: 7 days (configurable by environment variable)

## Notes

- If `uv sync` reports file lock errors, stop any running server process and retry.
- For best reliability, keep the PC and ESP8266 on the same Wi-Fi subnet.
