import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape

from geo_engine import GeoEngine
from routing import get_route

st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE PRO")

engine = GeoEngine()

# ---------------- LOAD ----------------
file = st.file_uploader("GeoJSON")

if file:

    data = json.loads(file.read())

    geometries = [shape(f["geometry"]) for f in data["features"]]

    st.success(f"{len(geometries)} geometries loaded")

    if st.button("Build Spatial Index"):

        with st.spinner("Building index..."):
            engine.build(geometries)

        st.success("Index ready")


# ---------------- CLIENT ----------------
coords = st.text_input("lat,lon")

if coords and engine.tree:

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

        if best_route:

            layers.append(pdk.Layer(
                "PathLayer",
                data=[{"path": best_route}],
                get_path="path",
                width_scale=5
            ))

        st.pydeck_chart(pdk.Deck(layers=layers))