import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

import streamlit as st
import json
import math
import pandas as pd

from shapely.geometry import shape
from collections import defaultdict
from streamlit_folium import st_folium

import folium

from core.geo_engine_h3 import H3GeoEngine
from core.capex_scoring import capex_score
from utils.geocoder import resolve_input
from core.feasibility import generate_opportunities


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
# EXCEL COSTOS
# =========================================================
@st.cache_data
def load_costs():

    df = pd.read_csv(
        "costs.csv",
        sep="\t",          
        encoding="utf-8"
    )

    df.columns = ["Ciudad", "Valor Unitario"]

    return df


costs_df = load_costs()


def get_unit_cost(city: str):
    row = costs_df[costs_df["Ciudad"] == city]
    if row.empty:
        return None
    return float(row["Valor Unitario"].values[0])


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
    city = st.text_input("🏙️ Ciudad")
    mrc_cliente = st.number_input("💰 MRC", value=3000000)

    if st.button("Analizar cotización"):

        result = resolve_input(location_input)

        if result is None:
            st.error("No se pudo encontrar ubicación")
            st.stop()

        lat = result["lat"]
        lon = result["lon"]

        st.success(result["address"])

        # distancia simple base (puedes reemplazar luego por routing real)
        candidates = engine.query(lon, lat)

        best_point = None
        best_score = -1

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

        # distancia aproximada cliente → punto óptimo
        distance = haversine(lon, lat, best_point[0], best_point[1])

        st.session_state.analysis = {
            "lat": lat,
            "lon": lon,
            "best_point": best_point,
            "distance": distance,
            "mrc": mrc_cliente,
            "city": city
        }

        st.session_state.line_points = []


# =========================================================
# FACTIBILIDAD
# =========================================================
else:

    st.header("💰 Factibilidad")

    if st.session_state.analysis:

        data = st.session_state.analysis

        city = data["city"]
        distance = data["distance"]
        mrc = data["mrc"]

        unit_cost = get_unit_cost(city)

        if unit_cost is None:
            st.error("Ciudad no encontrada en Excel")
            st.stop()

        costo_obra = distance * unit_cost

        st.metric("Costo obra civil", f"${costo_obra:,.0f}")

        term = 24

        opportunities = generate_opportunities(
            costo=int(costo_obra),
            mrc_input=int(mrc),
            term_input=term
        )

        if len(opportunities) == 0:

            st.error("❌ Factibilidad NEGATIVA")

            st.write("No existe configuración válida")

        elif len(opportunities) >= 1:

            st.success("✅ Factibilidad POSITIVA")

            for op in opportunities:

                st.subheader(f"Oportunidad {op['oportunidad']}")

                st.write(f"MRC: {op['mrc']}")
                st.write(f"NRC: {op['nrc']}")
                st.write(f"Term: {op['term']}")

    else:
        st.warning("Primero ejecuta Cotización")