# =========================
# 1. IMPORTS
# =========================
import json
import time
import requests
import numpy as np
import pandas as pd
import streamlit as st
import pydeck as pdk

from shapely.geometry import shape, Point
from shapely.ops import nearest_points
from scipy.spatial import cKDTree
from concurrent.futures import ThreadPoolExecutor, as_completed


# =========================
# 2. CONFIG
# =========================
OSRM_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot"
TIMEOUT_FAST = 3
TIMEOUT_FULL = 8
BATCH_SIZE = 5


# =========================
# 3. CORE (SIN STREAMLIT)
# =========================
def build_spatial_index(geometries):
    points, geom_indices = [], []

    for i, geom in enumerate(geometries):
        if geom.geom_type == "Point":
            points.append([geom.x, geom.y])
            geom_indices.append(i)

        elif geom.geom_type in ["LineString", "LinearRing"]:
            coords = list(geom.coords)
            points.extend([[coords[0][0], coords[0][1]], [coords[-1][0], coords[-1][1]]])
            geom_indices.extend([i, i])

        elif geom.geom_type == "Polygon":
            c = geom.centroid
            points.append([c.x, c.y])
            geom_indices.append(i)

        elif geom.geom_type.startswith("Multi") and len(geom.geoms) > 0:
            c = geom.geoms[0].centroid
            points.append([c.x, c.y])
            geom_indices.append(i)

    if not points:
        return None, []

    return cKDTree(np.array(points)), geom_indices


def get_nearest_candidates(tree, geom_indices, client_lon, client_lat, max_results):
    query_point = [client_lon, client_lat]
    k = min(max_results * 2, len(geom_indices))

    distances, indices = tree.query(query_point, k=k)

    seen, results = set(), []

    for dist, idx in zip(distances, indices):
        geom_idx = geom_indices[idx]
        if geom_idx not in seen:
            seen.add(geom_idx)
            dist_m = dist * 111320
            results.append((dist_m, geom_idx))

            if len(results) >= max_results:
                break

    return results


def generate_candidate_points(geom, client_lon, client_lat):
    if geom.geom_type == "Point":
        return [(geom.x, geom.y)]

    elif geom.geom_type in ["LineString", "LinearRing"]:
        coords = list(geom.coords)
        return [coords[0], coords[len(coords)//2], coords[-1]]

    elif geom.geom_type == "Polygon":
        try:
            p = Point(client_lon, client_lat)
            _, closest = nearest_points(p, geom.boundary)
            return [(closest.x, closest.y)]
        except:
            c = geom.centroid
            return [(c.x, c.y)]

    return []

def find_best_route_parallel(
    geometries, client_lon, client_lat, max_candidates,
    progress_callback=None,
    max_workers=10  # 🔥 puedes ajustar esto
):
    tree, geom_indices = build_spatial_index(geometries)
    if tree is None:
        return None

    candidates = get_nearest_candidates(tree, geom_indices, client_lon, client_lat, max_candidates)

    tasks = []
    for _, idx in candidates:
        pts = generate_candidate_points(geometries[idx], client_lon, client_lat)
        for p in pts:
            tasks.append((idx, p[0], p[1]))

    best = {"distance": float("inf"), "point": None, "geom_idx": None, "duration": None}

    total = len(tasks)
    completed = 0

    # 🔥 PARALELIZACIÓN
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(get_route_fast, client_lon, client_lat, lon, lat): (idx, lon, lat)
            for idx, lon, lat in tasks
        }

        for future in as_completed(futures):
            idx, lon, lat = futures[future]

            try:
                d, t = future.result()
                if d and d < best["distance"]:
                    best.update({
                        "distance": d,
                        "point": (lon, lat),
                        "geom_idx": idx,
                        "duration": t
                    })
            except:
                pass

            completed += 1
            if progress_callback:
                progress_callback(completed / total)

    return best


# =========================
# 4. SERVICIOS (API)
# =========================
def get_route_fast(start_lon, start_lat, end_lon, end_lat):
    try:
        r = requests.get(
            f"{OSRM_URL}/{start_lon},{start_lat};{end_lon},{end_lat}",
            params={"overview": "false"},
            timeout=TIMEOUT_FAST
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("routes"):
                route = data["routes"][0]
                return route["distance"], route["duration"]
    except:
        pass
    return None, None


def get_full_route(start_lon, start_lat, end_lon, end_lat):
    try:
        r = requests.get(
            f"{OSRM_URL}/{start_lon},{start_lat};{end_lon},{end_lat}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=TIMEOUT_FULL
        )
        if r.status_code == 200:
            route = r.json()["routes"][0]
            return route["geometry"]["coordinates"]
    except:
        pass
    return None


# =========================
# 5. VISUALIZACIÓN
# =========================
def load_geojson(gj):
    return [shape(f["geometry"]) for f in gj["features"] if f.get("geometry")]


def build_map(layers):
    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=10, longitude=-74, zoom=12),
    )


# =========================
# 6. UI
# =========================
def main():
    st.set_page_config(page_title="CAPEX", layout="wide")
    st.title("CAPEX EVALUATION")

    # Sidebar
    strategy = st.sidebar.selectbox("Estrategia", ["Ultra Rápida", "Híbrida", "Precisa"])
    max_candidates = {"Ultra Rápida":10, "Híbrida":25, "Precisa":50}[strategy]

    # Inputs
    gj_file = st.file_uploader("GeoJSON", type=["geojson"])
    client = st.text_input("Coordenadas (lat,lon)")

    if not gj_file or not client:
        return

    gj = json.loads(gj_file.read())
    geoms = load_geojson(gj)

    lat, lon = map(float, client.split(","))

    if st.button("🚀 Ejecutar"):
        progress = st.progress(0)

        def update(p):
            progress.progress(p)

        result = find_best_route_parallel(geoms, lon, lat, max_candidates, update)

        if not result or not result["point"]:
            st.error("No se encontró ruta")
            return

        route = get_full_route(lon, lat, result["point"][0], result["point"][1])

        st.success(f"Distancia: {result['distance']:.0f} m")

        layers = [
            pdk.Layer("ScatterplotLayer", data=[{"position":[lon,lat]}], get_position="position", get_fill_color=[255,0,0]),
            pdk.Layer("ScatterplotLayer", data=[{"position":list(result["point"])}], get_position="position", get_fill_color=[0,255,0])
        ]

        if route:
            layers.append(pdk.Layer("PathLayer", data=[{"path":route}], get_path="path"))

        st.pydeck_chart(build_map(layers))


# =========================
# 7. ENTRYPOINT
# =========================
if __name__ == "__main__":
    main()
    

# # Info sidebar
# st.sidebar.markdown("---")
# st.sidebar.markdown("""
                    

# ### ⚡ Optimizaciones Implementadas

# **KDTree Espacial:** Búsqueda O(log n) vs O(n)

# **Cache Inteligente:** Índice se construye solo una vez

# **Filtro Agresivo:** Solo evalúa mejores candidatos

# **Timeouts Cortos:** 3s por request vs 5s

# **Procesamiento por Lotes:** Mejor uso de recursos

# ### 🎯 Rendimiento Esperado

# - **Ultra Rápida:** 10-30 segundos
# - **Híbrida:** 30-60 segundos  
# - **Precisa:** 60-120 segundos

# ### 💡 Recomendaciones

# - **<1K geometrías:** Cualquier estrategia
# - **1K-5K geometrías:** Híbrida
# - **>5K geometrías:** Ultra Rápida
# """)