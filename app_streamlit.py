import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape
from collections import defaultdict
from utils_geo import haversine
from geo_engine_h3 import H3GeoEngine
from capex_scoring import capex_score


st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE H3 PRO MAX")


@st.cache_data
def load_data():
    with open("test.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    geometries = []
    centroids = []

    for f in data["features"]:
        try:
            g = shape(f["geometry"])
            c = g.centroid

            geometries.append(g)
            centroids.append((c.x, c.y))

        except:
            continue

    return geometries, centroids


geometries, centroids = load_data()

st.success(f"{len(geometries)} geometries loaded")

engine = H3GeoEngine(resolution=9)
engine.build(geometries)

coords = st.text_input("lat,lon (ej: 4.71,-74.07)")

if coords:

    lat, lon = map(float, coords.split(","))

    candidates = engine.query(lon, lat)

    density_map = defaultdict(int)

    for h, idx in candidates:
        density_map[h] += 1

    best_score = -1
    best_point = None

    # 🔥 OPTIMIZADO: usar centroid cache
    for h, idx in candidates:

        x, y = centroids[idx]

        d = haversine(lon, lat, x, y)

        density = density_map[h]
        presence = 1 if density > 3 else 0

        score = capex_score(d, density, presence)

        if score > best_score:
            best_score = score
            best_point = (x, y)

    layers = []

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": [lon, lat]}],
        get_position="position",
        get_radius=150,
        get_fill_color=[255, 0, 0]
    ))

    if best_point:

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": list(best_point)}],
            get_position="position",
            get_radius=150,
            get_fill_color=[0, 255, 0]
        ))

        st.success(f"CAPEX SCORE: {best_score:.5f}")

    # 🔥 OPTIMIZACIÓN VISUAL (SUBSAMPLING)
    sampled = [
        {"position": [centroids[i][0], centroids[i][1]]}
        for i in range(0, len(centroids), max(1, len(centroids)//5000))
    ]

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=sampled,
        get_position="position",
        get_radius=10,
        get_fill_color=[0, 255, 0, 120]
    ))

    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=11
        ),
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    ))