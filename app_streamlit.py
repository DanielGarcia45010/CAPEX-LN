import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape
from collections import defaultdict

from geo_engine_h3 import H3GeoEngine
from capex_scoring import capex_score

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

    best_score = -1
    best_point = None

    # densidad por celda
    density_map = defaultdict(int)

    for h, idx in candidates:
        density_map[h] += 1

    for h, idx in candidates:

        g = geometries[idx]
        c = g.centroid

        # distancia simple
        d = ((lon - c.x)**2 + (lat - c.y)**2) ** 0.5 * 111320

        density = density_map[h]

        presence_bonus = 1 if density > 3 else 0

        score = capex_score(d, density, presence_bonus)

        if score > best_score:
            best_score = score
            best_point = (c.x, c.y)

    # ---------------- VISUAL ----------------
    layers = []

    # cliente
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": [lon, lat]}],
        get_position="position",
        get_radius=120,
        get_fill_color=[255, 0, 0]
    ))

    # mejor nodo red (VERDE)
    if best_point:

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": list(best_point)}],
            get_position="position",
            get_radius=120,
            get_fill_color=[0, 255, 0]
        ))

        st.success(f"CAPEX SCORE: {best_score:.4f}")

    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=11
        )
    ))