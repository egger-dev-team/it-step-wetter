from datetime import datetime

from pydantic import BaseModel, Field, field_validator


VALID_WIND_DIRECTIONS = {
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
    "UNKNOWN",
}


class WeatherIn(BaseModel):
    station_id: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=128)
    temperatur: float = Field(ge=-80, le=80)
    luftfeuchtigkeit: float = Field(ge=0, le=100)
    luftdruck: float = Field(ge=300, le=1200)
    niederschlag: float = Field(ge=0, le=2000)
    windgeschwindigkeit: float = Field(ge=0, le=200)
    windrichtung: str = Field(min_length=1, max_length=16)
    helligkeit: float = Field(ge=0, le=300000)

    @field_validator("windrichtung")
    @classmethod
    def validate_windrichtung(cls, value: str) -> str:
        direction = value.strip().upper()
        if direction not in VALID_WIND_DIRECTIONS:
            raise ValueError("invalid wind direction")
        return direction


class WeatherOut(BaseModel):
    id: int
    station_id: str
    temperatur: float
    luftfeuchtigkeit: float
    luftdruck: float
    niederschlag: float
    windgeschwindigkeit: float
    windrichtung: str
    helligkeit: float
    received_at: datetime
