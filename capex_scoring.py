import math

def capex_score(distance_m, density_local, density_global, presence_bonus):

    # Evita explosiones numéricas
    distance_m = max(distance_m, 1)

    # 🔥 distancia con decay realista
    distance_score = math.exp(-distance_m / 5000)

    # 🔥 densidad local (captura clustering inmediato)
    local_score = math.log1p(density_local)

    # 🔥 densidad global (evita sesgo a zonas vacías)
    global_score = math.log1p(density_global)

    # 🔥 bonus estructural
    presence_score = presence_bonus * 0.5

    return (
        0.40 * distance_score +
        0.25 * local_score +
        0.25 * global_score +
        0.10 * presence_score
    )