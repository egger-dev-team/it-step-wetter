import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import WeatherIn, WeatherOut, ForecastItem, ForecastResponse
from .storage import Storage
from .forecast import Forecaster, ForecastError, reference_time_utc


HOST = os.getenv("WEATHER_SERVER_HOST", "0.0.0.0")
PORT = int(os.getenv("WEATHER_SERVER_PORT", "8000"))
API_KEY = os.getenv("WEATHER_API_KEY", "46885206")
RETENTION_DAYS = int(os.getenv("WEATHER_RETENTION_DAYS", "7"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://weather:weather@db:5432/weatherstation",
)
FORECAST_MODEL_PATH = os.getenv(
    "WEATHER_FORECAST_MODEL",
    str(Path(__file__).resolve().parent.parent.parent
        / "data" / "models" / "forecast_v1.joblib"),
)
FORECAST_HISTORY_HOURS = int(os.getenv("WEATHER_FORECAST_HISTORY_HOURS", "12"))
CLEANUP_INTERVAL_SECONDS = 3600

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
STATIC_DIR = BASE_DIR / "static"

storage = Storage(database_url=DATABASE_URL, retention_days=RETENTION_DAYS)
forecaster = Forecaster(model_path=FORECAST_MODEL_PATH)


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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


@app.get("/api/stations")
def stations() -> list[dict]:
    return [
        {
            "station_id": row["station_id"],
            "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
            "sample_count": int(row["sample_count"]),
        }
        for row in storage.stations()
    ]


@app.get("/api/forecast", response_model=ForecastResponse)
def forecast(station_id: str | None = None) -> ForecastResponse:
    if not forecaster.is_available:
        raise HTTPException(
            status_code=503,
            detail=f"forecast model not available at {FORECAST_MODEL_PATH}",
        )
    rows = storage.history(
        hours=FORECAST_HISTORY_HOURS, station_id=station_id
    )
    if not rows:
        raise HTTPException(
            status_code=503,
            detail="no station readings available for forecast",
        )
    try:
        predictions = forecaster.predict(rows)
        meta = forecaster.metadata()
    except ForecastError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ForecastResponse(
        generated_at=reference_time_utc(),
        class_labels=meta["class_labels"],
        horizons=[
            ForecastItem(
                horizon_hours=p.horizon_hours,
                label=p.label,
                probabilities=p.probabilities,
            )
            for p in predictions
        ],
    )


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
