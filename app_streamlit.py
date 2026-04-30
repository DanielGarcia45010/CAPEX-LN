import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape

from geo_engine import GeoEngine

st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE PRO")

# 🔥 cargar índice ya procesado
engine = GeoEngine()

# 🔥 cargar geometrías desde DISCO (NO uploader)
@st.cache_data
def load_geometries():

    path = __import__("pathlib").Path.home() / "Downloads" / "test.json"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [shape(f["geometry"]) for f in data["features"]]

geometries = load_geometries()

st.success(f"{len(geometries)} geometries loaded")

# ---------------- INPUT ----------------
coords = st.text_input("lat,lon")

if coords:

    lat, lon = map(float, coords.split(","))

    results = engine.query(lon, lat)

    st.write("Candidates:", len(results))

    best = None
    best_d = float("inf")
    best_route = None

    for dist, idx in results:

        g = geometries[idx]

        try:
            c = g.centroid

            # sin routing complejo para test base (evita fallos)
            d = ((lon - c.x)**2 + (lat - c.y)**2) ** 0.5 * 111320

            if d < best_d:
                best_d = d
                best = (c.x, c.y)

        except:
            continue

    if best:

        st.success(f"Best distance: {best_d:.0f} m")

        layers = []

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": [lon, lat]}],
            get_position="position",
            get_radius=15,
            get_fill_color=[255, 0, 0]
        ))

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": list(best)}],
            get_position="position",
            get_radius=15,
            get_fill_color=[0, 255, 0]
        ))

        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=lat,
                longitude=lon,
                zoom=12
            )
        ))