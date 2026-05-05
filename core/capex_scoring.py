import math

def capex_score(distance_m, density, presence_bonus):
    distance_m = max(distance_m, 1)

    # suavizado más estable
    distance_score = 1 / (1 + math.log1p(distance_m))
    density_score = math.log1p(density)

    return (
        0.55 * distance_score +
        0.30 * density_score +
        0.15 * presence_bonus
    )