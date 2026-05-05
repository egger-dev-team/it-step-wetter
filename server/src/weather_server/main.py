import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .models import WeatherIn, WeatherOut
from .storage import Storage


HOST = os.getenv("WEATHER_SERVER_HOST", "0.0.0.0")
PORT = int(os.getenv("WEATHER_SERVER_PORT", "8000"))
API_KEY = os.getenv("WEATHER_API_KEY", "46885206")
RETENTION_DAYS = int(os.getenv("WEATHER_RETENTION_DAYS", "7"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://weather:weather@db:5432/weatherstation",
)
CLEANUP_INTERVAL_SECONDS = 3600

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

storage = Storage(database_url=DATABASE_URL, retention_days=RETENTION_DAYS)


async def cleanup_loop() -> None:
    while True:
        storage.cleanup_old()
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    storage.cleanup_old()
    cleanup_task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()


app = FastAPI(title="Weatherstation Local Server", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    if not storage.ping():
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}


def ensure_key(key: str) -> None:
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid key")


def row_to_out(row) -> WeatherOut:
    return WeatherOut(
        id=row["id"],
        station_id=row["station_id"],
        temperatur=row["temperatur"],
        luftfeuchtigkeit=row["luftfeuchtigkeit"],
        luftdruck=row["luftdruck"],
        niederschlag=row["niederschlag"],
        windgeschwindigkeit=row["windgeschwindigkeit"],
        windrichtung=row["windrichtung"],
        helligkeit=row["helligkeit"],
        received_at=row["received_at"],
    )


@app.get("/speichern.php")
def speichern_php(
    id: str,
    schluessel: str,
    temperatur: float,
    luftfeuchtigkeit: float,
    luftdruck: float,
    niederschlag: float,
    windgeschwindigkeit: float,
    windrichtung: str,
    helligkeit: float,
) -> dict[str, str | int]:
    ensure_key(schluessel)
    payload = WeatherIn(
        station_id=id,
        key=schluessel,
        temperatur=temperatur,
        luftfeuchtigkeit=luftfeuchtigkeit,
        luftdruck=luftdruck,
        niederschlag=niederschlag,
        windgeschwindigkeit=windgeschwindigkeit,
        windrichtung=windrichtung,
        helligkeit=helligkeit,
    )
    row_id = storage.insert(payload)
    return {"status": "ok", "id": row_id}


@app.post("/api/weather")
def ingest_weather(payload: WeatherIn) -> dict[str, str | int]:
    ensure_key(payload.key)
    row_id = storage.insert(payload)
    return {"status": "ok", "id": row_id}


@app.get("/api/weather/latest", response_model=WeatherOut)
def latest(station_id: str | None = None):
    row = storage.latest(station_id=station_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no data")
    return row_to_out(row)


@app.get("/api/weather/history", response_model=list[WeatherOut])
def history(
    hours: int = Query(default=24, ge=1, le=24 * 7),
    station_id: str | None = None,
):
    rows = storage.history(hours=hours, station_id=station_id)
    return [row_to_out(row) for row in rows]


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    latest_row = storage.latest()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"latest": latest_row},
    )


def run() -> None:
    uvicorn.run(
        "weather_server.main:app",
        host=HOST,
        port=PORT,
        reload=False,
    )


if __name__ == "__main__":
    run()
