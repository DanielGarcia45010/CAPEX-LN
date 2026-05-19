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
# NORMALIZE
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
# CITY EXTRACTION
# =========================================================
def extract_city(result):

    possible = [
        result.get("city"),
        result.get("town"),
        result.get("village"),
        result.get("municipality"),
        result.get("county"),
        result.get("state_district"),
        result.get("region"),
    ]

    for value in possible:
        if value and str(value).strip():
            return normalize(value)

    address = result.get("address", "")

    if address:
        first = address.split(",")[0]
        return normalize(first)

    return "bogota"


# =========================================================
# COSTS
# =========================================================
@st.cache_data
def load_costs():

    df = pd.read_excel("costs.xlsx", engine="openpyxl")

    df.columns = df.columns.str.strip()

    if "Ciudad" not in df.columns:
        raise ValueError("Falta columna Ciudad")

    if "Valor Unitario" not in df.columns:
        raise ValueError("Falta columna Valor Unitario")

    df["Ciudad"] = df["Ciudad"].astype(str).apply(normalize)

    # =====================================================
    # CONVERSIÓN CORRECTA
    # 10.500,6125 -> 10500.6125
    # =====================================================
    df["Valor Unitario"] = (
        df["Valor Unitario"]
        .astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    df["Valor Unitario"] = pd.to_numeric(
        df["Valor Unitario"],
        errors="coerce"
    )

    return df


costs_df = load_costs()


def get_unit_cost(ciudad):

    ciudad = normalize(ciudad)

    row = costs_df[costs_df["Ciudad"] == ciudad]

    if row.empty:

        row = costs_df[
            costs_df["Ciudad"].str.contains(
                ciudad,
                na=False
            )
        ]

    if row.empty:
        row = costs_df[costs_df["Ciudad"] == "bogota"]

    return float(row.iloc[0]["Valor Unitario"])


# =========================================================
# DISTANCE
# =========================================================
def haversine(lon1, lat1, lon2, lat2):

    R = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    return 2 * R * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


# =========================================================
# FEASIBILITY RULE
# =========================================================
def evaluate_positive(costo, mrc, term):

    if mrc <= 0:
        return False

    payback = costo / mrc

    return payback <= (term / 2)


# =========================================================
# NEGATIVE OPTIONS
# =========================================================
def generate_negative_options(
    costo,
    mrc_entrada,
    term_entrada
):

    opportunities = []

    # =====================================================
    # OPORTUNIDAD 1
    # =====================================================
    term1 = term_entrada

    mrc1 = math.ceil(
        (2 * costo) / term1
    )

    if mrc1 <= mrc_entrada:
        mrc1 = int(mrc_entrada) + 1

    nrc1 = 0

    payback1 = (
        costo - nrc1
    ) / mrc1

    opportunities.append({
        "oportunidad": 1,
        "term": int(term1),
        "mrc": int(mrc1),
        "nrc": int(nrc1),
        "paybackMeses": round(payback1, 2)
    })

    # =====================================================
    # OPORTUNIDAD 2
    # =====================================================
    term2 = 36

    mrc2 = max(
        int(mrc_entrada * 1.2),
        int(mrc1 * 0.75)
    )

    if mrc2 == mrc1:
        mrc2 += 1

    nrc2 = math.ceil(
        max(
            0,
            costo - (
                mrc2 * (term2 / 2)
            )
        )
    )

    max_nrc = costo * 0.4

    if nrc2 > max_nrc:

        mrc2 = math.ceil(
            (costo - max_nrc)
            / (term2 / 2)
        )

        while mrc2 in [
            mrc_entrada,
            mrc1
        ]:
            mrc2 += 1

        nrc2 = math.ceil(
            max(
                0,
                costo - (
                    mrc2 * (term2 / 2)
                )
            )
        )

    payback2 = (
        costo - nrc2
    ) / mrc2

    opportunities.append({
        "oportunidad": 2,
        "term": int(term2),
        "mrc": int(mrc2),
        "nrc": int(nrc2),
        "paybackMeses": round(payback2, 2)
    })

    # =====================================================
    # OPORTUNIDAD 3
    # =====================================================
    term3 = 24

    mrc3 = max(
        int(mrc_entrada * 1.4),
        int(mrc2 * 0.9)
    )

    while mrc3 in [
        mrc_entrada,
        mrc1,
        mrc2
    ]:
        mrc3 += 1

    nrc3 = math.ceil(
        max(
            0,
            costo - (
                mrc3 * (term3 / 2)
            )
        )
    )

    if nrc3 > max_nrc:

        mrc3 = math.ceil(
            (costo - max_nrc)
            / (term3 / 2)
        )

        while mrc3 in [
            mrc_entrada,
            mrc1,
            mrc2
        ]:
            mrc3 += 1

        nrc3 = math.ceil(
            max(
                0,
                costo - (
                    mrc3 * (term3 / 2)
                )
            )
        )

    payback3 = (
        costo - nrc3
    ) / mrc3

    opportunities.append({
        "oportunidad": 3,
        "term": int(term3),
        "mrc": int(mrc3),
        "nrc": int(nrc3),
        "paybackMeses": round(payback3, 2)
    })

    return opportunities


# =========================================================
# DATA
# =========================================================
@st.cache_data
def load_data():

    with open(
        "test.json",
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    return [
        shape(f["geometry"])
        for f in data["features"]
    ]


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
section = st.sidebar.radio(
    "Menú",
    ["Cotización", "Factibilidad"]
)


# =========================================================
# COTIZACIÓN
# =========================================================
if section == "Cotización":

    st.header("📍 Cotización")

    location_input = st.text_input(
        "📍 Dirección o coordenadas"
    )

    mrc_cliente = st.number_input(
        "💰 MRC",
        value=0,
        step=100000
    )

    if st.button("Analizar cotización"):

        result = resolve_input(location_input)

        if result is None:
            st.error(
                "No se pudo encontrar ubicación"
            )
            st.stop()

        lat = result["lat"]
        lon = result["lon"]

        ciudad = extract_city(result)

        valor_unitario = get_unit_cost(ciudad)

        candidates = engine.query(lon, lat)

        best_score = -1
        best_point = None

        density_map = defaultdict(int)

        for h, idx in candidates:
            density_map[h] += 1

        for h, idx in candidates:

            g = geometries[idx]
            c = g.centroid

            d = haversine(
                lon,
                lat,
                c.x,
                c.y
            )

            density = density_map[h]

            presence_bonus = (
                1 if density > 3 else 0
            )

            score = capex_score(
                d,
                density,
                presence_bonus
            )

            if score > best_score:

                best_score = score
                best_point = (
                    c.x,
                    c.y
                )

        st.session_state.analysis = {
            "lat": lat,
            "lon": lon,
            "best_point": best_point,
            "score": best_score,
            "mrc": int(mrc_cliente),
            "ciudad": ciudad,
            "valor_unitario": valor_unitario
        }

        st.session_state.draw_geojson = None

        st.success(
            f"Ciudad detectada: "
            f"{ciudad.title()}"
        )

        st.success(
            f"Valor unitario: "
            f"${valor_unitario:,.2f} COP"
        )

    # =====================================================
    # MAPA
    # =====================================================
    if st.session_state.analysis:

        data = st.session_state.analysis

        lat = data["lat"]
        lon = data["lon"]

        best_point = data["best_point"]

        st.metric(
            "CAPEX SCORE",
            f"{data['score']:.4f}"
        )

        m = folium.Map(
            location=[lat, lon],
            zoom_start=13,
            tiles="CartoDB dark_matter"
        )

        folium.Marker(
            [lat, lon],
            tooltip="CLIENTE",
            icon=folium.Icon(
                color="red"
            )
        ).add_to(m)

        if best_point:

            folium.Marker(
                [
                    best_point[1],
                    best_point[0]
                ],
                tooltip="ÓPTIMO",
                icon=folium.Icon(
                    color="green"
                )
            ).add_to(m)

        draw = Draw(
            export=True,
            filename="route.geojson",
            position="topleft",
            draw_options={
                "polyline": True,
                "polygon": False,
                "circle": False,
                "rectangle": False,
                "marker": False,
                "circlemarker": False,
            },
            edit_options={
                "edit": True,
                "remove": True
            },
        )

        draw.add_to(m)

        output = st_folium(
            m,
            height=750,
            width=1100,
            key="DRAW_MAP"
        )

        if output and "all_drawings" in output:

            drawings = output[
                "all_drawings"
            ]

            if drawings:

                last = drawings[-1]

                if (
                    last["geometry"]["type"]
                    == "LineString"
                ):

                    coords = last[
                        "geometry"
                    ]["coordinates"]

                    st.session_state.draw_geojson = coords

        total = 0

        if (
            st.session_state.draw_geojson
            and len(
                st.session_state.draw_geojson
            ) > 1
        ):

            pts = (
                st.session_state.draw_geojson
            )

            for i in range(
                len(pts) - 1
            ):

                lon1, lat1 = pts[i]
                lon2, lat2 = pts[i + 1]

                total += haversine(
                    lon1,
                    lat1,
                    lon2,
                    lat2
                )

            st.success(
                f"📏 Distancia total: "
                f"{total:,.2f} metros"
            )

        if st.button("Reset ruta"):
            st.session_state.draw_geojson = None


# =========================================================
# FACTIBILIDAD
# =========================================================
else:

    st.header("💰 Factibilidad")

    if not st.session_state.analysis:

        st.warning(
            "Primero debes generar "
            "una cotización."
        )

        st.stop()

    data = st.session_state.analysis

    # =====================================================
    # DISTANCIA
    # =====================================================
    total_distance = 0

    if (
        st.session_state.draw_geojson
        and len(
            st.session_state.draw_geojson
        ) > 1
    ):

        pts = (
            st.session_state.draw_geojson
        )

        for i in range(
            len(pts) - 1
        ):

            lon1, lat1 = pts[i]
            lon2, lat2 = pts[i + 1]

            total_distance += haversine(
                lon1,
                lat1,
                lon2,
                lat2
            )

    # =====================================================
    # CONVERSIÓN CORRECTA
    # Valor unitario está en COP por km
    # distancia viene en metros
    # =====================================================

    distancia_km = total_distance / 1000

    valor_unitario = data["valor_unitario"]

    costo_obra = math.ceil(
        distancia_km * valor_unitario
    )

    # =====================================================
    # CAMPOS
    # =====================================================
    st.number_input(
        "MRC",
        value=int(data["mrc"]),
        disabled=True
    )

    term = st.selectbox(
        "Term (meses)",
        options=[12, 24, 36],
        index=1
    )

    st.number_input(
        "Costo de Obras",
        value=float(costo_obra),
        disabled=True
    )

    st.write(
        f"📍 Ciudad: "
        f"{data['ciudad'].title()}"
    )

    st.write(
        f"📏 Distancia: "
        f"{distancia_km:,.2f} km"
    )

    st.write(
        f"💵 Valor unitario: "
        f"${valor_unitario:,.2f} COP/km"
    )

    # =====================================================
    # EVALUAR
    # =====================================================
    if st.button(
        "Evaluar factibilidad"
    ):

        mrc = int(data["mrc"])

        feasible = evaluate_positive(
            costo_obra,
            mrc,
            term
        )

        if feasible:

            payback = (
                costo_obra / mrc
            )

            st.success(
                "🟢 FACTIBILIDAD POSITIVA"
            )

            st.metric(
                "Payback",
                f"{payback:.2f} meses"
            )

        else:

            st.error(
                "🔴 FACTIBILIDAD NEGATIVA"
            )

            st.subheader(
                "3 oportunidades requeridas"
            )

            ops = generate_negative_options(
                costo_obra,
                mrc,
                term
            )

            st.json(ops)