# frontend/app_streamlit.py

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

import streamlit as st
import json
import math
import requests
import folium

from shapely.geometry import shape
from collections import defaultdict
from streamlit_folium import st_folium

from core.geo_engine_h3 import H3GeoEngine
from core.capex_scoring import capex_score
from utils.geocoder import resolve_input


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(page_title="CAPEX ENGINE", layout="wide")
st.title("🚀 CAPEX ENGINE")


# =========================================================
# STATE (ESTABLE REAL)
# =========================================================

if "analysis" not in st.session_state:
    st.session_state.analysis = None

if "line_points" not in st.session_state:
    st.session_state.line_points = []

if "last_click" not in st.session_state:
    st.session_state.last_click = None


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

    location_input = st.text_input("📍 Dirección o coordenadas")
    mrc_cliente = st.number_input("💰 MRC", value=3000000)


    # =====================================================
    # ANÁLISIS
    # =====================================================

    if st.button("Analizar cotización"):

        result = resolve_input(location_input)

        if result is None:
            st.error("No se pudo encontrar ubicación")
            st.stop()

        lat = result["lat"]
        lon = result["lon"]

        st.success(result["address"])

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

        st.session_state.analysis = {
            "lat": lat,
            "lon": lon,
            "best_point": best_point,
            "score": best_score
        }


    # =====================================================
    # RENDER (MAPA ÚNICO ESTABLE)
    # =====================================================

    if st.session_state.analysis:

        data = st.session_state.analysis
        lat = data["lat"]
        lon = data["lon"]
        best_point = data["best_point"]

        st.metric("CAPEX SCORE", f"{data['score']:.4f}")

        # =========================
        # MAPA BASE
        # =========================
        m = folium.Map(
            location=[lat, lon],
            zoom_start=13,
            tiles="CartoDB dark_matter"
        )

        folium.Marker(
            [lat, lon],
            tooltip="CLIENTE",
            icon=folium.Icon(color="red")
        ).add_to(m)

        if best_point:
            folium.Marker(
                [best_point[1], best_point[0]],
                tooltip="ÓPTIMO",
                icon=folium.Icon(color="green")
            ).add_to(m)

        # =========================
        # LÍNEA CONTINUA
        # =========================
        if len(st.session_state.line_points) > 1:
            folium.PolyLine(
                [(p[1], p[0]) for p in st.session_state.line_points],
                color="cyan",
                weight=5
            ).add_to(m)

        # =========================
        # MAPA INTERACTIVO
        # =========================
        output = st_folium(
            m,
            height=700,
            width=1100,
            key="ONLY_MAP"
        )

        # =================================================
        # CLICK CONTROLADO (SIN RERUN, SIN RESET VISUAL)
        # =================================================
        if output and output.get("last_clicked"):

            click = output["last_clicked"]
            new_point = (click["lng"], click["lat"])

            # evita duplicados exactos
            if st.session_state.last_click != new_point:
                st.session_state.last_click = new_point
                st.session_state.line_points.append(new_point)

        # =================================================
        # DISTANCIA TOTAL
        # =================================================
        total = 0

        for i in range(len(st.session_state.line_points) - 1):
            lon1, lat1 = st.session_state.line_points[i]
            lon2, lat2 = st.session_state.line_points[i + 1]
            total += haversine(lon1, lat1, lon2, lat2)

        if len(st.session_state.line_points) > 1:
            st.success(f"📏 Distancia total: {total:,.2f} metros")

        # =================================================
        # RESET
        # =================================================
        if st.button("Reset línea"):
            st.session_state.line_points = []
            st.session_state.last_click = None


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