"""Open-Meteo 实时天气查询。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class WeatherReport:
    city: str
    temperature: float
    apparent_temperature: float
    humidity: int
    weather_code: int
    wind_speed: float

    def to_chinese(self) -> str:
        condition = _WEATHER_CODES.get(self.weather_code, "天气情况未知")
        return (
            f"{self.city}当前天气：{condition}，气温 {self.temperature:g}°C，"
            f"体感 {self.apparent_temperature:g}°C，湿度 {self.humidity}% ，"
            f"风速 {self.wind_speed:g} km/h。"
        )


_WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    95: "雷雨",
    96: "雷雨伴冰雹",
    99: "强雷雨伴冰雹",
}


class OpenMeteoWeatherClient:
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, http_get: Callable[[str, Mapping[str, Any]], dict] | None = None) -> None:
        self._http_get = http_get or self._request_json

    def get_current(self, city: str) -> WeatherReport:
        city = city.strip()
        if not city:
            raise ValueError("城市不能为空")
        location = self._fetch(
            self.GEOCODING_URL,
            {"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        results = location.get("results") or []
        if not results:
            raise RuntimeError(f"未找到城市：{city}")
        place = results[0]
        forecast = self._fetch(
            self.FORECAST_URL,
            {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": ",".join([
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "weather_code",
                    "wind_speed_10m",
                ]),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
            },
        )
        current = forecast.get("current") or {}
        return WeatherReport(
            city=place.get("name", city),
            temperature=float(current["temperature_2m"]),
            apparent_temperature=float(current["apparent_temperature"]),
            humidity=int(current["relative_humidity_2m"]),
            weather_code=int(current["weather_code"]),
            wind_speed=float(current["wind_speed_10m"]),
        )

    def _fetch(self, url: str, params: Mapping[str, Any]) -> dict:
        last_error = None
        for attempt in range(3):
            try:
                return self._http_get(url, params)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.2)
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _request_json(url: str, params: Mapping[str, Any]) -> dict:
        request = Request(f"{url}?{urlencode(params)}", headers={"User-Agent": "wx-bot/1.0"})
        with urlopen(request, timeout=10) as response:
            return json.load(response)
