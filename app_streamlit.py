import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape

from geo_engine_h3 import GeoEngineH3
from routing import get_route

st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE PRO (TEST MODE)")

engine = GeoEngineH3(resolution=8)
geometries = []

# ---------------- DATA SOURCE ----------------
st.sidebar.title("Data Source")

mode = st.sidebar.radio(
    "Choose data source",
    ["Local file (recommended)", "Upload file"]
)

data = None

# -------- LOCAL FILE (RECOMENDADO) --------
if mode == "Local file (recommended)":

    path = st.text_input("Path to GeoJSON", "data/sample.geojson")

    if st.button("Load local file"):

        try:
            with open(path) as f:
                data = json.load(f)

            geometries = [shape(f["geometry"]) for f in data["features"]]

            st.success(f"{len(geometries)} geometries loaded (LOCAL)")

        except Exception as e:
            st.error(f"Error: {e}")

# -------- UPLOAD (solo para archivos pequeños) --------
else:

    file = st.file_uploader("Upload GeoJSON")

    if file:
        data = json.loads(file.read())
        geometries = [shape(f["geometry"]) for f in data["features"]]

        st.success(f"{len(geometries)} geometries loaded (UPLOAD)")

# ---------------- BUILD INDEX ----------------
if geometries:

    if st.button("Build H3 Index"):

        with st.spinner("Building index..."):
            engine.build(geometries)

        st.success("Index ready 🚀")

# ---------------- QUERY ----------------
coords = st.text_input("lat,lon", "10.99384,-74.79639")

if coords and engine.index:

    lat, lon = map(float, coords.split(","))

    results = engine.query(lon, lat)

    st.write("Candidates:", len(results))

    best = None
    best_d = float("inf")
    best_route = None

    for idx in results:

        g = geometries[idx]

        try:
            c = g.centroid
            route, d, _ = get_route(lon, lat, c.x, c.y)

            if d and d < best_d:
                best_d = d
                best = (c.x, c.y)
                best_route = route

        except:
            continue

    if best:

        st.success(f"Best distance: {best_d:.0f} m")

        layers = []

        # Cliente
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": [lon, lat]}],
            get_position="position",
            get_radius=15,
            get_fill_color=[255, 0, 0]
        ))

        # Punto más cercano
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": list(best)}],
            get_position="position",
            get_radius=15,
            get_fill_color=[0, 255, 0]
        ))

        # Ruta
        if best_route:
            layers.append(pdk.Layer(
                "PathLayer",
                data=[{"path": best_route}],
                get_path="path",
                width_scale=5
            ))

        st.pydeck_chart(pdk.Deck(layers=layers))