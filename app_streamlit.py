import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape
from collections import defaultdict
import math

from geo_engine_h3 import H3GeoEngine
from capex_scoring import capex_score


# ---------------- DISTANCIA REAL ----------------
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


# ---------------- APP ----------------
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

    # fallback si estás lejos
    if len(candidates) < 5:
        candidates = engine.query(lon, lat, k_ring=4)

    best_score = -1
    best_point = None

    density_map = defaultdict(int)

    for h, idx in candidates:
        density_map[h] += 1

    # ---------------- SCORE ----------------
    for h, idx in candidates:

        g = geometries[idx]
        c = g.centroid

        d = haversine(lon, lat, c.x, c.y)

        density = density_map[h]

        presence_bonus = 1 if density > 3 else 0

        score = capex_score(
            d,
            density,
            presence_bonus
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

    # 🟢 BEST NODE
    if best_point:

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": list(best_point)}],
            get_position="position",
            get_radius=120,
            get_fill_color=[0, 255, 0]
        ))

        st.success(f"CAPEX SCORE: {best_score:.4f}")

    # 🟢 RED COMPLETA (ESTABLE Y VISUAL)
    red_points = []

    for i, geom in enumerate(geometries):

        try:
            c = geom.centroid

            red_points.append({
                "position": [c.x, c.y]
            })

        except:
            continue

        # control performance
        if i > 8000:
            break

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=red_points,
        get_position="position",
        get_radius=8,
        get_fill_color=[0, 255, 0, 140],
        pickable=False
    ))

    # ---------------- MAPA BASE (CLAVE) ----------------
    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=11
        ),

        # 🔥 ESTO RESTAURA LA CIUDAD (NO MAPBOX TOKEN REQUIRED)
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    ))