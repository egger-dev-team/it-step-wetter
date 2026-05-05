"""Seed the database with backdated hourly readings.

Useful to get the forecast endpoint past its 6h history requirement during
local development. Inserts realistic synthetic rows once per hour for the
last N hours plus the current time.

Usage:

    uv run python scripts/seed_backfill.py
    uv run python scripts/seed_backfill.py --hours 12 --station-id sim-backfill
"""

from __future__ import annotations

import argparse
import math
import os
import random
from datetime import datetime, timedelta, timezone

import psycopg


WIND_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def build_row(ts: datetime) -> dict:
    hour_fraction = ts.hour + ts.minute / 60.0
    day_wave = math.sin((hour_fraction / 24.0) * 2.0 * math.pi)
    return {
        "temperatur": round(16.0 + day_wave * 7.0 + random.uniform(-0.3, 0.3), 2),
        "luftfeuchtigkeit": round(
            max(20.0, min(100.0, 62.0 - day_wave * 14.0
                          + random.uniform(-1.0, 1.0))), 2),
        "luftdruck": round(1012.0 + random.uniform(-1.5, 1.5), 2),
        "niederschlag": 0.0 if random.random() > 0.1
                        else round(random.uniform(0.2, 1.5), 2),
        "windgeschwindigkeit": round(abs(2.0 + random.uniform(-1.0, 1.5)), 2),
        "windrichtung": random.choice(WIND_DIRECTIONS),
        "helligkeit": round(max(0.0, day_wave) * 70000.0
                            + random.uniform(0.0, 200.0), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url",
                        default=os.getenv("DATABASE_URL",
                                          "postgresql://weather:weather"
                                          "@127.0.0.1:5432/weatherstation"))
    parser.add_argument("--station-id", default="sim-backfill")
    parser.add_argument("--hours", type=int, default=8,
                        help="How many hours of history to seed.")
    parser.add_argument("--per-hour", type=int, default=2,
                        help="Samples per hour (>=1).")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    interval = timedelta(minutes=60 // max(1, args.per_hour))
    total = args.hours * args.per_hour + 1
    rows = []
    for i in range(total):
        ts = now - i * interval
        row = build_row(ts)
        rows.append((args.station_id, row["temperatur"],
                     row["luftfeuchtigkeit"], row["luftdruck"],
                     row["niederschlag"], row["windgeschwindigkeit"],
                     row["windrichtung"], row["helligkeit"], ts))

    with psycopg.connect(args.database_url) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO weather_records (
                    station_id, temperatur, luftfeuchtigkeit, luftdruck,
                    niederschlag, windgeschwindigkeit, windrichtung,
                    helligkeit, received_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()

    print(f"Inserted {len(rows)} rows for station '{args.station_id}' "
          f"spanning {args.hours} h ending {now.isoformat()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
