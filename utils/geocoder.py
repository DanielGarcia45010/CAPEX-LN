from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import re


geolocator = Nominatim(
    user_agent="capex-ln"
)


# ---------------------------------------------------
# DETECTAR COORDENADAS
# ---------------------------------------------------
def is_coordinates(text):

    pattern = r"^-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?$"

    return re.match(pattern, text.strip()) is not None


# ---------------------------------------------------
# PARSE COORDENADAS
# ---------------------------------------------------
def parse_coordinates(text):

    lat, lon = map(float, text.split(","))

    return lat, lon


# ---------------------------------------------------
# NORMALIZAR DIRECCIONES COLOMBIA
# ---------------------------------------------------
def normalize_address(text):

    text = text.lower().strip()

    # reemplazos comunes
    replacements = {
        "cl ": "calle ",
        "cra ": "carrera ",
        "kr ": "carrera ",
        "av ": "avenida ",
        "#": " # ",
        "-": " - "
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    # detectar formato:
    # calle 163 54c 85
    pattern = r"(calle|carrera|avenida)\s+(\d+\w*)\s+(\d+\w*)\s+(\d+\w*)"

    match = re.search(pattern, text)

    if match:

        tipo = match.group(1)
        n1 = match.group(2)
        n2 = match.group(3)
        n3 = match.group(4)

        formatted = f"{tipo} {n1} #{n2}-{n3}"

        # mantener ciudad si existe
        if "bogota" in text:
            formatted += ", Bogotá, Colombia"

        elif "medellin" in text:
            formatted += ", Medellín, Colombia"

        elif "barranquilla" in text:
            formatted += ", Barranquilla, Colombia"

        else:
            formatted += ", Colombia"

        return formatted

    return text


# ---------------------------------------------------
# GEOCODING
# ---------------------------------------------------
def geocode_location(text):

    try:

        normalized = normalize_address(text)

        location = geolocator.geocode(
            normalized,
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


# ---------------------------------------------------
# INPUT UNIVERSAL
# ---------------------------------------------------
def resolve_input(user_input):

    user_input = user_input.strip()

    # coordenadas
    if is_coordinates(user_input):

        lat, lon = parse_coordinates(user_input)

        return {
            "lat": lat,
            "lon": lon,
            "address": "Coordinates"
        }

    # dirección
    lat, lon, address = geocode_location(user_input)

    if lat is None:

        return None

    return {
        "lat": lat,
        "lon": lon,
        "address": address
    }