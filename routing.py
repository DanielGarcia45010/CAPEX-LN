import requests


BASE_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"


def safe_request(url, params, timeout=4):

    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except:
        return None

    return None


def get_route(start_lon, start_lat, end_lon, end_lat, full=False):

    url = f"{BASE_URL}{start_lon},{start_lat};{end_lon},{end_lat}"

    params = {
        "overview": "full" if full else "false",
        "geometries": "geojson"
    }

    data = safe_request(url, params, timeout=6 if full else 3)

    if not data:
        return None, None, None

    try:
        route = data["routes"][0]

        return (
            route.get("geometry", {}).get("coordinates", None),
            route["distance"],
            route["duration"]
        )
    except:
        return None, None, None