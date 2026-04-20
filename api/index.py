from datetime import datetime, timedelta, timezone
import os
import time
import xml.etree.ElementTree as ET

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://roadcast-sable.vercel.app", "http://localhost:3000", "https://22082476.github.io", "https://zqqxwcll-3000.euw.devtunnels.ms"],
    allow_methods=["get"],
    allow_headers=["*"],
)

# =====================
# CACHE
# =====================
data_cache = None
last_loaded = 0
CACHE_TTL = 120


@app.get("/docs", response_class=HTMLResponse)
def get_docs():
    """
    Serve an HTML documentation page with Vercel Web Analytics integrated.
    This endpoint provides API documentation and tracks visitor analytics.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RoadCast API Documentation</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                line-height: 1.6;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                border-bottom: 3px solid #0070f3;
                padding-bottom: 10px;
            }
            h2 {
                color: #0070f3;
                margin-top: 30px;
            }
            .endpoint {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
                margin: 15px 0;
                border-left: 4px solid #0070f3;
            }
            code {
                background: #e9ecef;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }
            .method {
                display: inline-block;
                padding: 4px 8px;
                background: #28a745;
                color: white;
                border-radius: 3px;
                font-weight: bold;
                font-size: 0.9em;
            }
            .param {
                margin: 10px 0;
                padding-left: 20px;
            }
            a {
                color: #0070f3;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌤️ RoadCast API Documentation</h1>
            <p>Welcome to the RoadCast Weather API. This API provides weather forecasts and KNMI warnings for the Netherlands.</p>
            
            <h2>Endpoints</h2>
            
            <div class="endpoint">
                <p><span class="method">GET</span> <code>/</code></p>
                <p><strong>Description:</strong> Get weather forecast data for a specific day</p>
                <div class="param">
                    <strong>Query Parameters:</strong>
                    <ul>
                        <li><code>day</code> (optional, default: 0) - Day offset (0 = today, 1 = tomorrow, etc.)</li>
                    </ul>
                </div>
                <p><strong>Example:</strong> <code>/?day=0</code></p>
            </div>

            <div class="endpoint">
                <p><span class="method">GET</span> <code>/docs</code></p>
                <p><strong>Description:</strong> This documentation page</p>
            </div>
            
            <h2>Response Format</h2>
            <p>All responses are returned in JSON format with the following structure:</p>
            <pre><code>{
  "min_temp": 5.2,
  "max_temp": 12.8,
  "rain": 2.5,
  "showers": 0.3,
  "snow": 0.0,
  "sunrise": "2026-04-20T06:30:00",
  "sunset": "2026-04-20T20:45:00",
  "min_visibility": 8000,
  "max_visibility": 24000,
  "wind_speed": 25.5,
  "wind_gusts": 40.2,
  "warnings": []
}</code></pre>
            
            <h2>Data Sources</h2>
            <ul>
                <li><strong>Weather Data:</strong> <a href="https://open-meteo.com" target="_blank">Open-Meteo API</a> (KNMI Seamless model)</li>
                <li><strong>Weather Warnings:</strong> <a href="https://www.knmi.nl" target="_blank">KNMI Netherlands</a></li>
            </ul>
            
            <h2>CORS Policy</h2>
            <p>This API allows requests from the following origins:</p>
            <ul>
                <li>https://roadcast-sable.vercel.app</li>
                <li>https://22082476.github.io</li>
                <li>http://localhost:3000 (for development)</li>
            </ul>
            
            <h2>Rate Limiting & Caching</h2>
            <p>Weather data is cached for 120 seconds to reduce load on upstream APIs and improve response times.</p>
        </div>
        
        <!-- Vercel Web Analytics -->
        <script>
            window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
        </script>
        <script defer src="/_vercel/insights/script.js"></script>
    </body>
    </html>
    """
    return html_content


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
