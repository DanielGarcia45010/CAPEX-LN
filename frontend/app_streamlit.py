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
import html
import hashlib

from datetime import datetime
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

st.set_page_config(
    page_title="CAPEX ENGINE",
    layout="wide"
)


# =========================================================
# RUTAS
# =========================================================

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_FILE = DATA_DIR / "historial_factibilidades.json"


# =========================================================
# CSS
# =========================================================

def load_css():

    css_path = ROOT / "frontend" / "styles.css"

    if not css_path.exists():
        css_path = ROOT / "styles.css"

    if css_path.exists():

        with open(
            css_path,
            "r",
            encoding="utf-8"
        ) as f:

            st.markdown(
                f"<style>{f.read()}</style>",
                unsafe_allow_html=True
            )


load_css()


# =========================================================
# LOGO
# =========================================================

logo_path = ROOT / "frontend" / "logo.jpg"

if not logo_path.exists():
    logo_path = ROOT / "logo.jpg"

if logo_path.exists():

    st.image(
        str(logo_path),
        width=350
    )


st.markdown(
    """
    <h1 style="margin-bottom:0;">
        CAPEX ENGINE
    </h1>

    <p style="
        color:#6B7280;
        margin-top:0;
    ">
        Liberty Networks · Plataforma de evaluación CAPEX
    </p>
    """,
    unsafe_allow_html=True
)


# =========================================================
# SESSION STATE
# =========================================================

DEFAULT_STATE = {
    "analysis": None,
    "draw_geojson": None,
    "section": "Cotización",
    "factibilidad_resultado": None,
    "factibilidad_id": None,
    "historial_seleccionado": None,
}


for key, value in DEFAULT_STATE.items():

    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# HISTORIAL JSON
# =========================================================

def initialize_history_file():

    if not HISTORY_FILE.exists():

        initial_data = {
            "ultimo_serial": 0,
            "factibilidades": []
        }

        save_history(initial_data)


def save_history(data):

    temp_file = HISTORY_FILE.with_suffix(".tmp")

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )

    temp_file.replace(HISTORY_FILE)


def load_history():

    initialize_history_file()

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

    except Exception:

        data = {
            "ultimo_serial": 0,
            "factibilidades": []
        }

        save_history(data)

        return data

    # -----------------------------------------------------
    # COMPATIBILIDAD CON JSON ANTIGUO
    # -----------------------------------------------------

    if isinstance(data, list):

        max_serial = 0

        for item in data:

            fact_id = str(
                item.get("id", "")
            )

            match = re.search(
                r"CO(\d+)",
                fact_id
            )

            if match:

                max_serial = max(
                    max_serial,
                    int(match.group(1))
                )

        data = {
            "ultimo_serial": max_serial,
            "factibilidades": data
        }

        save_history(data)

    if not isinstance(data, dict):

        data = {
            "ultimo_serial": 0,
            "factibilidades": []
        }

    if "ultimo_serial" not in data:
        data["ultimo_serial"] = 0

    if "factibilidades" not in data:
        data["factibilidades"] = []

    # -----------------------------------------------------
    # ASEGURAR QUE EL SERIAL NUNCA RETROCEDA
    # -----------------------------------------------------

    max_serial = 0

    for item in data["factibilidades"]:

        fact_id = str(
            item.get("id", "")
        )

        match = re.search(
            r"CO(\d+)",
            fact_id
        )

        if match:

            max_serial = max(
                max_serial,
                int(match.group(1))
            )

    if max_serial > int(data["ultimo_serial"]):

        data["ultimo_serial"] = max_serial

        save_history(data)

    return data


initialize_history_file()


# =========================================================
# GENERAR ID
# =========================================================

def get_next_factibilidad_id():

    history = load_history()

    next_serial = (
        int(history["ultimo_serial"])
        + 1
    )

    return (
        f"CO{next_serial:06d}",
        next_serial
    )


# =========================================================
# FIRMA ÚNICA
# =========================================================

def build_factibilidad_fingerprint(record):

    datos = record.get(
        "datos_cliente",
        {}
    )

    presupuesto = record.get(
        "presupuestos",
        {}
    )

    data = {

        "tipo":
            record.get(
                "tipo",
                ""
            ),

        "operador":
            datos.get(
                "operador",
                ""
            ),

        "nombre_servicio":
            datos.get(
                "nombre_servicio",
                ""
            ),

        "ciudad":
            datos.get(
                "ciudad",
                ""
            ),

        "lat":
            datos.get(
                "lat",
                0
            ),

        "lon":
            datos.get(
                "lon",
                0
            ),

        "mrc":
            presupuesto.get(
                "mrc",
                0
            ),

        "nrc":
            presupuesto.get(
                "nrc",
                0
            ),

        "term":
            presupuesto.get(
                "term",
                0
            ),

        "costo_obra":
            presupuesto.get(
                "costo_obra",
                0
            ),

        "distancia":
            presupuesto.get(
                "distancia",
                0
            ),

        "oportunidades":
            record.get(
                "oportunidades",
                []
            )
    }

    serialized = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


# =========================================================
# REGISTRAR FACTIBILIDAD
# =========================================================

def register_factibilidad(record):

    history = load_history()

    fingerprint = build_factibilidad_fingerprint(
        record
    )

    # -----------------------------------------------------
    # EVITAR DUPLICADOS
    # -----------------------------------------------------

    for existing in history["factibilidades"]:

        if existing.get(
            "fingerprint"
        ) == fingerprint:

            return (
                existing.get("id"),
                False
            )

    # -----------------------------------------------------
    # NUEVO SERIAL
    # -----------------------------------------------------

    next_serial = (
        int(
            history.get(
                "ultimo_serial",
                0
            )
        )
        + 1
    )

    fact_id = (
        f"CO{next_serial:06d}"
    )

    record["id"] = fact_id

    record["serial"] = next_serial

    record["fingerprint"] = fingerprint

    record["fecha"] = (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    # -----------------------------------------------------
    # ESTADO
    # -----------------------------------------------------
    #
    # Se guarda explícitamente para evitar el error:
    # KeyError: 'estado'
    #

    if record.get("tipo") == "POSITIVA":

        record["estado"] = "POSITIVA"

    else:

        record["estado"] = "NEGATIVA"

    history["ultimo_serial"] = next_serial

    history["factibilidades"].append(
        record
    )

    save_history(history)

    return (
        fact_id,
        True
    )


# =========================================================
# NORMALIZAR TEXTO
# =========================================================

def normalize(text):

    if text is None:
        return ""

    text = unicodedata.normalize(
        "NFKD",
        str(text)
    )

    text = text.encode(
        "ascii",
        "ignore"
    ).decode(
        "utf-8"
    )

    text = text.lower().strip()

    text = re.sub(
        r"[^a-z0-9 ]",
        "",
        text
    )

    return text


# =========================================================
# COSTOS
# =========================================================

@st.cache_data
def load_costs():

    costs_path = (
        ROOT
        / "data"
        / "costs.xlsx"
    )

    if not costs_path.exists():

        costs_path = (
            ROOT
            / "costs.xlsx"
        )

    df = pd.read_excel(
        costs_path,
        engine="openpyxl"
    )

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
    )

    if "Ciudad" not in df.columns:

        raise ValueError(
            "Falta columna Ciudad en costs.xlsx"
        )

    if "Valor Unitario" not in df.columns:

        raise ValueError(
            "Falta columna Valor Unitario en costs.xlsx"
        )

    df["Ciudad"] = (
        df["Ciudad"]
        .astype(str)
        .apply(normalize)
    )

    def parse_value(x):

        if pd.isna(x):
            return 0.0

        s = str(x).strip()

        if "," in s and "." in s:

            s = s.replace(
                ".",
                ""
            )

            s = s.replace(
                ",",
                "."
            )

        elif "," in s:

            s = s.replace(
                ",",
                "."
            )

        try:

            return float(s)

        except Exception:

            return 0.0

    df["Valor Unitario"] = (
        df["Valor Unitario"]
        .apply(parse_value)
    )

    return df.dropna(
        subset=[
            "Ciudad",
            "Valor Unitario"
        ]
    )


costs_df = load_costs()


# =========================================================
# EXTRAER CIUDAD
# =========================================================

def extract_city(result):

    address = normalize(
        result.get(
            "address",
            ""
        )
    )

    cities = (
        costs_df["Ciudad"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    for city in cities:

        if city in address:

            return city

    return "bogota"


# =========================================================
# COSTO UNITARIO
# =========================================================

def get_unit_cost(ciudad):

    ciudad = normalize(
        ciudad
    )

    row = costs_df[
        costs_df["Ciudad"] == ciudad
    ]

    if row.empty:

        def match_loose(x):

            x_tokens = set(
                x.split()
            )

            c_tokens = set(
                ciudad.split()
            )

            return len(
                x_tokens & c_tokens
            ) > 0

        row = costs_df[
            costs_df["Ciudad"].apply(
                match_loose
            )
        ]

    if row.empty:

        row = costs_df[
            costs_df["Ciudad"] == "bogota"
        ]

    return float(
        row.iloc[0][
            "Valor Unitario"
        ]
    )


# =========================================================
# HAVERSINE
# =========================================================

def haversine(
    lon1,
    lat1,
    lon2,
    lat2
):

    R = 6371000

    phi1 = math.radians(
        lat1
    )

    phi2 = math.radians(
        lat2
    )

    dphi = math.radians(
        lat2 - lat1
    )

    dlambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dphi / 2) ** 2
        +
        math.cos(phi1)
        *
        math.cos(phi2)
        *
        math.sin(
            dlambda / 2
        ) ** 2
    )

    return (
        2
        * R
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


# =========================================================
# FACTIBILIDAD POSITIVA
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

    return (
        payback
        <=
        term / 2
    )


# =========================================================
# GENERAR 3 OPCIONES
# =========================================================

def generate_negative_options(
    costo,
    mrc_entrada,
    term_entrada
):

    opportunities = []

    # -----------------------------------------------------
    # OPCIÓN 1
    # -----------------------------------------------------

    mrc1 = math.ceil(
        (2 * costo)
        / term_entrada
    )

    if mrc1 <= mrc_entrada:

        mrc1 = (
            mrc_entrada
            + 1
        )

    payback1 = (
        costo / mrc1
    )

    opportunities.append({

        "oportunidad": 1,

        "term": int(
            term_entrada
        ),

        "mrc": int(
            mrc1
        ),

        "nrc": 0,

        "paybackMeses":
            round(
                payback1,
                2
            )
    })

    # -----------------------------------------------------
    # OPCIÓN 2
    # -----------------------------------------------------

    term2 = 36

    mrc2 = int(
        mrc1 * 0.75
    )

    if mrc2 <= 0:
        mrc2 = 1

    if mrc2 == mrc1:
        mrc2 += 1

    nrc2 = math.ceil(
        max(
            0,
            costo
            -
            (
                mrc2
                *
                (
                    term2 / 2
                )
            )
        )
    )

    payback2 = (
        costo - nrc2
    ) / mrc2

    opportunities.append({

        "oportunidad": 2,

        "term": term2,

        "mrc": int(
            mrc2
        ),

        "nrc": int(
            nrc2
        ),

        "paybackMeses":
            round(
                payback2,
                2
            )
    })

    # -----------------------------------------------------
    # OPCIÓN 3
    # -----------------------------------------------------

    term3 = 24

    mrc3 = int(
        mrc2 * 1.20
    )

    if mrc3 <= 0:
        mrc3 = 1

    while mrc3 in [
        mrc1,
        mrc2
    ]:

        mrc3 += 1

    nrc3 = math.ceil(
        max(
            0,
            costo
            -
            (
                mrc3
                *
                (
                    term3 / 2
                )
            )
        )
    )

    payback3 = (
        costo - nrc3
    ) / mrc3

    opportunities.append({

        "oportunidad": 3,

        "term": term3,

        "mrc": int(
            mrc3
        ),

        "nrc": int(
            nrc3
        ),

        "paybackMeses":
            round(
                payback3,
                2
            )
    })

    return opportunities


# =========================================================
# HTML SEGURO
# =========================================================

def safe_html(value):

    if value is None:
        return ""

    return html.escape(
        str(value)
    )


# =========================================================
# TABLA DE FACTIBILIDAD
#
# ESTA FUNCIÓN ES LA IMPORTANTE.
#
# Se conserva el diseño original de la tabla.
# =========================================================

def render_feasibility_response(
    titulo,
    operador,
    nombre_servicio,
    ciudad,
    lat,
    lon,
    mrc,
    nrc,
    term,
    factibilidad_id=None,
    color="#FF7A00"
):

    titulo = safe_html(
        titulo
    )

    operador = safe_html(
        operador
    )

    nombre_servicio = safe_html(
        nombre_servicio
    )

    ciudad = safe_html(
        str(ciudad).title()
    )

    fact_id = safe_html(
        factibilidad_id
        if factibilidad_id
        else ""
    )

    try:

        lat_text = (
            f"{float(lat):.6f}"
        )

    except Exception:

        lat_text = "0.000000"

    try:

        lon_text = (
            f"{float(lon):.6f}"
        )

    except Exception:

        lon_text = "0.000000"

    try:

        mrc_text = (
            f"${float(mrc):,.0f} COP"
        )

    except Exception:

        mrc_text = "$0 COP"

    try:

        nrc_text = (
            f"${float(nrc):,.0f} COP"
        )

    except Exception:

        nrc_text = "$0 COP"

    term_text = safe_html(
        term
    )

    # =====================================================
    # ENCABEZADO + TABLA
    # =====================================================

    html_block = f"""

    <div style="
        width:100%;
        margin-top:15px;
        margin-bottom:25px;
        padding:0;
        font-family:Arial,sans-serif;
        box-sizing:border-box;
    ">

        <!-- =============================================
             ENCABEZADO
             ============================================= -->

        <div style="
            width:100%;
            display:flex;
            flex-direction:row;
            align-items:stretch;
            margin:0;
            padding:0;
            box-sizing:border-box;
        ">

            <!-- TITULO -->

            <div style="
                flex:1;
                background:{color};
                color:#FFFFFF;
                text-align:center;
                font-family:Arial,sans-serif;
                font-size:23px;
                font-weight:700;
                padding:7px 10px;
                border:1px solid #000000;
                display:flex;
                align-items:center;
                justify-content:center;
                box-sizing:border-box;
                min-height:48px;
            ">
                {titulo}
            </div>


            <!-- ID -->

            <div style="
                min-width:145px;
                background:#000000;
                color:#FFFFFF;
                text-align:center;
                font-family:Arial,sans-serif;
                font-size:21px;
                font-weight:700;
                padding:7px 12px;
                border-top:1px solid #000000;
                border-right:1px solid #000000;
                border-bottom:1px solid #000000;
                display:flex;
                align-items:center;
                justify-content:center;
                white-space:nowrap;
                box-sizing:border-box;
                min-height:48px;
            ">
                {fact_id}
            </div>

        </div>


        <!-- =============================================
             TABLA COMPLETA
             ============================================= -->

        <table style="
            width:100% !important;
            border-collapse:collapse !important;
            border-spacing:0 !important;
            table-layout:fixed !important;
            margin:0 !important;
            padding:0 !important;
            border-left:1px solid #000000 !important;
            border-right:1px solid #000000 !important;
            border-bottom:1px solid #000000 !important;
            background:#FFFFFF !important;
            font-family:Arial,sans-serif !important;
            display:table !important;
        ">

            <tbody style="
                display:table-row-group !important;
            ">


                <!-- =====================================
                     DATOS CLIENTE
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td colspan="2"
                        style="
                            display:table-cell !important;
                            width:100% !important;
                            background:#F2F2F2 !important;
                            color:{color} !important;
                            text-align:center !important;
                            font-family:Arial,sans-serif !important;
                            font-size:21px !important;
                            font-weight:700 !important;
                            padding:5px !important;
                            border:1px solid #000000 !important;
                            box-sizing:border-box !important;
                        ">

                        Datos del Cliente

                    </td>

                </tr>


                <!-- =====================================
                     OPERADOR
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td style="
                        display:table-cell !important;
                        width:33% !important;
                        background:#FFF1E0 !important;
                        color:#000000 !important;
                        text-align:center !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:700 !important;
                        padding:7px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        Operador:

                    </td>

                    <td style="
                        display:table-cell !important;
                        width:67% !important;
                        background:#FFFFFF !important;
                        color:#000000 !important;
                        text-align:left !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:400 !important;
                        padding:7px 10px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        {operador}

                    </td>

                </tr>


                <!-- =====================================
                     NOMBRE SERVICIO
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td style="
                        display:table-cell !important;
                        width:33% !important;
                        background:#FFF1E0 !important;
                        color:#000000 !important;
                        text-align:center !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:700 !important;
                        padding:7px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        Nombre del servicio:

                    </td>

                    <td style="
                        display:table-cell !important;
                        width:67% !important;
                        background:#FFFFFF !important;
                        color:#000000 !important;
                        text-align:left !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:400 !important;
                        padding:7px 10px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        {nombre_servicio}

                    </td>

                </tr>


                <!-- =====================================
                     DIRECCION / CIUDAD
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td style="
                        display:table-cell !important;
                        width:33% !important;
                        background:#FFF1E0 !important;
                        color:#000000 !important;
                        text-align:center !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:700 !important;
                        padding:7px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        Dirección/Ciudad:

                    </td>

                    <td style="
                        display:table-cell !important;
                        width:67% !important;
                        background:#FFFFFF !important;
                        color:#000000 !important;
                        text-align:left !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:400 !important;
                        padding:7px 10px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        {ciudad}
                        ({lat_text}, {lon_text})

                    </td>

                </tr>


                <!-- =====================================
                     PRESUPUESTOS
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td colspan="2"
                        style="
                            display:table-cell !important;
                            width:100% !important;
                            background:#F2F2F2 !important;
                            color:{color} !important;
                            text-align:center !important;
                            font-family:Arial,sans-serif !important;
                            font-size:21px !important;
                            font-weight:700 !important;
                            padding:5px !important;
                            border:1px solid #000000 !important;
                            box-sizing:border-box !important;
                        ">

                        Presupuestos y Condiciones

                    </td>

                </tr>


                <!-- =====================================
                     MRC
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td style="
                        display:table-cell !important;
                        width:33% !important;
                        background:#FFF1E0 !important;
                        color:#000000 !important;
                        text-align:center !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:700 !important;
                        padding:7px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        MRC (Recurrente mensual)

                    </td>

                    <td style="
                        display:table-cell !important;
                        width:67% !important;
                        background:#FFFFFF !important;
                        color:#000000 !important;
                        text-align:left !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:400 !important;
                        padding:7px 10px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        {mrc_text}

                    </td>

                </tr>


                <!-- =====================================
                     NRC
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td style="
                        display:table-cell !important;
                        width:33% !important;
                        background:#FFF1E0 !important;
                        color:#000000 !important;
                        text-align:center !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:700 !important;
                        padding:7px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        NRC (No recurrente)

                    </td>

                    <td style="
                        display:table-cell !important;
                        width:67% !important;
                        background:#FFFFFF !important;
                        color:#000000 !important;
                        text-align:left !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:400 !important;
                        padding:7px 10px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        {nrc_text}

                    </td>

                </tr>


                <!-- =====================================
                     TIEMPO CONTRATACION
                     ===================================== -->

                <tr style="
                    display:table-row !important;
                ">

                    <td style="
                        display:table-cell !important;
                        width:33% !important;
                        background:#FFF1E0 !important;
                        color:#000000 !important;
                        text-align:center !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:700 !important;
                        padding:7px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        Tiempo Contratación (Meses)

                    </td>

                    <td style="
                        display:table-cell !important;
                        width:67% !important;
                        background:#FFFFFF !important;
                        color:#000000 !important;
                        text-align:left !important;
                        vertical-align:middle !important;
                        font-family:Arial,sans-serif !important;
                        font-size:18px !important;
                        font-weight:400 !important;
                        padding:7px 10px !important;
                        border:1px solid #000000 !important;
                        box-sizing:border-box !important;
                    ">

                        {term_text}

                    </td>

                </tr>


            </tbody>

        </table>

    </div>
    """

    st.markdown(
        html_block,
        unsafe_allow_html=True
    )


# =========================================================
# MOSTRAR REGISTRO HISTÓRICO
# =========================================================

def render_historical_record(record):

    if not isinstance(record, dict):
        return

    fact_id = record.get(
        "id",
        ""
    )

    tipo = record.get(
        "tipo",
        record.get(
            "estado",
            "POSITIVA"
        )
    )

    cliente = record.get(
        "datos_cliente",
        {}
    )

    presupuesto = record.get(
        "presupuestos",
        {}
    )

    oportunidades = record.get(
        "oportunidades",
        []
    )

    # -----------------------------------------------------
    # COMPATIBILIDAD CON REGISTROS ANTIGUOS
    # -----------------------------------------------------

    if not isinstance(cliente, dict):
        cliente = {}

    if not isinstance(presupuesto, dict):
        presupuesto = {}

    if not isinstance(oportunidades, list):
        oportunidades = []

    tipo = str(
        tipo
    ).upper()

    # -----------------------------------------------------
    # INFORMACIÓN HISTÓRICA
    # -----------------------------------------------------

    st.markdown(
        f"""
        <div style="
            background:#F2F2F2;
            border:1px solid #000000;
            padding:10px 15px;
            margin-top:15px;
            margin-bottom:15px;
            font-family:Arial,sans-serif;
        ">

            <span style="
                color:#FF7A00;
                font-size:22px;
                font-weight:700;
            ">
                Factibilidad {safe_html(fact_id)}
            </span>

            <span style="
                margin-left:20px;
                font-size:16px;
                font-weight:600;
                color:#333333;
            ">
                {safe_html(tipo)}
            </span>

            <span style="
                float:right;
                font-size:14px;
                color:#666666;
            ">
                {safe_html(record.get("fecha", ""))}
            </span>

        </div>
        """,
        unsafe_allow_html=True
    )

    # =====================================================
    # POSITIVA
    # =====================================================

    if tipo == "POSITIVA":

        render_feasibility_response(

            titulo="RESPUESTA DE FACTIBILIDAD",

            operador=cliente.get(
                "operador",
                ""
            ),

            nombre_servicio=cliente.get(
                "nombre_servicio",
                ""
            ),

            ciudad=cliente.get(
                "ciudad",
                ""
            ),

            lat=cliente.get(
                "lat",
                0
            ),

            lon=cliente.get(
                "lon",
                0
            ),

            mrc=presupuesto.get(
                "mrc",
                0
            ),

            nrc=presupuesto.get(
                "nrc",
                0
            ),

            term=presupuesto.get(
                "term",
                0
            ),

            factibilidad_id=fact_id
        )

    # =====================================================
    # NEGATIVA
    # =====================================================

    else:

        if not oportunidades:

            # Registro antiguo que no tenía oportunidades.
            render_feasibility_response(

                titulo="RESPUESTA DE FACTIBILIDAD",

                operador=cliente.get(
                    "operador",
                    ""
                ),

                nombre_servicio=cliente.get(
                    "nombre_servicio",
                    ""
                ),

                ciudad=cliente.get(
                    "ciudad",
                    ""
                ),

                lat=cliente.get(
                    "lat",
                    0
                ),

                lon=cliente.get(
                    "lon",
                    0
                ),

                mrc=presupuesto.get(
                    "mrc",
                    0
                ),

                nrc=presupuesto.get(
                    "nrc",
                    0
                ),

                term=presupuesto.get(
                    "term",
                    0
                ),

                factibilidad_id=fact_id
            )

        else:

            for op in oportunidades:

                render_feasibility_response(

                    titulo=(
                        "RESPUESTA DE FACTIBILIDAD - "
                        f"OPORTUNIDAD "
                        f"{op.get('oportunidad', '')}"
                    ),

                    operador=cliente.get(
                        "operador",
                        ""
                    ),

                    nombre_servicio=cliente.get(
                        "nombre_servicio",
                        ""
                    ),

                    ciudad=cliente.get(
                        "ciudad",
                        ""
                    ),

                    lat=cliente.get(
                        "lat",
                        0
                    ),

                    lon=cliente.get(
                        "lon",
                        0
                    ),

                    mrc=op.get(
                        "mrc",
                        0
                    ),

                    nrc=op.get(
                        "nrc",
                        0
                    ),

                    term=op.get(
                        "term",
                        0
                    ),

                    factibilidad_id=fact_id
                )


# =========================================================
# DATA GEO
# =========================================================

@st.cache_data
def load_data():

    geojson_path = (
        ROOT
        / "frontend"
        / "test.json"
    )

    if not geojson_path.exists():

        geojson_path = (
            ROOT
            / "test.json"
        )

    with open(
        geojson_path,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    return [
        shape(
            feature["geometry"]
        )
        for feature
        in data["features"]
    ]


geometries = load_data()


# =========================================================
# ENGINE
# =========================================================

@st.cache_resource
def build_engine():

    engine = H3GeoEngine(
        resolution=9
    )

    engine.build(
        geometries
    )

    return engine


engine = build_engine()


# =========================================================
# MENU
# =========================================================

section_options = [
    "Cotización",
    "Factibilidad",
    "Historial"
]

if st.session_state.section not in section_options:

    st.session_state.section = "Cotización"

section = st.sidebar.radio(
    "Menú",
    section_options,
    index=section_options.index(
        st.session_state.section
    )
)

st.session_state.section = section


# =========================================================
# COTIZACIÓN
# =========================================================

if section == "Cotización":

    st.header(
        "📍 Cotización"
    )

    location_input = st.text_input(
        "📍 Dirección o coordenadas"
    )

    mrc_cliente = st.number_input(
        "💰 MRC",
        value=0,
        step=100000
    )

    if st.button(
        "Analizar cotización"
    ):

        result = resolve_input(
            location_input
        )

        if result is None:

            st.error(
                "No se pudo encontrar ubicación."
            )

            st.stop()

        lat = float(
            result["lat"]
        )

        lon = float(
            result["lon"]
        )

        ciudad = extract_city(
            result
        )

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

            geometry = geometries[idx]

            centroid = geometry.centroid

            distance = haversine(
                lon,
                lat,
                centroid.x,
                centroid.y
            )

            density = density_map[h]

            presence_bonus = (
                1
                if density > 3
                else 0
            )

            score = capex_score(
                distance,
                density,
                presence_bonus
            )

            if score > best_score:

                best_score = score

                best_point = (
                    centroid.x,
                    centroid.y
                )

        # -------------------------------------------------
        # DISTANCIA MÁXIMA
        # -------------------------------------------------

        if best_point is not None:

            best_distance = haversine(

                lon,
                lat,

                best_point[0],
                best_point[1]
            )

            MAX_DISTANCE = 5000

            if best_distance > MAX_DISTANCE:

                best_point = None

        st.session_state.analysis = {

            "lat":
                lat,

            "lon":
                lon,

            "best_point":
                best_point,

            "score":
                best_score,

            "mrc":
                int(mrc_cliente),

            "ciudad":
                ciudad,

            "valor_unitario":
                valor_unitario,

            "negative_site":
                best_point is None
        }

        st.session_state.draw_geojson = None

        st.session_state.factibilidad_resultado = None

        st.session_state.factibilidad_id = None

        st.success(
            f"Ciudad detectada: "
            f"{ciudad.title()}"
        )

        st.success(
            f"Valor unitario: "
            f"${valor_unitario:,.2f} COP/m"
        )

    # =====================================================
    # RESULTADO COTIZACIÓN
    # =====================================================

    if st.session_state.analysis:

        data = (
            st.session_state.analysis
        )

        lat = data["lat"]

        lon = data["lon"]

        best_point = data[
            "best_point"
        ]

        st.metric(
            "CAPEX SCORE",
            f"{data['score']:.4f}"
        )

        # -------------------------------------------------
        # POSITIVA
        # -------------------------------------------------

        if not data.get(
            "negative_site",
            False
        ):

            st.markdown(
                """
                <div style="
                    background-color:#ECFDF5;
                    border:1px solid #10B981;
                    border-radius:10px;
                    padding:20px;
                    margin:15px 0 20px 0;
                    color:#111827;
                ">

                    <h3 style="
                        color:#047857;
                        margin-top:0;
                    ">
                        🟢 COBERTURA POSITIVA
                    </h3>

                    <p style="
                        line-height:1.6;
                    ">
                        Confirmamos cobertura POSITIVA para las sedes en adjunto, sujeta a viabilidad en sitio y a los permisos de uso de infraestructura de terceros, de ser aplicable.
                    </p>

                    <p style="
                        font-weight:700;
                    ">
                        Términos y Condiciones:
                    </p>

                    <p style="
                        line-height:1.7;
                    ">
                        Tarifas antes de IVA.<br>
                        Medio. Fibra Óptica.<br>
                        Costo Obras de infraestructura interna: A determinar en estudio de sitio.<br>
                        No incluye espacio para colocación de equipos del CLIENTE en racks de Liberty Networks, ni otros no relacionados.<br>
                        No incluye costo de colocación ni cross-conexiones, ni otros no relacionados.<br>
                        Aplica cláusula de permanencia del tiempo de contratado y/o Prorrogado.<br>
                        Sujetos a viabilidad en sitio y permisos del operador de infraestructura en caso de aplicar.<br>
                        Tiempo de instalación: 30 días (sujeto a visita de factibilidad y permisos de infraestructura).<br>
                        Vigencia de la oferta, 60 días.<br>
                        Servicio lineal, SLA 99,6%.<br>
                        Tarifa para un servicio en capa 2.<br>
                        Las tarifas antes mencionadas no aplican para el Aeropuerto de Bogotá ni para ningún otro aeropuerto.<br>
                        No se incluye instalación de CPE.<br>
                        Tarifas en pesos colombianos.<br>
                        Tarifas aplican para contrataciones nuevas.
                    </p>

                    <p style="
                        margin-top:18px;
                        padding-top:12px;
                        border-top:1px solid #A7F3D0;
                    ">
                        <strong>NOTA:</strong>
                        Recordar que son 3 conceptos que se facturan:
                        Obras + Conexión + Mensualidad
                    </p>

                </div>
                """,
                unsafe_allow_html=True
            )

        # -------------------------------------------------
        # NEGATIVA
        # -------------------------------------------------

        else:

            st.error(
                "🔴 SITIO NEGATIVO\n\n"
                "No se encontró infraestructura "
                "cercana al cliente."
            )

        # =================================================
        # MAPA
        # =================================================

        m = folium.Map(

            location=[
                lat,
                lon
            ],

            zoom_start=13,

            tiles="CartoDB positron"
        )

        folium.Marker(

            [
                lat,
                lon
            ],

            tooltip="CLIENTE",

            icon=folium.Icon(
                color="red"
            )

        ).add_to(m)

        if (
            best_point
            and not data.get(
                "negative_site",
                False
            )
        ):

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

                "circlemarker": False
            },

            edit_options={

                "edit": True,

                "remove": True
            }
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
            and "all_drawings"
            in output
        ):

            drawings = output[
                "all_drawings"
            ]

            if drawings:

                last = drawings[-1]

                if (
                    last.get(
                        "geometry",
                        {}
                    ).get(
                        "type"
                    )
                    ==
                    "LineString"
                ):

                    st.session_state.draw_geojson = (
                        last[
                            "geometry"
                        ][
                            "coordinates"
                        ]
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

                lon2, lat2 = pts[
                    i + 1
                ]

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

        # -------------------------------------------------
        # IR A FACTIBILIDAD
        # -------------------------------------------------

        if st.button(
            "Evaluar Factibilidad"
        ):

            st.session_state.section = (
                "Factibilidad"
            )

            st.rerun()


# =========================================================
# FACTIBILIDAD
# =========================================================

elif section == "Factibilidad":

    st.header(
        "💰 Factibilidad"
    )

    if not st.session_state.analysis:

        st.warning(
            "Primero genera una cotización."
        )

        st.stop()

    data = (
        st.session_state.analysis
    )

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

            lon2, lat2 = pts[
                i + 1
            ]

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

    costo_obra = int(
        total_distance
        * valor_unitario
    )

    # =====================================================
    # INFORMACIÓN
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
    # CLIENTE
    # =====================================================

    operador = st.text_input(
        "Operador",
        key="fact_operador"
    )

    nombre_servicio = st.text_input(
        "Nombre del servicio",
        key="fact_nombre_servicio"
    )

    # =====================================================
    # MRC
    # =====================================================

    mrc = st.number_input(

        "MRC",

        value=int(
            data["mrc"]
        ),

        step=100000,

        disabled=True,

        key="fact_mrc"
    )

    # =====================================================
    # NRC
    # =====================================================

    nrc = st.number_input(

        "NRC",

        value=0,

        step=100000,

        min_value=0,

        key="fact_nrc"
    )

    # =====================================================
    # TERM
    # =====================================================

    term = st.selectbox(

        "Term (meses)",

        options=[
            12,
            24,
            36
        ],

        index=1,

        key="fact_term"
    )

    # =====================================================
    # COSTO OBRAS
    # =====================================================

    st.number_input(

        "Costo de Obras",

        value=float(
            costo_obra
        ),

        disabled=True,

        key="fact_costo_obra"
    )

    # =====================================================
    # EVALUAR
    # =====================================================

    if st.button(
        "Evaluar factibilidad",
        key="evaluar_factibilidad"
    ):

        mrc_int = int(mrc)

        nrc_int = int(nrc)

        term_int = int(term)

        costo_obra_int = int(
            costo_obra
        )

        feasible = evaluate_positive(

            costo_obra_int,

            nrc_int,

            mrc_int,

            term_int
        )

        payback = (

            (
                costo_obra_int
                - nrc_int
            )
            / mrc_int

        ) if mrc_int > 0 else 999999

        # =================================================
        # POSITIVA
        # =================================================

        if feasible:

            st.session_state.factibilidad_resultado = {

                "tipo":
                    "POSITIVA",

                "operador":
                    operador,

                "nombre_servicio":
                    nombre_servicio,

                "mrc":
                    mrc_int,

                "nrc":
                    nrc_int,

                "term":
                    term_int,

                "payback":
                    payback,

                "costo_obra":
                    costo_obra_int,

                "distancia":
                    total_distance
            }

        # =================================================
        # NEGATIVA
        # =================================================

        else:

            ops = generate_negative_options(

                costo_obra_int,

                mrc_int,

                term_int
            )

            st.session_state.factibilidad_resultado = {

                "tipo":
                    "NEGATIVA",

                "operador":
                    operador,

                "nombre_servicio":
                    nombre_servicio,

                "mrc":
                    mrc_int,

                "nrc":
                    nrc_int,

                "term":
                    term_int,

                "payback":
                    payback,

                "costo_obra":
                    costo_obra_int,

                "distancia":
                    total_distance,

                "oportunidades":
                    ops
            }

        st.session_state.factibilidad_id = None

        st.rerun()

    # =====================================================
    # MOSTRAR RESULTADO
    # =====================================================

    resultado = (
        st.session_state.factibilidad_resultado
    )

    if resultado:

        tipo = resultado.get(
            "tipo",
            "POSITIVA"
        )

        # =================================================
        # POSITIVA
        # =================================================

        if tipo == "POSITIVA":

            st.success(
                "🟢 FACTIBILIDAD POSITIVA"
            )

            render_feasibility_response(

                titulo="RESPUESTA DE FACTIBILIDAD",

                operador=resultado.get(
                    "operador",
                    ""
                ),

                nombre_servicio=resultado.get(
                    "nombre_servicio",
                    ""
                ),

                ciudad=data.get(
                    "ciudad",
                    ""
                ),

                lat=data.get(
                    "lat",
                    0
                ),

                lon=data.get(
                    "lon",
                    0
                ),

                mrc=resultado.get(
                    "mrc",
                    0
                ),

                nrc=resultado.get(
                    "nrc",
                    0
                ),

                term=resultado.get(
                    "term",
                    0
                ),

                factibilidad_id=(
                    st.session_state.factibilidad_id
                )
            )

        # =================================================
        # NEGATIVA
        # =================================================

        else:

            st.error(
                "🔴 FACTIBILIDAD NEGATIVA"
            )

            ops = resultado.get(
                "oportunidades",
                []
            )

            for op in ops:

                render_feasibility_response(

                    titulo=(
                        "RESPUESTA DE FACTIBILIDAD - "
                        f"OPORTUNIDAD "
                        f"{op.get('oportunidad', '')}"
                    ),

                    operador=resultado.get(
                        "operador",
                        ""
                    ),

                    nombre_servicio=resultado.get(
                        "nombre_servicio",
                        ""
                    ),

                    ciudad=data.get(
                        "ciudad",
                        ""
                    ),

                    lat=data.get(
                        "lat",
                        0
                    ),

                    lon=data.get(
                        "lon",
                        0
                    ),

                    mrc=op.get(
                        "mrc",
                        0
                    ),

                    nrc=op.get(
                        "nrc",
                        0
                    ),

                    term=op.get(
                        "term",
                        0
                    ),

                    factibilidad_id=(
                        st.session_state.factibilidad_id
                    )
                )

        # =================================================
        # GUARDAR
        # =================================================

        if st.session_state.factibilidad_id:

            st.success(
                f"✅ Factibilidad guardada correctamente "
                f"con ID "
                f"{st.session_state.factibilidad_id}"
            )

        else:

            st.markdown(
                """
                <div style="
                    margin-top:20px;
                    margin-bottom:10px;
                    padding:12px 15px;
                    background:#FFF7ED;
                    border:1px solid #FF7A00;
                    border-radius:8px;
                    color:#000000;
                    font-family:Arial,sans-serif;
                ">
                    <strong>
                        La factibilidad todavía no ha sido enviada.
                    </strong>
                    <br>
                    Presiona el botón para guardarla en el historial.
                </div>
                """,
                unsafe_allow_html=True
            )

            if st.button(
                "📨 Enviar y guardar factibilidad",
                type="primary",
                key="guardar_factibilidad"
            ):

                # -----------------------------------------
                # CONSTRUIR REGISTRO
                # -----------------------------------------

                record = {

                    "tipo":
                        tipo,

                    "estado":
                        tipo,

                    "datos_cliente": {

                        "operador":
                            resultado.get(
                                "operador",
                                ""
                            ),

                        "nombre_servicio":
                            resultado.get(
                                "nombre_servicio",
                                ""
                            ),

                        "ciudad":
                            data.get(
                                "ciudad",
                                ""
                            ),

                        "lat":
                            data.get(
                                "lat",
                                0
                            ),

                        "lon":
                            data.get(
                                "lon",
                                0
                            )
                    },

                    "presupuestos": {

                        "mrc":
                            resultado.get(
                                "mrc",
                                0
                            ),

                        "nrc":
                            resultado.get(
                                "nrc",
                                0
                            ),

                        "term":
                            resultado.get(
                                "term",
                                0
                            ),

                        "costo_obra":
                            resultado.get(
                                "costo_obra",
                                0
                            ),

                        "distancia":
                            resultado.get(
                                "distancia",
                                0
                            ),

                        "payback":
                            resultado.get(
                                "payback",
                                0
                            )
                    },

                    "oportunidades":
                        resultado.get(
                            "oportunidades",
                            []
                        )
                }

                fact_id, created = (
                    register_factibilidad(
                        record
                    )
                )

                st.session_state.factibilidad_id = (
                    fact_id
                )

                if created:

                    st.success(
                        f"✅ Factibilidad enviada "
                        f"y guardada correctamente: "
                        f"{fact_id}"
                    )

                else:

                    st.warning(
                        f"⚠️ Esta factibilidad "
                        f"ya estaba registrada "
                        f"con el ID: "
                        f"{fact_id}"
                    )

                st.rerun()


# =========================================================
# HISTORIAL
# =========================================================

elif section == "Historial":

    st.header(
        "📚 Historial de Factibilidades"
    )

    history = load_history()

    records = history.get(
        "factibilidades",
        []
    )

    # =====================================================
    # SIN REGISTROS
    # =====================================================

    if not records:

        st.info(
            "Todavía no existen "
            "factibilidades guardadas."
        )

        st.stop()

    # =====================================================
    # TOTAL
    # =====================================================

    st.markdown(
        f"""
        <div style="
            background:#F2F2F2;
            border:1px solid #000000;
            padding:15px;
            margin-bottom:20px;
            font-family:Arial,sans-serif;
        ">

            <span style="
                color:#FF7A00;
                font-size:22px;
                font-weight:700;
            ">
                Total de factibilidades:
            </span>

            <span style="
                font-size:22px;
                font-weight:700;
                margin-left:10px;
            ">
                {len(records)}
            </span>

        </div>
        """,
        unsafe_allow_html=True
    )

    # =====================================================
    # SELECCIONAR FACTIBILIDAD
    # =====================================================

    history_options = []

    record_by_option = {}

    for item in reversed(records):

        item_id = item.get(
            "id",
            ""
        )

        cliente = item.get(
            "datos_cliente",
            {}
        )

        if not isinstance(cliente, dict):
            cliente = {}

        servicio = cliente.get(
            "nombre_servicio",
            ""
        )

        fecha = item.get(
            "fecha",
            ""
        )

        tipo = item.get(
            "tipo",
            item.get(
                "estado",
                ""
            )
        )

        option = (
            f"{item_id} | "
            f"{servicio} | "
            f"{tipo} | "
            f"{fecha}"
        )

        history_options.append(
            option
        )

        record_by_option[
            option
        ] = item

    # -----------------------------------------------------
    # SELECCIÓN
    # -----------------------------------------------------

    default_index = 0

    if (
        st.session_state.historial_seleccionado
        in history_options
    ):

        default_index = (
            history_options.index(
                st.session_state.historial_seleccionado
            )
        )

    selected = st.selectbox(

        "Selecciona una factibilidad",

        options=history_options,

        index=default_index,

        key="historial_selector"
    )

    st.session_state.historial_seleccionado = selected

    selected_record = record_by_option.get(
        selected
    )

    # =====================================================
    # MOSTRAR FACTIBILIDAD COMPLETA
    # =====================================================

    if selected_record:

        render_historical_record(
            selected_record
        )

    # =====================================================
    # TABLA RESUMEN
    # =====================================================

    st.markdown(
        """
        <div style="
            margin-top:35px;
            margin-bottom:10px;
            color:#FF7A00;
            font-size:22px;
            font-weight:700;
        ">
            Registros guardados
        </div>
        """,
        unsafe_allow_html=True
    )

    summary_rows = []

    for record in reversed(records):

        cliente = record.get(
            "datos_cliente",
            {}
        )

        if not isinstance(cliente, dict):
            cliente = {}

        summary_rows.append({

            "ID":
                record.get(
                    "id",
                    ""
                ),

            "Fecha":
                record.get(
                    "fecha",
                    ""
                ),

            "Estado":
                record.get(
                    "tipo",
                    record.get(
                        "estado",
                        ""
                    )
                ),

            "Operador":
                cliente.get(
                    "operador",
                    ""
                ),

            "Servicio":
                cliente.get(
                    "nombre_servicio",
                    ""
                ),

            "Ciudad":
                str(
                    cliente.get(
                        "ciudad",
                        ""
                    )
                ).title()
        })

    st.dataframe(
        pd.DataFrame(
            summary_rows
        ),
        width="stretch",
        hide_index=True
    )