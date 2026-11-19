import os
import requests
from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

BASE_URL = "https://api.openweathermap.org/data/2.5"


def get_current_weather(city: str):
    """
    Fetch current weather information for a city.
    """

    if not OPENWEATHER_API_KEY:
        raise ValueError(
            "OPENWEATHER_API_KEY is missing from environment variables."
        )

    response = requests.get(
        f"{BASE_URL}/weather",
        params={
            "q": city,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric"
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    weather = data["weather"][0]

    return {
        "city": data["name"],
        "country": data["sys"]["country"],
        "temperature": data["main"]["temp"],
        "feels_like": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "description": weather["description"],
        "wind_speed": data["wind"]["speed"],
        "min_temperature": data["main"]["temp_min"],
        "max_temperature": data["main"]["temp_max"]
    }


def get_weather_forecast(city: str):
    """
    Fetch 5-day weather forecast for a city.
    OpenWeather provides forecasts in 3-hour intervals.
    """

    if not OPENWEATHER_API_KEY:
        raise ValueError(
            "OPENWEATHER_API_KEY is missing from environment variables."
        )

    response = requests.get(
        f"{BASE_URL}/forecast",
        params={
            "q": city,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric"
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    forecast_list = []

    for item in data["list"]:
        weather = item["weather"][0]

        forecast_list.append({
            "date_time": item["dt_txt"],
            "temperature": item["main"]["temp"],
            "feels_like": item["main"]["feels_like"],
            "humidity": item["main"]["humidity"],
            "description": weather["description"],
            "wind_speed": item["wind"]["speed"]
        })

    return {
        "city": data["city"]["name"],
        "country": data["city"]["country"],
        "forecast": forecast_list
    }