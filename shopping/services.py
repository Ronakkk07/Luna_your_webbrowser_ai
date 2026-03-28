from urllib.parse import urlencode

import requests
from django.conf import settings


DEFAULT_CITY_INFO_URL = (
    "https://mec2nt9daf.execute-api.us-east-1.amazonaws.com/default/GeoCodingCityInfo"
)


class CityInfoLookupError(Exception):
    pass


def fetch_city_info(city):
    city_name = (city or "").strip()
    if not city_name:
        raise ValueError("City is required.")

    base_url = getattr(settings, "CITY_INFO_API_URL", DEFAULT_CITY_INFO_URL)
    response = requests.get(
        f"{base_url}?{urlencode({'city': city_name})}",
        timeout=10,
    )
    response.raise_for_status()

    try:
        return response.json()
    except ValueError as exc:
        raise CityInfoLookupError("City info service returned invalid JSON.") from exc
