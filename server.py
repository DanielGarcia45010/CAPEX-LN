from fastapi import FastAPI
from pydantic import BaseModel
import json

from core.engine import GeoEngine
from core.scoring import capex_score
from core.geo import haversine
from core.cache import get_cache, set_cache


app = FastAPI(title="CAPEX Cloud Engine")

engine = GeoEngine(resolution=9)


class Query(BaseModel):
    lat: float
    lon: float


@app.on_event("startup")
def load():
    # aquí podrías cargar desde S3 / DB
    pass


@app.post("/score")
def score(query: Query):

    cache_key = f"{query.lat}_{query.lon}"
    cached = get_cache(cache_key)

    if cached:
        return cached

    candidates = engine.query(query.lon, query.lat)

    best_score = -1
    best = None

    density_map = {}

    for h, idx in candidates:
        density_map[h] = density_map.get(h, 0) + 1

    for h, idx in candidates:

        x, y = engine.centroids[idx]

        d = haversine(query.lon, query.lat, x, y)

        score = capex_score(
            d,
            density_map[h],
            1 if density_map[h] > 3 else 0
        )

        if score > best_score:
            best_score = score
            best = (x, y)

    result = {
        "score": best_score,
        "location": best
    }

    set_cache(cache_key, result)

    return result