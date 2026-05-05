#!/usr/bin/env python3
import argparse
import json
import math
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


WIND_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


@dataclass
class SimulatorState:
    temperature: float
    humidity: float
    pressure: float
    precipitation: float
    wind_speed: float
    luminosity: float


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_payload(state: SimulatorState, station_id: str, api_key: str, tick: int) -> dict:
    # Smooth day-like cycle so charts look realistic, plus small random drift.
    now = datetime.now(timezone.utc)
    hour_fraction = now.hour + (now.minute / 60.0)
    day_wave = math.sin((hour_fraction / 24.0) * 2.0 * math.pi)

    state.temperature = clamp(16.0 + (day_wave * 7.0) + random.uniform(-0.3, 0.3), -20.0, 45.0)
    state.humidity = clamp(62.0 - (day_wave * 14.0) + random.uniform(-1.0, 1.0), 20.0, 100.0)
    state.pressure = clamp(state.pressure + random.uniform(-0.25, 0.25), 980.0, 1040.0)

    rain_spike = random.random() < 0.08
    if rain_spike:
        state.precipitation = clamp(random.uniform(0.2, 3.0), 0.0, 10.0)
    else:
        state.precipitation = clamp(state.precipitation * random.uniform(0.3, 0.8), 0.0, 10.0)

    state.wind_speed = clamp(abs(state.wind_speed + random.uniform(-0.6, 0.8)), 0.0, 24.0)

    daylight = max(0.0, day_wave)
    cloud_factor = random.uniform(0.55, 1.0)
    state.luminosity = clamp((daylight * 85000.0 * cloud_factor) + random.uniform(0.0, 200.0), 0.0, 120000.0)

    direction = WIND_DIRECTIONS[(tick + random.randint(0, 2)) % len(WIND_DIRECTIONS)]

    return {
        "station_id": station_id,
        "key": api_key,
        "temperatur": round(state.temperature, 2),
        "luftfeuchtigkeit": round(state.humidity, 2),
        "luftdruck": round(state.pressure, 2),
        "niederschlag": round(state.precipitation, 2),
        "windgeschwindigkeit": round(state.wind_speed, 2),
        "windrichtung": direction,
        "helligkeit": round(state.luminosity, 2),
    }


def post_payload(api_url: str, payload: dict, timeout: int) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.getcode()
        response_body = resp.read().decode("utf-8", errors="replace")
        return status, response_body


def main() -> None:
    parser = argparse.ArgumentParser(description="Weather station simulator for dashboard testing")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--station-id", default="sim-station-2", help="Virtual station ID")
    parser.add_argument("--api-key", default="46885206", help="API key")
    parser.add_argument("--interval", type=float, default=15.0, help="Seconds between sends")
    parser.add_argument("--count", type=int, default=0, help="Messages to send (0 = infinite)")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout seconds")
    args = parser.parse_args()

    api_url = args.base_url.rstrip("/") + "/api/weather"
    state = SimulatorState(
        temperature=20.0,
        humidity=55.0,
        pressure=1012.0,
        precipitation=0.0,
        wind_speed=3.5,
        luminosity=2000.0,
    )

    sent = 0
    tick = 0
    while args.count == 0 or sent < args.count:
        payload = build_payload(state, args.station_id, args.api_key, tick)
        tick += 1

        try:
            status, body = post_payload(api_url, payload, args.timeout)
            print(f"[{datetime.now().isoformat(timespec='seconds')}] {args.station_id} -> {status} {body}")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP error {exc.code}: {error_body}")
        except Exception as exc:  # noqa: BLE001
            print(f"Send failed: {exc}")

        sent += 1
        if args.count == 0 or sent < args.count:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
