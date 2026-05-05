import math
from functools import lru_cache

R = 6371000


@lru_cache(maxsize=100000)
def haversine(lon1, lat1, lon2, lat2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2 +
        math.cos(phi1) * math.cos(phi2) *
        math.sin(dlambda / 2) ** 2
    )

    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))