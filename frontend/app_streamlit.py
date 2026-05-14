import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

import streamlit as st
import json
import math
import folium
import pandas as pd
import unicodedata
import re

from shapely.geometry import shape, LineString
from collections import defaultdict
from streamlit_folium import st_folium

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
# NORMALIZACIÓN
# =========================================================
def normalize(text):
    if text is None:
        return ""

    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return text


# =========================================================
# COSTOS (EXCEL REAL, SOLO 2 COLUMNAS)
# =========================================================
@st.cache_data
def load_costs():
    df = pd.read_excel("costs.xlsx", engine="openpyxl")

    # limpieza estricta SIN renombrar columnas
    df.columns = df.columns.str.strip()

    if "Ciudad" not in df.columns or "Valor Unitario" not in df.columns:
        raise ValueError("El Excel debe tener: Ciudad | Valor Unitario")

    df["Ciudad"] = df["Ciudad"].astype(str).apply(normalize)
    df["Valor Unitario"] = pd.to_numeric(df["Valor Unitario"], errors="coerce")

    return df


costs_df = load_costs()


def get_unit_cost(city):
    city = normalize(city)

    row = costs_df[costs_df["Ciudad"] == city]

    if row.empty:
        return None

    return int(row.iloc[0]["Valor Unitario"])


# =========================================================
# DISTANCIA REAL
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
# DATA + ENGINE
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
# COTIZACIÓN (MAPA + LÍNEA)
# =========================================================
if section == "Cotización":

    st.header("📍 Cotización")

    location_input = st.text_input("📍 Dirección o coordenadas")
    mrc = st.number_input("💰 MRC", value=3000000)

    if st.button("Analizar cotización"):

        result = resolve_input(location_input)

        if result is None:
            st.error("No se pudo encontrar ubicación")
            st.stop()

        lat, lon = result["lat"], result["lon"]

        city = "bogota"  # fijo si no hay fuente confiable
        unit_cost = get_unit_cost(city)

        if unit_cost is None:
            st.error("No se encontró costo unitario en Excel")
            st.stop()

        candidates = engine.query(lon, lat)

        density_map = defaultdict(int)

        for h, idx in candidates:
            density_map[h] += 1

        best_score = -1
        best_point = None

        for h, idx in candidates:
            g = geometries[idx]
            c = g.centroid

            d = haversine(lon, lat, c.x, c.y)
            density = density_map[h]

            score = capex_score(d, density, 0)

            if score > best_score:
                best_score = score
                best_point = (c.x, c.y)

        st.session_state.analysis = {
            "client": (lon, lat),
            "best": best_point,
            "unit_cost": unit_cost,
            "mrc": mrc
        }

        st.session_state.line_points = []


# =========================================================
# MAPA + DIBUJO DE LÍNEA
# =========================================================
if st.session_state.analysis:

    data = st.session_state.analysis

    client = data["client"]
    best = data["best"]
    unit_cost = data["unit_cost"]

    m = folium.Map(location=[client[1], client[0]], zoom_start=13)

    folium.Marker([client[1], client[0]], tooltip="Cliente", icon=folium.Icon(color="red")).add_to(m)

    if best:
        folium.Marker([best[1], best[0]], tooltip="Óptimo", icon=folium.Icon(color="green")).add_to(m)

    # línea acumulada
    if len(st.session_state.line_points) > 1:
        folium.PolyLine(
            [(p[1], p[0]) for p in st.session_state.line_points],
            color="cyan",
            weight=5
        ).add_to(m)

    output = st_folium(m, height=650, width=1100)

    # click continuo (NO reinicia mapa)
    if output and output.get("last_clicked"):
        p = output["last_clicked"]
        new = (p["lng"], p["lat"])

        if not st.session_state.line_points or st.session_state.line_points[-1] != new:
            st.session_state.line_points.append(new)

    # distancia total real
    total = 0
    for i in range(len(st.session_state.line_points) - 1):
        lon1, lat1 = st.session_state.line_points[i]
        lon2, lat2 = st.session_state.line_points[i + 1]
        total += haversine(lon1, lat1, lon2, lat2)

    st.metric("Distancia total (m)", f"{total:,.2f}")


# =========================================================
# FACTIBILIDAD (SOLO AQUÍ DECIDE)
# =========================================================
if st.session_state.analysis:

    data = st.session_state.analysis
    unit_cost = data["unit_cost"]
    mrc = data["mrc"]

    if st.button("Evaluar factibilidad"):

        # costo real correcto
        distance = 0

        for i in range(len(st.session_state.line_points) - 1):
            lon1, lat1 = st.session_state.line_points[i]
            lon2, lat2 = st.session_state.line_points[i + 1]
            distance += haversine(lon1, lat1, lon2, lat2)

        costo_obra = distance * unit_cost

        ops = generate_opportunities(
            costo=costo_obra,
            mrc_input=mrc,
            term_input=24
        )

        if len(ops) > 0:
            st.success("🟢 FACTIBILIDAD POSITIVA")
        else:
            st.error("🔴 FACTIBILIDAD NEGATIVA")
            st.json(ops)