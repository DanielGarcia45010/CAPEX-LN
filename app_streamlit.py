import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape
from collections import defaultdict

from geo_engine_h3 import H3GeoEngine
from capex_scoring import capex_score
from utils_geo import haversine
import h3

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

# ---------------- ENGINE ----------------
engine = H3GeoEngine(resolution=9)
engine.build(geometries)

# ---------------- INPUT ----------------
coords = st.text_input("lat,lon (ej: 4.71,-74.07)")

if coords:

    lat, lon = map(float, coords.split(","))

    candidates = engine.query(lon, lat)

    st.write("Candidates H3:", len(candidates))

    # 🔥 fallback si estás lejos
    if len(candidates) < 5:
        st.warning("Expandiendo búsqueda global...")
        candidates = engine.query(lon, lat, k_ring=5, max_expansion=8)

    best_score = -1
    best_point = None

    density_map = defaultdict(int)

    for h, idx in candidates:
        density_map[h] += 1

    global_density_map = {h: len(idxs) for h, idxs in engine.index.items()}

    # ---------------- SCORE ----------------
    for h, idx in candidates:

        g = geometries[idx]
        c = g.centroid

        # 🔥 distancia real
        d = haversine(lon, lat, c.x, c.y)

        density_local = density_map[h]
        density_global = global_density_map.get(h, 0)

        presence_bonus = 1 if density_local > 3 else 0

        score = capex_score(
            d,
            density_local,
            density_global,
            presence_bonus
        )

        if score > best_score:
            best_score = score
            best_point = (c.x, c.y)

    # ---------------- VISUAL ----------------
    layers = []

    # 🔴 punto usuario
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": [lon, lat]}],
        get_position="position",
        get_radius=120,
        get_fill_color=[255, 0, 0]
    ))

    # 🟢 RED COMPLETA (IMPORTANTE FIX)
    # 👉 LIMITAMOS para evitar overflow visual
    all_points = []

    for h, idxs in list(engine.index.items())[:5000]:  # 🔥 CLAVE: límite de performance

        try:
            lat_h, lon_h = h3.cell_to_latlng(h)

            all_points.append({
                "position": [lon_h, lat_h],
                "count": len(idxs)
            })

        except:
            continue

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=all_points,
        get_position="position",
        get_radius="count * 12",
        get_fill_color=[0, 255, 0, 120],
        pickable=True
    ))

    # 🟢 mejor nodo
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