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

from folium.plugins import Draw

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

if "analysis" not in st.session_state:
    st.session_state.analysis = None

if "draw_geojson" not in st.session_state:
    st.session_state.draw_geojson = None


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
# UI
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
    # ANÁLISIS CAPEX (SIN CAMBIOS)
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
    # MAPA + DRAW TOOL (ESTO ES LA CLAVE)
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

        # CLIENTE
        folium.Marker(
            [lat, lon],
            tooltip="CLIENTE",
            icon=folium.Icon(color="red")
        ).add_to(m)

        # ÓPTIMO
        if best_point:
            folium.Marker(
                [best_point[1], best_point[0]],
                tooltip="ÓPTIMO",
                icon=folium.Icon(color="green")
            ).add_to(m)

        # =========================
        # 🔥 LEAFLET DRAW TOOL
        # =========================
        draw = Draw(
            export=True,
            filename="route.geojson",
            position="topleft",
            draw_options={
                "polyline": True,
                "polygon": False,
                "circle": False,
                "rectangle": False,
                "marker": True,
                "circlemarker": False,
            },
            edit_options={"edit": True, "remove": True},
        )

        draw.add_to(m)

        # =========================
        # RENDER MAPA
        # =========================
        output = st_folium(
            m,
            height=750,
            width=1100,
            key="DRAW_MAP"
        )

        # =========================
        # CAPTURA DE DIBUJO REAL
        # =========================
        if output and "all_drawings" in output:

            drawings = output["all_drawings"]

            if drawings:

                last = drawings[-1]

                if last["geometry"]["type"] == "LineString":
                    coords = last["geometry"]["coordinates"]

                    st.session_state.draw_geojson = coords

        # =========================
        # DISTANCIA REAL SOBRE LÍNEA
        # =========================
        total = 0

        if st.session_state.draw_geojson and len(st.session_state.draw_geojson) > 1:

            pts = st.session_state.draw_geojson

            for i in range(len(pts) - 1):
                lon1, lat1 = pts[i]
                lon2, lat2 = pts[i + 1]
                total += haversine(lon1, lat1, lon2, lat2)

            st.success(f"📏 Distancia total: {total:,.2f} metros")

        # =========================
        # RESET
        # =========================
        if st.button("Reset ruta"):
            st.session_state.draw_geojson = None


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