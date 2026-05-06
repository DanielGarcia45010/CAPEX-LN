import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
import pydeck as pdk
import requests
from shapely.geometry import shape

from core.geo_engine_h3 import H3GeoEngine

API = "http://localhost:8000/score"

st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE H3")


# ---------------- LOAD GEO ----------------
@st.cache_data
def load_data():
    with open("test.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return [shape(f["geometry"]) for f in data["features"]]


geometries = load_data()

engine = H3GeoEngine(resolution=9)
engine.build(geometries)


# ---------------- INPUT ----------------
coords = st.text_input("lat,lon")

if coords:

    lat, lon = map(float, coords.split(","))

    # ---------------- BACKEND ----------------
    res = requests.post(API, json={
        "lat": lat,
        "lon": lon
    }).json()

    st.success(f"Score: {res['score']}")

    best = res["location"]


    # ---------------- LAYERS ----------------
    layers = []


    # 🔴 USER
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"position": [lon, lat]}],
        get_position="position",
        get_radius=120,
        get_fill_color=[255, 0, 0]
    ))


    # 🟡 BEST
    if best:

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": best}],
            get_position="position",
            get_radius=120,
            get_fill_color=[0, 255, 0]
        ))


    # 🟢 RED EMPRESA (ESTO ES LO QUE PERDISTE)
    red_points = []

    for g in geometries:
        try:
            c = g.centroid
            red_points.append({
                "position": [c.x, c.y]
            })
        except:
            continue

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=red_points,
        get_position="position",
        get_radius = 8,
        get_fill_color=[0, 255, 0, 140],
        pickable=False
    ))


    # ---------------- MAP ----------------
   st.pydeck_chart(pdk.Deck(
    layers=layers,
    initial_view_state=pdk.ViewState(
        latitude=lat,
        longitude=lon,
        zoom=11
    ),
    map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
))