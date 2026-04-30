import json
import streamlit as st
import pandas as pd
import pydeck as pdk
from shapely.geometry import shape
from densifier import densify_geometry

st.set_page_config(page_title="GeoJSON Pro H3 Ready", layout="wide")
st.title("🚀 GeoJSON Viewer Optimized")

SPACING = 0.001
MAX_RENDER = 50000

file = st.file_uploader("GeoJSON")

if file:

    data = json.loads(file.read())

    points = []
    features = data["features"]

    for f in features:

        try:
            geom = shape(f["geometry"])
            for p in densify_geometry(geom, SPACING):
                points.append(p)

        except:
            continue

    st.success(f"Points: {len(points):,}")

    df = pd.DataFrame(points, columns=["lon", "lat"])
    df = df.head(MAX_RENDER)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_radius=12
    )

    st.pydeck_chart(pdk.Deck(layers=[layer]))