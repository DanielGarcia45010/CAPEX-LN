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

st.set_page_config(
    page_title="CAPEX ENGINE",
    layout="wide"
)

st.title("🚀 CAPEX ENGINE")


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

    return 2 * R * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


# =========================================================
# LOAD GEOJSON
# =========================================================

@st.cache_data
def load_data():

    with open("test.json", "r", encoding="utf-8") as f:

        data = json.load(f)

    return [shape(f["geometry"]) for f in data["features"]]


geometries = load_data()

# =========================================================
# BUILD ENGINE
# =========================================================

@st.cache_resource
def build_engine():

    engine = H3GeoEngine(resolution=9)

    engine.build(geometries)

    return engine


engine = build_engine()


# =========================================================
# SIDEBAR MENU
# =========================================================

st.sidebar.title("📌 Menú")

section = st.sidebar.radio(
    "Selecciona una opción",
    [
        "Cotización",
        "Factibilidad"
    ]
)


# =========================================================
# =========================================================
# 1. COTIZACIÓN
# =========================================================
# =========================================================

if section == "Cotización":

    st.header("📍 Cotización")

    st.write(
        """
        Esta sección permite analizar una nueva ubicación
        y determinar si el sitio es viable según la red
        existente y el valor mensual ofrecido por el cliente.
        """
    )

    # -----------------------------------------------------
    # INPUTS
    # -----------------------------------------------------

    location_input = st.text_input(
        "📍 Dirección o coordenadas",
        placeholder="Ej: Chapinero Bogotá o 4.7110,-74.0721"
    )

    mrc_cliente = st.number_input(
        "💰 Valor mensual ofrecido por el cliente (COP)",
        value=3000000,
        step=100000
    )

    # -----------------------------------------------------
    # ANALIZAR
    # -----------------------------------------------------

    if st.button("Analizar cotización"):

        result = resolve_input(location_input)

        if result is None:

            st.error("No se pudo encontrar la ubicación")

            st.stop()

        lat = result["lat"]
        lon = result["lon"]

        st.success(f"Ubicación encontrada: {result['address']}")

        # -------------------------------------------------
        # QUERY H3
        # -------------------------------------------------

        candidates = engine.query(lon, lat)

        if len(candidates) < 5:
            candidates = engine.query(
                lon,
                lat,
                max_k=10
            )

        st.write("📡 Nodos cercanos:", len(candidates))

        # -------------------------------------------------
        # SCORE
        # -------------------------------------------------

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

            presence_bonus = 1 if density > 3 else 0

            score = capex_score(
                d,
                density,
                presence_bonus
            )

            if score > best_score:

                best_score = score

                best_point = (c.x, c.y)

        # -------------------------------------------------
        # FACTIBILIDAD SIMPLE
        # -------------------------------------------------

        FACTIBLE_THRESHOLD = 2.5

        viable = (
            best_score * mrc_cliente
        ) > FACTIBLE_THRESHOLD * 1000000

        # -------------------------------------------------
        # RESULTADO
        # -------------------------------------------------

        if viable:

            st.success("✅ El sitio es FACTIBLE")

        else:

            st.error("❌ El sitio NO es factible")

            st.warning(
                """
                Será necesario generar opciones de
                factibilidad financiera.
                """
            )

        st.metric(
            "CAPEX SCORE",
            f"{best_score:.4f}"
        )

        # -------------------------------------------------
        # MAPA
        # -------------------------------------------------

        layers = []

        # USER
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=[
                    {
                        "position": [lon, lat]
                    }
                ],
                get_position="position",
                get_radius=140,
                get_fill_color=[255, 0, 0]
            )
        )

        # BEST NODE
        if best_point:

            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=[
                        {
                            "position": list(best_point)
                        }
                    ],
                    get_position="position",
                    get_radius=180,
                    get_fill_color=[0, 255, 0]
                )
            )

        # NETWORK
        red_points = []

        for geom in geometries:

            try:

                c = geom.centroid

                red_points.append({
                    "position": [c.x, c.y]
                })

            except:
                continue

        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=red_points,
                get_position="position",
                get_radius=10,
                get_fill_color=[0, 255, 0, 120],
                pickable=False
            )
        )

        # MAP
        st.pydeck_chart(
            pdk.Deck(
                layers=layers,

                initial_view_state=pdk.ViewState(
                    latitude=lat,
                    longitude=lon,
                    zoom=11
                ),

                map_style="mapbox://styles/mapbox/dark-v10"
            )
        )


# =========================================================
# =========================================================
# 2. FACTIBILIDAD
# =========================================================
# =========================================================

if section == "Factibilidad":

    st.header("💰 Factibilidad")

    st.write(
        """
        Esta sección permite generar alternativas
        financieras cuando un sitio no es viable.
        """
    )

    # -----------------------------------------------------
    # INPUTS
    # -----------------------------------------------------

    costo = st.number_input(
        "🏗 Costo de obra civil (COP)",
        value=100000000,
        step=1000000
    )

    mrc = st.number_input(
        "💵 MRC actual (COP)",
        value=3000000,
        step=100000
    )

    nrc = st.number_input(
        "💳 NRC actual (COP)",
        value=0,
        step=100000
    )

    term = st.number_input(
        "📅 Termino (meses)",
        value=24,
        step=1
    )

    # -----------------------------------------------------
    # ANALIZAR
    # -----------------------------------------------------

    if st.button("Generar opciones"):

        try:

            res = requests.post(
                "http://localhost:8000/feasibility",
                json={
                    "costoObraCivil": int(costo),
                    "mrc": int(mrc),
                    "term": int(term)
                }
            )

            data = res.json()

            st.success(
                "✅ Opciones generadas correctamente"
            )

            # ---------------------------------------------
            # RESULTADOS
            # ---------------------------------------------

            for opp in data:

                with st.container(border=True):

                    st.subheader(
                        f"Oportunidad {opp['oportunidad']}"
                    )

                    st.metric(
                        "MRC",
                        f"${opp['mrc']:,} COP"
                    )

                    st.metric(
                        "NRC",
                        f"${opp['nrc']:,} COP"
                    )

                    st.metric(
                        "Term",
                        f"{opp['term']} meses"
                    )

        except Exception as e:

            st.error(str(e))