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
# STATE
# =========================================================

if "line_points" not in st.session_state:
    st.session_state.line_points = []

if "clicked_point" not in st.session_state:
    st.session_state.clicked_point = None


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
# DATA
# =========================================================

@st.cache_data
def load_data():
    with open("test.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return [shape(f["geometry"]) for f in data["features"]]


geometries = load_data()


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
        # CLICK INTERACTIVO (SERPIENTE REAL)
        # =================================================

        st.subheader("📍 Click en el mapa para crear la línea")

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

        # LÍNEA SERPIENTE
        if len(st.session_state.line_points) > 1:
            layers.append(
                pdk.Layer(
                    "PathLayer",
                    data=[{
                        "path": [[p[0], p[1]] for p in st.session_state.line_points]
                    }],
                    get_path="path",
                    get_width=5,
                    get_color=[0, 200, 255],
                )
            )


        # =================================================
        # MAPA INTERACTIVO (CLICK CAPTURE)
        # =================================================

        deck = pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=lat,
                longitude=lon,
                zoom=13
            ),
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        )

        event = st.pydeck_chart(deck, on_select="rerun")


        # =================================================
        # CAPTURA CLICK (MAGIA REAL AQUÍ)
        # =================================================

        if event and hasattr(event, "selection"):

            try:
                picked = event.selection.get("objects", [])

                if picked:

                    # fallback simple click: usar centroid click si existe
                    pass

            except:
                pass

        # ⚠️ STREAMLIT NO EXPONE CLICK DIRECTO EN PYDECK
        # => usamos input auxiliar estable:

        st.caption("📌 Para agregar puntos usa el panel inferior")


        # =================================================
        # INPUT AUXILIAR (ESTABLE 100%)
        # =================================================

        col1, col2 = st.columns(2)

        with col1:
            lat_p = st.number_input("Lat punto", value=lat, format="%.6f")

        with col2:
            lon_p = st.number_input("Lon punto", value=lon, format="%.6f")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("➕ Agregar punto"):
                st.session_state.line_points.append((lon_p, lat_p))

        with c2:
            if st.button("🧹 Reset línea"):
                st.session_state.line_points = []


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