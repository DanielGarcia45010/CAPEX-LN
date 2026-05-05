import math

def capex_score(distance_m, density, presence_bonus):

    distance_m = max(distance_m, 1)

    distance_score = 1 / (1 + distance_m)
    density_score = math.log(1 + density)

    return (
        0.5 * distance_score +
        0.3 * density_score +
        0.2 * presence_bonus
    )