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

from shapely.geometry import shape
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


def extract_city(result):
    raw = (
        result.get("city")
        or result.get("municipality")
        or result.get("region")
        or result.get("address")
        or ""
    )

    if not raw:
        return "bogota"

    city = raw.split(",")[0].strip()
    city = re.sub(r"\d+", "", city)

    return city if city else "bogota"


# =========================================================
# COSTOS (EXCEL REAL)
# =========================================================
@st.cache_data
def load_costs():

    file_path = "costs.xlsx"  # 👈 OBLIGATORIO: archivo real

    df = pd.read_excel(file_path, engine="openpyxl")

    df.columns = df.columns.str.strip()

    # validación estricta
    if "Ciudad" not in df.columns or "Valor Unitario" not in df.columns:
        raise ValueError(
            f"El Excel debe contener columnas: 'Ciudad' y 'Valor Unitario'. "
            f"Se encontraron: {df.columns}"
        )

    df["Ciudad"] = df["Ciudad"].astype(str).str.strip()

    df["Ciudad_norm"] = df["Ciudad"].apply(normalize)

    df["Valor Unitario"] = pd.to_numeric(df["Valor Unitario"], errors="coerce")

    return df


costs_df = load_costs()


def get_unit_cost(city):

    city_norm = normalize(city)

    row = costs_df[costs_df["Ciudad_norm"] == city_norm]

    if row.empty:
        row = costs_df[costs_df["Ciudad_norm"].str.contains(city_norm, na=False)]

    if row.empty:
        return None

    return int(row.iloc[0]["Valor Unitario"])


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
    mrc = st.number_input("💰 MRC", value=3000000)

    if st.button("Analizar cotización"):

        result = resolve_input(location_input)

        if result is None:
            st.error("No se pudo encontrar ubicación")
            st.stop()

        lat, lon = result["lat"], result["lon"]

        city = extract_city(result)
        unit_cost = get_unit_cost(city)

        if unit_cost is None:
            st.error(f"No se encontró tarifa para ciudad: {city}")
            st.write(costs_df["Ciudad"].unique())
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

            presence_bonus = 1 if density > 3 else 0
            score = capex_score(d, density, presence_bonus)

            if score > best_score:
                best_score = score
                best_point = (c.x, c.y)

        st.session_state.analysis = {
            "lat": lat,
            "lon": lon,
            "city": city,
            "unit_cost": unit_cost,
            "mrc": mrc,
            "best_point": best_point,
            "score": best_score
        }

        st.success(f"✔ Ciudad detectada: {city} | costo: {unit_cost}")


# =========================================================
# FACTIBILIDAD
# =========================================================
if st.session_state.analysis:

    data = st.session_state.analysis

    mrc = data["mrc"]
    unit_cost = data["unit_cost"]

    if st.button("Evaluar factibilidad"):

        costo_obra = unit_cost * 10  # luego conectas distancia real

        ops = generate_opportunities(
            costo=costo_obra,
            mrc_input=mrc,
            term_input=24
        )

        feasible = len(ops) > 0

        if feasible:
            st.success("🟢 FACTIBILIDAD POSITIVA")
            st.json(ops)
        else:
            st.error("🔴 FACTIBILIDAD NEGATIVA")
            st.write("Opciones de mejora:")
            st.json(ops)