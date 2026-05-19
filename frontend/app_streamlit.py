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

def load_css():
    with open("styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()


st.image("logo.jpg", width=350)

st.markdown("""
<h1 style="margin-bottom:0;">CAPEX ENGINE</h1>
<p style="color:#6B7280;margin-top:0;">
Liberty Networks · Plataforma de evaluación CAPEX
</p>
""", unsafe_allow_html=True)


# =========================================================
# SESSION STATE
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
# EXTRACT CITY
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
        return normalize(address.split(",")[0])

    return "bogota"


# =========================================================
# COSTOS AUTOMÁTICOS DESDE EXCEL
# =========================================================
@st.cache_data
def load_costs():

    df = pd.read_excel(
        "costs.xlsx",
        engine="openpyxl"
    )

    # limpiar nombres columnas
    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
    )

    if "Ciudad" not in df.columns:
        raise ValueError(
            "Falta columna Ciudad"
        )

    if "Valor Unitario" not in df.columns:
        raise ValueError(
            "Falta columna Valor Unitario"
        )

    # =====================================================
    # NORMALIZAR CIUDADES
    # =====================================================
    df["Ciudad"] = (
        df["Ciudad"]
        .astype(str)
        .apply(normalize)
    )

    # =====================================================
    # CONVERSIÓN CORRECTA DE DECIMALES
    # =====================================================
    def parse_value(x):

        if pd.isna(x):
            return 0.0

        s = str(x).strip()

        # Caso Excel latino:
        # 10.500,6125 -> 10500.6125
        if "," in s and "." in s:
            s = s.replace(".", "")
            s = s.replace(",", ".")

        # Caso:
        # 10500,6125
        elif "," in s:
            s = s.replace(",", ".")

        try:
            return float(s)

        except:
            return 0.0

    df["Valor Unitario"] = (
        df["Valor Unitario"]
        .apply(parse_value)
    )

    # eliminar vacíos
    df = df.dropna(
        subset=["Ciudad", "Valor Unitario"]
    )

    return df


costs_df = load_costs()


def get_unit_cost(ciudad):

    ciudad = normalize(ciudad)

    # 1. MATCH EXACTO
    row = costs_df[costs_df["Ciudad"] == ciudad]

    # 2. FIX CRÍTICO: reconstrucción flexible por tokens
    if row.empty:

        def match_loose(x):
            x_tokens = set(x.split())
            c_tokens = set(ciudad.split())
            return len(x_tokens & c_tokens) > 0

        row = costs_df[costs_df["Ciudad"].apply(match_loose)]

    # 3. FALLBACK BOGOTÁ
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
# FEASIBILITY
# =========================================================
def evaluate_positive(
    costo,
    nrc,
    mrc,
    term
):

    if mrc <= 0:
        return False

    payback = (
        costo - nrc
    ) / mrc

    return payback <= (term / 2)


# =========================================================
# GENERATE OPTIONS
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
    mrc1 = math.ceil(
        (2 * costo) / term_entrada
    )

    if mrc1 <= mrc_entrada:
        mrc1 = mrc_entrada + 1

    opportunities.append({
        "oportunidad": 1,
        "term": term_entrada,
        "mrc": int(mrc1),
        "nrc": 0,
        "paybackMeses": round(
            costo / mrc1,
            2
        )
    })

    # =====================================================
    # OPORTUNIDAD 2
    # =====================================================
    term2 = 36

    mrc2 = int(mrc1 * 0.75)

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

    opportunities.append({
        "oportunidad": 2,
        "term": term2,
        "mrc": int(mrc2),
        "nrc": int(nrc2),
        "paybackMeses": round(
            (costo - nrc2) / mrc2,
            2
        )
    })

    # =====================================================
    # OPORTUNIDAD 3
    # =====================================================
    term3 = 24

    mrc3 = int(mrc2 * 1.2)

    while mrc3 in [mrc1, mrc2]:
        mrc3 += 1

    nrc3 = math.ceil(
        max(
            0,
            costo - (
                mrc3 * (term3 / 2)
            )
        )
    )

    opportunities.append({
        "oportunidad": 3,
        "term": term3,
        "mrc": int(mrc3),
        "nrc": int(nrc3),
        "paybackMeses": round(
            (costo - nrc3) / mrc3,
            2
        )
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

    engine = H3GeoEngine(
        resolution=9
    )

    engine.build(geometries)

    return engine


engine = build_engine()


# =========================================================
# UI
# =========================================================

# ✅ estado inicial
if "section" not in st.session_state:
    st.session_state.section = "Cotización"

# ✅ trigger para navegación
if "go_factibilidad" not in st.session_state:
    st.session_state.go_factibilidad = False


# ✅ CONTROL DEL RADIO (CLAVE)
options = ["Cotización", "Factibilidad"]

if st.session_state.go_factibilidad:
    default_index = 1  # Factibilidad
    st.session_state.go_factibilidad = False
else:
    default_index = options.index(st.session_state.section)

section = st.sidebar.radio(
    "Menú",
    options,
    index=default_index
)

# ✅ sincroniza estado
st.session_state.section = section

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

        result = resolve_input(
            location_input
        )

        if result is None:

            st.error(
                "No se pudo encontrar ubicación"
            )

            st.stop()

        lat = result["lat"]
        lon = result["lon"]

        ciudad = extract_city(result)

        valor_unitario = get_unit_cost(
            ciudad
        )

        candidates = engine.query(
            lon,
            lat
        )

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
            f"${valor_unitario:,.2f} COP/m"
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
            tiles="CartoDB positron"
        )

        folium.Marker(
            [lat, lon],
            tooltip="CLIENTE",
            icon=folium.Icon(color="red")
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

        if (
            output
            and "all_drawings" in output
        ):

            drawings = output[
                "all_drawings"
            ]

            if drawings:

                last = drawings[-1]

                if (
                    last["geometry"]["type"]
                    == "LineString"
                ):

                    st.session_state.draw_geojson = (
                        last["geometry"]["coordinates"]
                    )

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

        # =================================================
        # RESET REAL
        # =================================================
        
        if st.button("Ir a factibilidad"):
            st.session_state.go_factibilidad = True
            st.rerun()

# =========================================================
# FACTIBILIDAD
# =========================================================
else:

    st.header("💰 Factibilidad")

    if not st.session_state.analysis:

        st.warning(
            "Primero genera "
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
    # COSTO OBRAS
    # =====================================================
    valor_unitario = data[
        "valor_unitario"
    ]

    # =====================================================
    # AQUÍ ESTABA EL ERROR
    # =====================================================
    costo_obra = (
        total_distance
        * valor_unitario
    )

    costo_obra = int(costo_obra)

    # =====================================================
    # INFO
    # =====================================================
    st.write(
        f"📍 Ciudad: "
        f"{data['ciudad'].title()}"
    )

    st.write(
        f"📏 Distancia: "
        f"{total_distance:,.2f} m"
    )

    st.write(
        f"💵 Valor unitario: "
        f"${valor_unitario:,.2f} COP/m"
    )

    # =====================================================
    # CAMPOS
    # =====================================================
    st.number_input(
        "MRC",
        value=int(data["mrc"]),
        disabled=True
    )

    nrc = st.number_input(
        "NRC",
        value=0,
        step=100000
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

    # =====================================================
    # FACTIBILIDAD
    # =====================================================
    if st.button(
        "Evaluar factibilidad"
    ):

        mrc = int(data["mrc"])

        feasible = evaluate_positive(
            costo_obra,
            nrc,
            mrc,
            term
        )

        payback = (
            (costo_obra - nrc)
            / mrc
        ) if mrc > 0 else 999999

        if feasible:

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

            st.metric(
                "Payback",
                f"{payback:.2f} meses"
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