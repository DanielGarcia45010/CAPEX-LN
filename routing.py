import requests

BASE_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"

def get_route(start_lon, start_lat, end_lon, end_lat):

    try:
        url = f"{BASE_URL}{start_lon},{start_lat};{end_lon},{end_lat}"
        r = requests.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=4)

        if r.status_code != 200:
            return None, None, None

        data = r.json()
        route = data["routes"][0]

        return (
            route["geometry"]["coordinates"],
            route["distance"],
            route["duration"]
        )

    except:
        return None, None, None