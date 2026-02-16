from datetime import datetime, timedelta, timezone
import os
import time
import xml.etree.ElementTree as ET

import requests
from fastapi import FastAPI, HTTPException, Query

app = FastAPI()

# =====================
# CACHE
# =====================
data_cache = None
last_loaded = 0
CACHE_TTL = 120


@app.get("/")
def get_weather(day: int = Query(default=0, ge=0)):
    global data_cache, last_loaded

    current_time = time.time()
    cache_age = current_time - last_loaded

    # =====================
    # FETCH WEATHER (Open-Meteo)
    # =====================
    if data_cache is None or cache_age > CACHE_TTL:
        try:
            response = requests.get(
                "https://api.open-meteo.com/v1/forecast"
                "?latitude=52.0167"
                "&longitude=4.7083"
                "&daily=sunrise,sunset,rain_sum,showers_sum,snowfall_sum,"
                "temperature_2m_min,temperature_2m_max,"
                "visibility_min,visibility_max,"
                "wind_speed_10m_max,wind_gusts_10m_max"
                "&timezone=auto"
                "&models=knmi_seamless",
                timeout=10,
            )
            response.raise_for_status()
            data_cache = response.json()
            last_loaded = current_time
        except Exception:
            if data_cache is None:
                raise HTTPException(status_code=500, detail="Weather fetch failed")

    # =====================
    # FETCH KNMI WARNINGS
    # =====================
    warnings = []
    api_key = os.getenv("KNMI_API_KEY", "")
    if api_key:
        try:
            knmi_xml = fetch_knmi_warnings(api_key)
            warnings = parse_knmi_warnings(knmi_xml)
        except Exception:
            warnings = []

    # =====================
    # BUILD RESPONSE
    # =====================
    try:
        body = weather_response_mapper(data_cache, day, warnings).to_dict()
        return body
    except IndexError:
        raise HTTPException(status_code=400, detail="Day index out of range")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =====================
# KNMI HELPERS
# =====================
def fetch_knmi_warnings(api_key):
    url = (
        "https://api.dataplatform.knmi.nl/open-data/v1/"
        "datasets/waarschuwingen_nederland_48h/"
        "versions/1.0/files"
    )

    headers = {"Authorization": api_key}

    files = requests.get(url, headers=headers, timeout=10).json()["files"]
    latest = sorted(files, key=lambda f: f["created"], reverse=True)[0]

    xml = requests.get(
        latest["downloadUrl"],
        headers=headers,
        timeout=10,
    ).text

    return xml


def parse_knmi_warnings(xml_text):
    now = datetime.now(timezone.utc)
    end_of_tomorrow = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59)

    root = ET.fromstring(xml_text)
    results = []

    for warning in root.findall(".//warning"):
        start = datetime.fromisoformat(warning.findtext("startTime"))
        end = datetime.fromisoformat(warning.findtext("endTime"))

        if start <= end_of_tomorrow and end >= now:
            results.append(
                {
                    "color": warning.findtext("awarenessLevel"),
                    "type": warning.findtext("phenomenon"),
                }
            )

    return results


# =====================
# WEATHER MAPPING
# =====================
def weather_response_mapper(response, day_index=0, warnings=None):
    api = RoadCastApiResponse.from_api(response, day_index)
    api.warnings = warnings or []
    return api


class RoadCastApiResponse:
    def __init__(
        self,
        min_temp=None,
        max_temp=None,
        rain=None,
        showers=None,
        snow=None,
        sunrise=None,
        sunset=None,
        min_visibility=None,
        max_visibility=None,
        wind_speed=None,
        wind_gusts=None,
        warnings=None,
    ):
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.rain = rain
        self.showers = showers
        self.snow = snow
        self.sunrise = sunrise
        self.sunset = sunset
        self.min_visibility = min_visibility
        self.max_visibility = max_visibility
        self.wind_speed = wind_speed
        self.wind_gusts = wind_gusts
        self.warnings = warnings or []

    @staticmethod
    def from_api(response, index=0):
        daily = response["daily"]

        def get_val(key):
            values = daily.get(key, [])
            return values[index] if index < len(values) else None

        return RoadCastApiResponse(
            min_temp=get_val("temperature_2m_min"),
            max_temp=get_val("temperature_2m_max"),
            rain=get_val("rain_sum"),
            showers=get_val("showers_sum"),
            snow=get_val("snowfall_sum"),
            sunrise=get_val("sunrise"),
            sunset=get_val("sunset"),
            min_visibility=get_val("visibility_min"),
            max_visibility=get_val("visibility_max"),
            wind_speed=get_val("wind_speed_10m_max"),
            wind_gusts=get_val("wind_gusts_10m_max"),
        )

    def to_dict(self):
        return {
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "rain": self.rain,
            "showers": self.showers,
            "snow": self.snow,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "min_visibility": self.min_visibility,
            "max_visibility": self.max_visibility,
            "wind_speed": self.wind_speed,
            "wind_gusts": self.wind_gusts,
            "warnings": self.warnings,
        }
