import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape
import pandas as pd

from geo_engine import GeoEngine
from densifier import densify_geometry

st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE PRO + HEATMAP")

engine = GeoEngine()

# ---------------- CONFIG ----------------
st.sidebar.header("⚙️ Configuración")

USE_HEATMAP = st.sidebar.checkbox("Activar Heatmap", value=True)
DENSIFY = st.sidebar.checkbox("Densificar geometrías", value=False)
MAX_POINTS = st.sidebar.slider("Máx puntos heatmap", 1000, 100000, 30000)

# ---------------- LOAD DESDE DISCO ----------------
@st.cache_data
def load_geometries():
    path = "test.json" 

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [shape(f["geometry"]) for f in data["features"]]

geometries = load_geometries()

st.success(f"{len(geometries)} geometries loaded")

if engine.tree is None:
    with st.spinner("Building spatial index..."):
        engine.build(geometries)
    st.success("Index ready")

coords = st.text_input("lat,lon", "10.99384,-74.79639")

if coords:

    lat, lon = map(float, coords.split(","))

    results = engine.query(lon, lat)

    st.write("Candidates:", len(results))

    best = None
    best_d = float("inf")

    for dist, idx in results:

        g = geometries[idx]

        try:
            c = g.centroid

            # 🚀 distancia rápida (sin routing)
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
            get_radius=50,
            get_fill_color=[255, 0, 0],
        ))


        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": list(best)}],
            get_position="position",
            get_radius=50,
            get_fill_color=[0, 255, 0],
        ))

        if USE_HEATMAP:

            st.info("Generating heatmap...")

            points = []

            for g in geometries:

                try:
                    if DENSIFY:
                        for p in densify_geometry(g, step=0.001):
                            points.append(p)
                    else:
                        c = g.centroid
                        points.append((c.x, c.y))

                except:
                    continue

            points = points[:MAX_POINTS]

            df = pd.DataFrame(points, columns=["lon", "lat"])

            heat_layer = pdk.Layer(
                "HeatmapLayer",
                data=df,
                get_position='[lon, lat]',
                aggregation=pdk.types.String("MEAN"),
                get_weight=1,
            )

            layers.append(heat_layer)

        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=lat,
                longitude=lon,
                zoom=12
            )
        ))