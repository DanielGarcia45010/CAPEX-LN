from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import re

geolocator = Nominatim(
    user_agent="capex-ln"
)


# ---------------- DETECTAR COORDENADAS ----------------
def is_coordinates(text):

    pattern = r"^-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?$"

    return re.match(pattern, text.strip()) is not None


# ---------------- PARSE COORDENADAS ----------------
def parse_coordinates(text):

    lat, lon = map(float, text.split(","))

    return lat, lon


# ---------------- GEOCODING FLEXIBLE ----------------
def geocode_location(text):

    try:

        location = geolocator.geocode(
            text,
            timeout=10,
            country_codes="co"
        )

        if location:

            return (
                location.latitude,
                location.longitude,
                location.address
            )

        return None, None, None

    except GeocoderTimedOut:

        return None, None, None


# ---------------- INPUT UNIVERSAL ----------------
def resolve_input(user_input):

    user_input = user_input.strip()

    # caso coordenadas
    if is_coordinates(user_input):

        lat, lon = parse_coordinates(user_input)

        return {
            "lat": lat,
            "lon": lon,
            "address": "Coordinates"
        }

    # caso dirección
    lat, lon, address = geocode_location(user_input)

    if lat is None:

        return None

    return {
        "lat": lat,
        "lon": lon,
        "address": address
    }