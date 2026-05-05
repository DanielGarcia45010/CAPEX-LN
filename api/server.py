from fastapi import FastAPI
from pydantic import BaseModel

from core.geo_engine_h3 import H3GeoEngine
from core.capex_scoring import capex_score
from core.utils_geo import haversine

app = FastAPI()

engine = H3GeoEngine(resolution=9)


class Query(BaseModel):
    lat: float
    lon: float


@app.get("/")
def home():
    return {"status": "running"}


@app.post("/score")
def score(query: Query):

    candidates = engine.query(query.lon, query.lat)

    if not candidates:
        return {"score": 0, "location": None}

    density_map = {}

    for h, idx in candidates:
        density_map[h] = density_map.get(h, 0) + 1

    best_score = -1
    best_point = None

    for h, idx in candidates:

        x, y = engine.centroids[idx]

        d = haversine(query.lon, query.lat, x, y)

        density = density_map[h]
        presence = 1 if density > 3 else 0

        score = capex_score(d, density, presence)

        if score > best_score:
            best_score = score
            best_point = [x, y]

    return {
        "score": float(best_score),
        "location": best_point
    }