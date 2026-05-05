"""Download historical hourly weather data from the Open-Meteo Archive API.

Defaults to a grid point near Sankt Johann in Tirol, Austria. The Open-Meteo
Archive endpoint is free, requires no API key, and serves ERA5 reanalysis
data with hourly resolution.

Example:

    python scripts/download_history.py --start 2016-01-01 --end 2025-12-31

Output is a CSV file under ``server/data/history/`` (parquet if pyarrow is
available).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "precipitation",
    "snowfall",
    "wind_speed_10m",
    "wind_direction_10m",
    "shortwave_radiation",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=47.5217,
                        help="Latitude (default: Sankt Johann in Tirol)")
    parser.add_argument("--lon", type=float, default=12.4342,
                        help="Longitude (default: Sankt Johann in Tirol)")
    parser.add_argument("--start", type=str, default="2016-01-01",
                        help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", type=str,
                        default=(date.today() - timedelta(days=7)).isoformat(),
                        help="End date YYYY-MM-DD (inclusive). Open-Meteo "
                             "archive lags real time by ~5 days.")
    parser.add_argument("--out-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent
                        / "data" / "history",
                        help="Output directory.")
    parser.add_argument("--chunk-years", type=int, default=2,
                        help="Years per request to keep responses small.")
    parser.add_argument("--timezone", type=str, default="UTC")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite output file if it already exists.")
    return parser.parse_args()


def daterange_chunks(start: date, end: date, chunk_years: int):
    cur = start
    while cur <= end:
        chunk_end_year = cur.year + chunk_years - 1
        try:
            chunk_end = date(chunk_end_year, 12, 31)
        except ValueError:
            chunk_end = end
        if chunk_end > end:
            chunk_end = end
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def fetch_chunk(lat: float, lon: float, start: date, end: date,
                timezone: str) -> dict:
    params = {
        "latitude": f"{lat}",
        "longitude": f"{lon}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": timezone,
        "windspeed_unit": "ms",
    }
    url = f"{ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "hourly" not in data or "time" not in data["hourly"]:
                raise RuntimeError(f"Unexpected response: {data!r}")
            return data
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            backoff = 2 ** attempt
            print(f"  attempt {attempt} failed ({exc}); retrying in "
                  f"{backoff}s...", file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(
        f"Failed to fetch {start}..{end} after retries: {last_error}"
    )


def merge_hourly(rows: list[dict], chunk: dict) -> None:
    hourly = chunk["hourly"]
    times = hourly["time"]
    columns = {var: hourly.get(var, [None] * len(times))
               for var in HOURLY_VARIABLES}
    for i, ts in enumerate(times):
        row = {"time": ts}
        for var in HOURLY_VARIABLES:
            row[var] = columns[var][i]
        rows.append(row)


def write_output(rows: list[dict], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["time", *HOURLY_VARIABLES]

    parquet_path = Path(str(out_path) + ".parquet")
    try:
        import pandas as pd  # type: ignore[import-not-found]

        df = pd.DataFrame(rows, columns=fieldnames)
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        try:
            df.to_parquet(parquet_path, index=False)
            print(f"Wrote {len(df):,} rows to {parquet_path}")
            return parquet_path
        except (ImportError, ValueError) as exc:
            print(f"  parquet write unavailable ({exc}); falling back to CSV",
                  file=sys.stderr)
    except ImportError:
        pass

    csv_path = Path(str(out_path) + ".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} rows to {csv_path}")
    return csv_path


def main() -> int:
    args = parse_args()

    try:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError as exc:
        print(f"Invalid date: {exc}", file=sys.stderr)
        return 2
    if end < start:
        print("--end must be on or after --start", file=sys.stderr)
        return 2

    base_name = (f"openmeteo_{args.lat:.4f}_{args.lon:.4f}_"
                 f"{start.isoformat()}_{end.isoformat()}")
    out_path = args.out_dir / base_name
    if not args.force:
        for ext in (".parquet", ".csv"):
            existing = Path(str(out_path) + ext)
            if existing.exists():
                print(f"Output already exists: {existing} (use --force to "
                      f"overwrite)")
                return 0

    print(f"Downloading Open-Meteo Archive for ({args.lat}, {args.lon}) "
          f"from {start} to {end}")
    rows: list[dict] = []
    for chunk_start, chunk_end in daterange_chunks(start, end,
                                                   args.chunk_years):
        print(f"  fetching {chunk_start} .. {chunk_end}")
        chunk = fetch_chunk(args.lat, args.lon, chunk_start, chunk_end,
                            args.timezone)
        merge_hourly(rows, chunk)

    if not rows:
        print("No rows returned.", file=sys.stderr)
        return 1

    write_output(rows, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
