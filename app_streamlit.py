import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape
from collections import defaultdict
import h3
import math

from geo_engine_h3 import H3GeoEngine
from capex_scoring import capex_score

# ---------------- GEO ----------------
def haversine(lon1, lat1, lon2, lat2):

    R = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
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

# ---------------- ENGINE ----------------
engine = H3GeoEngine(resolution=9)
engine.build(geometries)

# ---------------- INPUT ----------------
coords = st.text_input("lat,lon (ej: 4.71,-74.07)")

if coords:

    lat, lon = map(float, coords.split(","))

    candidates = engine.query(lon, lat)

    st.write("Candidates:", len(candidates))

    if len(candidates) < 5:
        st.warning("Expandiendo cobertura...")
        candidates = engine.query(lon, lat, k_ring=5, max_expansion=8)

    density_map = defaultdict(int)

    for h, idx in candidates:
        density_map[h] += 1

    global_density = {h: len(v) for h, v in engine.index.items()}

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
            global_density.get(h, 0),
            1 if density_map[h] > 3 else 0
        )

        if score > best_score:
            best_score = score
            best_point = (c.x, c.y)

    # ---------------- MAPA BASE (CLAVE) ----------------
    layers = []

    # 🧭 MAPA CIUDAD (OPENSTREETMAP BASE)
    # PyDeck lo maneja automáticamente con map_style

    # 🔴 usuario
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": [lon, lat]}],
        get_position="position",
        get_radius=120,
        get_fill_color=[255, 0, 0],
    ))

    # 🟢 RED H3 (CONTROLADA Y ESTABLE)
    all_points = []

    for i, (h, idxs) in enumerate(engine.index.items()):

        if i > 3000:  # 🔥 importante: evita romper el render
            break

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
        get_radius="count * 10",
        get_fill_color=[0, 255, 0, 140],
        pickable=False
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

    # ---------------- RENDER FINAL ----------------
    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=11
        ),
        map_style="mapbox://styles/mapbox/light-v9"
    ))