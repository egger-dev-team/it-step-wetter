import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import WeatherIn


@dataclass
class Storage:
    db_path: Path
    retention_days: int

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT NOT NULL,
                    temperatur REAL NOT NULL,
                    luftfeuchtigkeit REAL NOT NULL,
                    luftdruck REAL NOT NULL,
                    niederschlag REAL NOT NULL,
                    windgeschwindigkeit REAL NOT NULL,
                    windrichtung TEXT NOT NULL,
                    helligkeit REAL NOT NULL,
                    received_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_received_at
                ON weather_records(received_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_station_received
                ON weather_records(station_id, received_at)
                """
            )
            conn.commit()

    def insert(self, payload: WeatherIn) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO weather_records (
                    station_id, temperatur, luftfeuchtigkeit, luftdruck,
                    niederschlag, windgeschwindigkeit, windrichtung,
                    helligkeit, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.station_id,
                    payload.temperatur,
                    payload.luftfeuchtigkeit,
                    payload.luftdruck,
                    payload.niederschlag,
                    payload.windgeschwindigkeit,
                    payload.windrichtung,
                    payload.helligkeit,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def cleanup_old(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM weather_records WHERE received_at < ?",
                (cutoff.isoformat(),),
            )
            conn.commit()
            return cur.rowcount

    def latest(self, station_id: str | None = None) -> sqlite3.Row | None:
        query = "SELECT * FROM weather_records"
        params: tuple[str, ...] = ()
        if station_id:
            query += " WHERE station_id = ?"
            params = (station_id,)
        query += " ORDER BY received_at DESC LIMIT 1"

        with self.connect() as conn:
            return conn.execute(query, params).fetchone()

    def history(self, hours: int = 24, station_id: str | None = None) -> list[sqlite3.Row]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = "SELECT * FROM weather_records WHERE received_at >= ?"
        params: list[str] = [cutoff.isoformat()]

        if station_id:
            query += " AND station_id = ?"
            params.append(station_id)

        query += " ORDER BY received_at DESC"

        with self.connect() as conn:
            return conn.execute(query, tuple(params)).fetchall()
