# frontend/app_streamlit.py

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

import streamlit as st
import json
import pydeck as pdk
import math
import requests

from shapely.geometry import shape
from collections import defaultdict

from core.geo_engine_h3 import H3GeoEngine
from core.capex_scoring import capex_score
from utils.geocoder import resolve_input


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(page_title="CAPEX ENGINE", layout="wide")
st.title("🚀 CAPEX ENGINE")


# =========================================================
# STATE PARA LÍNEA
# =========================================================

if "line_points" not in st.session_state:
    st.session_state.line_points = []


# =========================================================
# HELPERS
# =========================================================

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


# =========================================================
# LOAD DATA
# =========================================================

@st.cache_data
def load_data():

    with open("test.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    return [shape(f["geometry"]) for f in data["features"]]


geometries = load_data()


# =========================================================
# ENGINE
# =========================================================

@st.cache_resource
def build_engine():

    engine = H3GeoEngine(resolution=9)
    engine.build(geometries)
    return engine


engine = build_engine()


# =========================================================
# SIDEBAR
# =========================================================

section = st.sidebar.radio("Menú", ["Cotización", "Factibilidad"])


# =========================================================
# COTIZACIÓN
# =========================================================

if section == "Cotización":

    st.header("📍 Cotización")

    location_input = st.text_input(
        "📍 Dirección o coordenadas",
        placeholder="Ej: Chapinero Bogotá o 4.7110,-74.0721"
    )

    mrc_cliente = st.number_input(
        "💰 Valor mensual (COP)",
        value=3000000,
        step=100000
    )

    # =====================================================
    # CONTROL DE PUNTOS (LÍNEA)
    # =====================================================

    st.subheader("📏 Dibujo de línea")

    col1, col2 = st.columns(2)

    with col1:
        lat_p = st.number_input("Lat punto", value=4.7110, format="%.6f")

    with col2:
        lon_p = st.number_input("Lon punto", value=-74.0721, format="%.6f")

    c1, c2 = st.columns(2)

    with c1:
        if st.button("➕ Agregar punto"):
            st.session_state.line_points.append((lon_p, lat_p))

    with c2:
        if st.button("🧹 Reset"):
            st.session_state.line_points = []


    # =====================================================
    # ANALIZAR
    # =====================================================

    if st.button("Analizar cotización"):

        result = resolve_input(location_input)

        if result is None:
            st.error("No se pudo encontrar ubicación")
            st.stop()

        lat = result["lat"]
        lon = result["lon"]

        st.success(result["address"])

        # =================================================
        # CAPEX ENGINE
        # =================================================

        candidates = engine.query(lon, lat)

        best_score = -1
        best_point = None

        density_map = defaultdict(int)

        for h, idx in candidates:
            density_map[h] += 1

        for h, idx in candidates:

            g = geometries[idx]
            c = g.centroid

            d = haversine(lon, lat, c.x, c.y)

            density = density_map[h]
            presence_bonus = 1 if density > 3 else 0

            score = capex_score(d, density, presence_bonus)

            if score > best_score:
                best_score = score
                best_point = (c.x, c.y)


        st.metric("CAPEX SCORE", f"{best_score:.4f}")


        # =================================================
        # MAPA PYDECK
        # =================================================

        layers = []

        # CLIENTE
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=[{"position": [lon, lat]}],
                get_position="position",
                get_radius=10,
                get_fill_color=[255, 0, 0],
            )
        )

        layers.append(
            pdk.Layer(
                "TextLayer",
                data=[{"position": [lon, lat], "text": "CLIENTE"}],
                get_position="position",
                get_text="text",
                get_size=16,
                get_color=[255, 0, 0],
            )
        )

        # BEST POINT
        if best_point:

            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"position": list(best_point)}],
                    get_position="position",
                    get_radius=10,
                    get_fill_color=[0, 255, 0],
                )
            )

        # NETWORK
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=[{"position": [g.centroid.x, g.centroid.y]} for g in geometries],
                get_position="position",
                get_radius=8,
                get_fill_color=[0, 255, 0, 120],
            )
        )


        # =================================================
        # LÍNEA DIBUJADA (SIN FOLIUM)
        # =================================================

        if len(st.session_state.line_points) > 1:

            layers.append(
                pdk.Layer(
                    "PathLayer",
                    data=[{
                        "path": [[lon, lat] for lon, lat in st.session_state.line_points]
                    }],
                    get_path="path",
                    get_width=5,
                    get_color=[0, 200, 255],
                )
            )


        # =================================================
        # DISTANCIA
        # =================================================

        total_distance = 0

        if len(st.session_state.line_points) > 1:

            for i in range(len(st.session_state.line_points) - 1):

                lon1, lat1 = st.session_state.line_points[i]
                lon2, lat2 = st.session_state.line_points[i + 1]

                total_distance += haversine(lon1, lat1, lon2, lat2)

            st.success(f"📏 Distancia total: {total_distance:,.2f} metros")


        # =================================================
        # MAPA FINAL
        # =================================================

        center_lat = lat
        center_lon = lon

        st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(
                    latitude=center_lat,
                    longitude=center_lon,
                    zoom=13
                ),
                map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
            )
        )


# =========================================================
# FACTIBILIDAD
# =========================================================

else:

    st.header("💰 Factibilidad")

    costo = st.number_input("Costo obra", value=100000000)
    mrc = st.number_input("MRC", value=3000000)
    term = st.number_input("Term", value=24)

    if st.button("Generar"):

        res = requests.post(
            "http://localhost:8000/feasibility",
            json={
                "costoObraCivil": int(costo),
                "mrc": int(mrc),
                "term": int(term)
            }
        )

        st.write(res.json())