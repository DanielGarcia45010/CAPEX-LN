from geopy.geocoders import Nominatim
from geopy.exc import (
    GeocoderTimedOut,
    GeocoderServiceError
)

import re
import time


# =====================================================
# GEOCODER
# =====================================================

geolocator = Nominatim(
    user_agent="capex-ln-colombia"
)


# =====================================================
# LIMPIEZA GENERAL
# =====================================================

def clean_text(text):

    if text is None:
        return ""

    text = str(text).strip()

    # eliminar espacios repetidos
    text = re.sub(r"\s+", " ", text)

    return text


# =====================================================
# NORMALIZAR ABREVIATURAS
# =====================================================

def normalize_address(text):

    text = clean_text(text)

    replacements = {
        r"\bcl\b": "Calle",
        r"\bcra\b": "Carrera",
        r"\bkr\b": "Carrera",
        r"\bav\b": "Avenida",
        r"\bdg\b": "Diagonal",
        r"\btr\b": "Transversal",
    }

    for pattern, replacement in replacements.items():

        text = re.sub(
            pattern,
            replacement,
            text,
            flags=re.IGNORECASE
        )

    return text


# =====================================================
# DETECTAR COORDENADAS
# =====================================================

def is_coordinates(text):

    pattern = r"""
        ^\s*
        -?\d+(\.\d+)?
        \s*,\s*
        -?\d+(\.\d+)?
        \s*$
    """

    return re.match(
        pattern,
        text,
        re.VERBOSE
    ) is not None


# =====================================================
# VALIDAR COORDENADAS
# =====================================================

def validate_coordinates(lat, lon):

    return (
        -90 <= lat <= 90 and
        -180 <= lon <= 180
    )


# =====================================================
# PARSE COORDENADAS
# =====================================================

def parse_coordinates(text):

    text = text.strip()

    lat, lon = map(
        float,
        text.split(",")
    )

    return lat, lon


# =====================================================
# CIUDADES COLOMBIA
# =====================================================

COLOMBIA_CITIES = {

    "barranquilla": (10.9685, -74.7813),
    "cartagena": (10.3910, -75.4794),
    "bucaramanga": (7.1193, -73.1227),
    "cucuta": (7.8939, -72.5078),
    "bogota": (4.7110, -74.0721),
    "villavicencio": (4.1420, -73.6266),
    "ibague": (4.4389, -75.2322),
    "sincelejo": (9.3047, -75.3978),
    "monteria": (8.7500, -75.8830),
    "medellin": (6.2442, -75.5812),
    "popayan": (2.4448, -76.6147),
    "pasto": (1.2136, -77.2811),
    "ipiales": (0.8250, -77.6397),
    "cali": (3.4516, -76.5320),
    "palmira": (3.5394, -76.3036),
    "santa marta": (11.2408, -74.1990),
    "valledupar": (10.4631, -73.2532)

}


# =====================================================
# HAVERSINE
# =====================================================

def haversine(lat1, lon1, lat2, lon2):

    from math import radians
    from math import sin
    from math import cos
    from math import sqrt
    from math import atan2

    R = 6371

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return R * c


# =====================================================
# REVERSE GEOCODING REAL
# =====================================================

def reverse_geocode(lat, lon):

    nearest_city = None
    min_distance = 999999

    for city, coords in COLOMBIA_CITIES.items():

        city_lat, city_lon = coords

        dist = haversine(
            lat,
            lon,
            city_lat,
            city_lon
        )

        if dist < min_distance:

            min_distance = dist
            nearest_city = city

    return {
        "lat": lat,
        "lon": lon,
        "address": nearest_city,
    }


# =====================================================
# GENERAR VARIANTES
# =====================================================

def generate_queries(text):

    text = normalize_address(text)

    queries = [

        # original
        text,

        # Colombia
        f"{text}, Colombia",

        # búsqueda amplia
        f"{text} Colombia",

        # Valle del Cauca
        f"{text}, Valle del Cauca, Colombia",

        # Antioquia
        f"{text}, Antioquia, Colombia",

        # Bogotá
        f"{text}, Bogotá, Colombia",
    ]

    # quitar vacíos
    queries = [
        q.strip()
        for q in queries
        if q.strip()
    ]

    # remover duplicados
    queries = list(dict.fromkeys(queries))

    return queries


# =====================================================
# GEOCODING ROBUSTO
# =====================================================

def geocode_address(address, retries=3):

    queries = generate_queries(address)

    for query in queries:

        for attempt in range(retries):

            try:

                print(f"Buscando: {query}")

                location = geolocator.geocode(
                    query,
                    exactly_one=True,
                    timeout=15,
                    addressdetails=True,
                    country_codes="co"
                )

                if location:

                    print(
                        f"Encontrado: "
                        f"{location.address}"
                    )

                    return {
                        "lat": location.latitude,
                        "lon": location.longitude,
                        "address": location.address
                    }

                time.sleep(0.5)

            except (
                GeocoderTimedOut,
                GeocoderServiceError
            ):

                time.sleep(1)

            except Exception as e:

                print(
                    "Geocoding error:",
                    e
                )

                time.sleep(1)

    return None


# =====================================================
# RESOLVER INPUT
# =====================================================

def resolve_input(user_input):

    user_input = clean_text(user_input)

    if not user_input:
        return None

    # =================================================
    # COORDENADAS
    # =================================================

    if is_coordinates(user_input):

        lat, lon = parse_coordinates(
            user_input
        )

        if not validate_coordinates(
            lat,
            lon
        ):

            return {
                "error": (
                    "Coordenadas inválidas"
                )
            }

        return reverse_geocode(
            lat,
            lon
        )

    # =================================================
    # DIRECCIÓN / POI / NEGOCIO
    # =================================================

    return geocode_address(
        user_input
    )


# =====================================================
# TESTS
# =====================================================

if __name__ == "__main__":

    tests = [

        "RESTAURANTE SALERMO VIA PALMIRA CALI",

        "Centro Comercial Santafé Medellín",

        "Aeropuerto El Dorado Bogotá",

        "Terminal de Transportes Bucaramanga",

        "Parque Arví Medellín",

        "cl 72 # 10-34 Bogotá",

        "3.4516,-76.5320",

        "3.56229,-76.3891"
    ]

    for test in tests:

        print("\n=================================")
        print("INPUT:", test)

        result = resolve_input(test)

        print(result)