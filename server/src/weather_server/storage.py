from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from .models import WeatherIn


@dataclass
class Storage:
    database_url: str
    retention_days: int

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_records (
                    id BIGSERIAL PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    temperatur DOUBLE PRECISION NOT NULL,
                    luftfeuchtigkeit DOUBLE PRECISION NOT NULL,
                    luftdruck DOUBLE PRECISION NOT NULL,
                    niederschlag DOUBLE PRECISION NOT NULL,
                    windgeschwindigkeit DOUBLE PRECISION NOT NULL,
                    windrichtung TEXT NOT NULL,
                    helligkeit DOUBLE PRECISION NOT NULL,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_received_at
                ON weather_records(received_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_station_received
                ON weather_records(station_id, received_at DESC)
                """
            )
            conn.commit()

    def insert(self, payload: WeatherIn) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO weather_records (
                    station_id, temperatur, luftfeuchtigkeit, luftdruck,
                    niederschlag, windgeschwindigkeit, windrichtung,
                    helligkeit
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
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
                ),
            ).fetchone()
            conn.commit()
            if row is None:
                raise RuntimeError("insert failed")
            return int(row["id"])

    def cleanup_old(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                DELETE FROM weather_records
                WHERE received_at < NOW() - (%s * INTERVAL '1 day')
                """,
                (self.retention_days,),
            )
            conn.commit()
            return row.rowcount

    def latest(self, station_id: str | None = None):
        query = "SELECT * FROM weather_records"
        params: tuple[str, ...] = ()
        if station_id:
            query += " WHERE station_id = %s"
            params = (station_id,)
        query += " ORDER BY received_at DESC LIMIT 1"

        with self.connect() as conn:
            return conn.execute(query, params).fetchone()

    def history(self, hours: int = 24, station_id: str | None = None):
        query = """
            SELECT * FROM weather_records
            WHERE received_at >= NOW() - (%s * INTERVAL '1 hour')
        """
        params: list[object] = [hours]

        if station_id:
            query += " AND station_id = %s"
            params.append(station_id)

        query += " ORDER BY received_at DESC"

        with self.connect() as conn:
            return conn.execute(query, tuple(params)).fetchall()

    def stations(self):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT station_id, MAX(received_at) AS last_seen,
                       COUNT(*) AS sample_count
                FROM weather_records
                GROUP BY station_id
                ORDER BY last_seen DESC
                """
            ).fetchall()
