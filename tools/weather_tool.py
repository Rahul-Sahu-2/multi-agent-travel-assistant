"""
Weather tool using Open-Meteo (free, no API key needed).

Keeps the same return shapes as the old OpenWeather version, so the
weather agent and _format_weather() work without changes.
"""

import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15

# WMO weather codes used by Open-Meteo -> short English description
WMO_DESCRIPTIONS = {
    0: "clear sky",
    1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def _describe(code) -> str:
    try:
        return WMO_DESCRIPTIONS.get(int(code), "unknown")
    except (TypeError, ValueError):
        return "unknown"


def _geocode(city: str) -> dict:
    """Find latitude/longitude and the official place name for a city."""
    response = requests.get(
        GEOCODE_URL,
        params={"name": city, "count": 1, "language": "en", "format": "json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    results = response.json().get("results") or []

    if not results:
        raise ValueError(f"Place not found for weather lookup: {city}")

    place = results[0]
    return {
        "name": place.get("name", city),
        "country_code": place.get("country_code", ""),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
    }


def _fetch_forecast_json(place: dict, days: int = 5) -> dict:
    response = requests.get(
        FORECAST_URL,
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                       "weather_code,wind_speed_10m",
            "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                      "weather_code,wind_speed_10m",
            "forecast_days": days,
            "wind_speed_unit": "ms",   # match the old m/s output
            "timezone": "auto",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_current_weather(city: str):
    """Current weather for a city (same keys as the old OpenWeather version)."""

    place = _geocode(city)
    data = _fetch_forecast_json(place, days=1)
    current = data.get("current") or {}

    temperature = current.get("temperature_2m")

    return {
        "city": place["name"],
        "country": place["country_code"],
        "temperature": temperature,
        "feels_like": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "description": _describe(current.get("weather_code")),
        "wind_speed": current.get("wind_speed_10m"),
        "min_temperature": temperature,
        "max_temperature": temperature,
    }


def get_weather_forecast(city: str):
    """Hourly forecast for about 5 days (same keys as the old version)."""

    place = _geocode(city)
    data = _fetch_forecast_json(place, days=5)
    hourly = data.get("hourly") or {}

    times = hourly.get("time", [])
    forecast_list = []

    for i, timestamp in enumerate(times):
        forecast_list.append({
            "date_time": timestamp.replace("T", " "),  # "2026-11-22 12:00"
            "temperature": hourly["temperature_2m"][i],
            "feels_like": hourly["apparent_temperature"][i],
            "humidity": hourly["relative_humidity_2m"][i],
            "description": _describe(hourly["weather_code"][i]),
            "wind_speed": hourly["wind_speed_10m"][i],
        })

    return {
        "city": place["name"],
        "country": place["country_code"],
        "forecast": forecast_list,
    }
