import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape
from collections import defaultdict
import math
import h3

from geo_engine_h3 import H3GeoEngine
from capex_scoring import capex_score


# ---------------- GEO HELP ----------------
def haversine(lon1, lat1, lon2, lat2):

    R = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2 +
        math.cos(phi1) * math.cos(phi2) *
        math.sin(dlambda / 2) ** 2
    )

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------- UI ----------------
st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE H3 PRO")

# ---------------- LOAD ----------------
@st.cache_data
def load_data():
    with open("test.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return [shape(f["geometry"]) for f in data["features"]]

geometries = load_data()

st.success(f"{len(geometries)} geometries loaded")

# 🔥 DEBUG IMPORTANTE (si algo falla aquí, era el problema real)
st.write("DEBUG geometries:", len(geometries))

# ---------------- ENGINE ----------------
engine = H3GeoEngine(resolution=9)
engine.build(geometries)

# ---------------- INPUT ----------------
coords = st.text_input("lat,lon (ej: 4.71,-74.07)")

if coords:

    lat, lon = map(float, coords.split(","))

    candidates = engine.query(lon, lat)

    st.write("Candidates:", len(candidates))

    # 🔥 fallback si estás lejos
    if len(candidates) < 5:
        st.warning("Expandiendo cobertura...")
        candidates = engine.query(lon, lat, k_ring=5, max_expansion=8)

    density_map = defaultdict(int)
    global_density_map = defaultdict(int)

    for h, idxs in engine.index.items():
        global_density_map[h] = len(idxs)

    for h, idx in candidates:
        density_map[h] += 1

    best_score = -1
    best_point = None

    # ---------------- SCORE ----------------
    for h, idx in candidates:

        g = geometries[idx]
        c = g.centroid

        d = haversine(lon, lat, c.x, c.y)

        score = capex_score(
            d,
            density_map[h],
            global_density_map[h],
            1 if density_map[h] > 3 else 0
        )

        if score > best_score:
            best_score = score
            best_point = (c.x, c.y)

    # ---------------- VISUAL ----------------
    layers = []

    # 🔴 USER POINT
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": [lon, lat]}],
        get_position="position",
        get_radius=120,
        get_fill_color=[255, 0, 0]
    ))

    # 🟢 RED COMPLETA (ESTABLE Y VISUAL)
    all_points = []

    # 🔥 usamos geometrías directamente (ESTO EVITA EL ERROR QUE ROMPÍA TODO)
    for i, geom in enumerate(geometries):

        try:
            c = geom.centroid

            all_points.append({
                "position": [c.x, c.y],
                "count": 1
            })

        except:
            continue

        # 🔥 seguridad performance
        if i > 12000:
            break

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=all_points,
        get_position="position",
        get_radius=10,
        get_fill_color=[0, 255, 0, 160],
        pickable=False
    ))

    # 🟢 BEST NODE
    if best_point:

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": list(best_point)}],
            get_position="position",
            get_radius=140,
            get_fill_color=[0, 255, 0]
        ))

        st.success(f"CAPEX SCORE: {best_score:.4f}")

    # ---------------- MAP ----------------
    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=11
        ),
        map_style="mapbox://styles/mapbox/light-v9"
    ))