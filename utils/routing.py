import requests

BASE_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"

def get_route(start_lon, start_lat, end_lon, end_lat, full=False):

    url = f"{BASE_URL}{start_lon},{start_lat};{end_lon},{end_lat}"

    params = {
        "overview": "full" if full else "false",
        "geometries": "geojson"
    }

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        route = data["routes"][0]

        return (
            route["geometry"]["coordinates"],
            route["distance"],
            route["duration"]
        )

    except:
        return None, None, None