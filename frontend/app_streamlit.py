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
import textwrap
import os

from datetime import datetime, timezone
from shapely.geometry import shape
from collections import defaultdict
from streamlit_folium import st_folium
from folium.plugins import Draw

from supabase import create_client, Client

from core.geo_engine_h3 import H3GeoEngine
from core.capex_scoring import capex_score
from utils.geocoder import resolve_input

# =========================================================
# SUPABASE
# =========================================================

SUPABASE_URL = st.secrets[
    "SUPABASE_URL"
]

SUPABASE_KEY = st.secrets[
    "SUPABASE_KEY"
]

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# =========================================================
# CONFIGURACIÓN
# =========================================================

st.set_page_config(
    page_title="CAPEX ENGINE",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =========================================================
# SUPABASE
# =========================================================

@st.cache_resource
def get_supabase() -> Client:

    supabase_url = st.secrets.get(
        "SUPABASE_URL",
        ""
    )

    supabase_key = st.secrets.get(
        "SUPABASE_KEY",
        ""
    )

    if not supabase_url:
        raise RuntimeError(
            "No se encontró SUPABASE_URL en "
            "Streamlit Secrets."
        )

    if not supabase_key:
        raise RuntimeError(
            "No se encontró SUPABASE_KEY en "
            "Streamlit Secrets."
        )

    return create_client(
        supabase_url,
        supabase_key
    )


try:

    supabase = get_supabase()

except Exception as e:

    st.error(
        "Error conectando con Supabase."
    )

    st.exception(e)

    st.stop()


# =========================================================
# RUTAS
# =========================================================

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


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
# CSS DE SEGURIDAD PARA LA INTERFAZ
# =========================================================

st.markdown(
    """
<style>

    .stApp {
        background-color: #FFFFFF;
    }

    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    h1, h2, h3, h4, h5, h6 {
        color: #1F2937 !important;
    }

    div[data-testid="stTextInput"] label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stRadio"] label {
        color: #1F2937 !important;
        font-weight: 600 !important;
    }

    div[data-testid="stTextInput"] label p,
    div[data-testid="stNumberInput"] label p,
    div[data-testid="stSelectbox"] label p,
    div[data-testid="stRadio"] label p {
        color: #1F2937 !important;
    }

    div[data-baseweb="input"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 8px !important;
    }

    div[data-baseweb="input"] input {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }

    div[data-baseweb="input"] input::placeholder {
        color: #6B7280 !important;
        opacity: 1 !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        border: 1px solid #D1D5DB !important;
    }

    div[data-baseweb="select"] span {
        color: #111827 !important;
    }

    .stButton > button {
        color: #FFFFFF !important;
        background-color: #FF7A00 !important;
        border: 1px solid #FF7A00 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        min-height: 42px !important;
    }

    .stButton > button:hover {
        background-color: #E96D00 !important;
        border-color: #E96D00 !important;
    }

    div[data-testid="stMetric"] {
        background-color: #F8FAFC !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 10px !important;
        padding: 12px !important;
    }

    div[data-testid="stMetricLabel"] {
        color: #374151 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #111827 !important;
    }

    div[data-testid="stDataFrame"] {
        color: #111827 !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
    }

    section[data-testid="stSidebar"] * {
        color: #1F2937;
    }

    div[data-testid="stAlert"] p {
        color: inherit !important;
    }

</style>
""",
    unsafe_allow_html=True
)


# =========================================================
# FUNCIÓN CENTRAL PARA HTML
# =========================================================

def render_html(content):

    if content is None:
        return

    clean_content = textwrap.dedent(
        str(content)
    ).strip()

    if not clean_content:
        return

    st.html(
        clean_content
    )


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


# =========================================================
# CABECERA
# =========================================================

render_html(
    """
    <div style="
        width:100%;
        margin:0 0 25px 0;
        padding:0;
        font-family:Arial,sans-serif;
    ">

        <h1 style="
            margin:0;
            color:#1F2937;
            font-size:38px;
            font-weight:800;
            line-height:1.2;
        ">
            CAPEX ENGINE
        </h1>

        <p style="
            color:#6B7280;
            margin:5px 0 0 0;
            font-size:16px;
        ">
            Liberty Networks · Plataforma de evaluación CAPEX
        </p>

    </div>
    """
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
# HISTORIAL - SUPABASE
# =========================================================

def load_history():

    try:

        response = (
            supabase
            .table("factibilidades")
            .select("*")
            .order(
                "serial",
                desc=False
            )
            .execute()
        )

        rows = response.data or []

        factibilidades = []

        max_serial = 0

        for row in rows:

            try:

                serial = int(
                    row.get(
                        "serial",
                        0
                    )
                )

            except Exception:

                serial = 0

            max_serial = max(
                max_serial,
                serial
            )

            datos_cliente = row.get(
                "datos_cliente",
                {}
            )

            presupuestos = row.get(
                "presupuestos",
                {}
            )

            oportunidades = row.get(
                "oportunidades",
                []
            )

            if not isinstance(
                datos_cliente,
                dict
            ):

                datos_cliente = {}

            if not isinstance(
                presupuestos,
                dict
            ):

                presupuestos = {}

            if not isinstance(
                oportunidades,
                list
            ):

                oportunidades = []

            fecha = row.get(
                "fecha",
                ""
            )

            if fecha:

                try:

                    fecha_dt = datetime.fromisoformat(
                        str(fecha).replace(
                            "Z",
                            "+00:00"
                        )
                    )

                    fecha = fecha_dt.astimezone(
                        timezone.utc
                    ).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                except Exception:

                    fecha = str(fecha)

            record = {

                "id":
                    row.get(
                        "factibilidad_id",
                        ""
                    ),

                "serial":
                    serial,

                "fingerprint":
                    row.get(
                        "fingerprint",
                        ""
                    ),

                "fecha":
                    fecha,

                "tipo":
                    row.get(
                        "tipo",
                        ""
                    ),

                "estado":
                    row.get(
                        "estado",
                        row.get(
                            "tipo",
                            ""
                        )
                    ),

                "datos_cliente":
                    datos_cliente,

                "presupuestos":
                    presupuestos,

                "oportunidades":
                    oportunidades
            }

            factibilidades.append(
                record
            )

        return {

            "ultimo_serial":
                max_serial,

            "factibilidades":
                factibilidades
        }

    except Exception as e:

        st.error(
            "No fue posible cargar el historial desde Supabase."
        )

        st.exception(e)

        return {

            "ultimo_serial": 0,

            "factibilidades": []
        }


# =========================================================
# GENERAR ID
# =========================================================

def get_next_factibilidad_id():

    history = load_history()

    next_serial = (
        int(
            history.get(
                "ultimo_serial",
                0
            )
        )
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
# REGISTRAR FACTIBILIDAD EN SUPABASE
# =========================================================

def register_factibilidad(record):

    try:

        # -------------------------------------------------
        # 1. Crear fingerprint
        # -------------------------------------------------

        fingerprint = build_factibilidad_fingerprint(
            record
        )

        # -------------------------------------------------
        # 2. Verificar si ya existe
        # -------------------------------------------------

        existing_response = (
            supabase
            .table("factibilidades")
            .select("id")
            .eq("fingerprint", fingerprint)
            .limit(1)
            .execute()
        )

        existing_rows = (
            existing_response.data
            if existing_response.data
            else []
        )

        if existing_rows:

            existing_id = existing_rows[0].get(
                "id"
            )

            return (
                existing_id,
                False
            )

        # -------------------------------------------------
        # 3. Obtener siguiente serial
        # -------------------------------------------------

        serial_response = (
            supabase
            .table("factibilidades")
            .select("serial")
            .order(
                "serial",
                desc=True
            )
            .limit(1)
            .execute()
        )

        serial_rows = (
            serial_response.data
            if serial_response.data
            else []
        )

        if serial_rows:

            last_serial = int(
                serial_rows[0].get(
                    "serial",
                    0
                )
            )

        else:

            last_serial = 0

        next_serial = (
            last_serial + 1
        )

        # -------------------------------------------------
        # 4. Generar ID
        # -------------------------------------------------

        fact_id = (
            f"CO{next_serial:06d}"
        )

        # -------------------------------------------------
        # 5. Preparar registro
        # -------------------------------------------------

        tipo = str(
            record.get(
                "tipo",
                "NEGATIVA"
            )
        ).upper()

        estado = (
            "POSITIVA"
            if tipo == "POSITIVA"
            else "NEGATIVA"
        )

        datos_cliente = record.get(
            "datos_cliente",
            {}
        )

        presupuestos = record.get(
            "presupuestos",
            {}
        )

        oportunidades = record.get(
            "oportunidades",
            []
        )

        # -------------------------------------------------
        # 6. Insertar en Supabase
        # -------------------------------------------------

        payload = {

            "id":
                fact_id,

            "serial":
                next_serial,

            "fingerprint":
                fingerprint,

            "tipo":
                tipo,

            "estado":
                estado,

            "datos_cliente":
                datos_cliente,

            "presupuestos":
                presupuestos,

            "oportunidades":
                oportunidades
        }

        response = (
            supabase
            .table("factibilidades")
            .insert(payload)
            .execute()
        )

        # -------------------------------------------------
        # 7. Validar respuesta
        # -------------------------------------------------

        inserted_rows = (
            response.data
            if response.data
            else []
        )

        if not inserted_rows:

            raise Exception(
                "Supabase no devolvió "
                "el registro insertado."
            )

        return (
            fact_id,
            True
        )

    except Exception as e:

        st.error(
            "No se pudo guardar la factibilidad."
        )

        st.exception(e)

        return (
            None,
            False
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

    if not costs_path.exists():

        raise FileNotFoundError(
            "No se encontró costs.xlsx "
            "en data/ ni en la raíz del proyecto."
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
            "Falta columna 'Ciudad' en costs.xlsx"
        )

    if "Valor Unitario" not in df.columns:

        raise ValueError(
            "Falta columna 'Valor Unitario' "
            "en costs.xlsx"
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
        payback <= term / 2
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

    render_html(
        f"""
        <div style="
            width:100%;
            margin:20px 0 30px 0;
            padding:0;
            font-family:Arial,sans-serif;
            box-sizing:border-box;
        ">

            <div style="
                width:100%;
                display:flex;
                align-items:stretch;
                margin:0;
                padding:0;
                box-sizing:border-box;
            ">

                <div style="
                    flex:1;
                    background:{color};
                    color:#FFFFFF;
                    text-align:center;
                    font-size:22px;
                    font-weight:700;
                    padding:10px;
                    border:1px solid #000000;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    box-sizing:border-box;
                    min-height:50px;
                ">
                    {titulo}
                </div>

                <div style="
                    min-width:150px;
                    background:#000000;
                    color:#FFFFFF;
                    text-align:center;
                    font-size:20px;
                    font-weight:700;
                    padding:10px 12px;
                    border-top:1px solid #000000;
                    border-right:1px solid #000000;
                    border-bottom:1px solid #000000;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    white-space:nowrap;
                    box-sizing:border-box;
                    min-height:50px;
                ">
                    {fact_id}
                </div>

            </div>

            <table style="
                width:100%;
                border-collapse:collapse;
                border-spacing:0;
                table-layout:fixed;
                margin:0;
                padding:0;
                border-left:1px solid #000000;
                border-right:1px solid #000000;
                border-bottom:1px solid #000000;
                background:#FFFFFF;
                font-family:Arial,sans-serif;
            ">

                <tbody>

                    <tr>

                        <td colspan="2"
                            style="
                                width:100%;
                                background:#F2F2F2;
                                color:{color};
                                text-align:center;
                                font-size:20px;
                                font-weight:700;
                                padding:8px;
                                border:1px solid #000000;
                            ">
                            Datos del Cliente
                        </td>

                    </tr>

                    <tr>

                        <td style="
                            width:33%;
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:17px;
                            font-weight:700;
                            padding:9px;
                            border:1px solid #000000;
                        ">
                            Operador:
                        </td>

                        <td style="
                            width:67%;
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:17px;
                            padding:9px 12px;
                            border:1px solid #000000;
                        ">
                            {operador}
                        </td>

                    </tr>

                    <tr>

                        <td style="
                            width:33%;
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:17px;
                            font-weight:700;
                            padding:9px;
                            border:1px solid #000000;
                        ">
                            Nombre del servicio:
                        </td>

                        <td style="
                            width:67%;
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:17px;
                            padding:9px 12px;
                            border:1px solid #000000;
                        ">
                            {nombre_servicio}
                        </td>

                    </tr>

                    <tr>

                        <td style="
                            width:33%;
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:17px;
                            font-weight:700;
                            padding:9px;
                            border:1px solid #000000;
                        ">
                            Dirección/Ciudad:
                        </td>

                        <td style="
                            width:67%;
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:17px;
                            padding:9px 12px;
                            border:1px solid #000000;
                        ">
                            {ciudad}
                            ({lat_text}, {lon_text})
                        </td>

                    </tr>

                    <tr>

                        <td colspan="2"
                            style="
                                width:100%;
                                background:#F2F2F2;
                                color:{color};
                                text-align:center;
                                font-size:20px;
                                font-weight:700;
                                padding:8px;
                                border:1px solid #000000;
                            ">
                            Presupuestos y Condiciones
                        </td>

                    </tr>

                    <tr>

                        <td style="
                            width:33%;
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:17px;
                            font-weight:700;
                            padding:9px;
                            border:1px solid #000000;
                        ">
                            MRC (Recurrente mensual)
                        </td>

                        <td style="
                            width:67%;
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:17px;
                            padding:9px 12px;
                            border:1px solid #000000;
                        ">
                            {mrc_text}
                        </td>

                    </tr>

                    <tr>

                        <td style="
                            width:33%;
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:17px;
                            font-weight:700;
                            padding:9px;
                            border:1px solid #000000;
                        ">
                            NRC (No recurrente)
                        </td>

                        <td style="
                            width:67%;
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:17px;
                            padding:9px 12px;
                            border:1px solid #000000;
                        ">
                            {nrc_text}
                        </td>

                    </tr>

                    <tr>

                        <td style="
                            width:33%;
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:17px;
                            font-weight:700;
                            padding:9px;
                            border:1px solid #000000;
                        ">
                            Tiempo Contratación (Meses)
                        </td>

                        <td style="
                            width:67%;
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:17px;
                            padding:9px 12px;
                            border:1px solid #000000;
                        ">
                            {term_text}
                        </td>

                    </tr>

                </tbody>

            </table>

        </div>
        """
    )


# =========================================================
# REGISTRO HISTÓRICO
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

    if not isinstance(
        cliente,
        dict
    ):

        cliente = {}

    if not isinstance(
        presupuesto,
        dict
    ):

        presupuesto = {}

    if not isinstance(
        oportunidades,
        list
    ):

        oportunidades = []

    tipo = str(
        tipo
    ).upper()

    estado_color = (
        "#16A34A"
        if tipo == "POSITIVA"
        else "#DC2626"
    )

    render_html(
        f"""
        <div style="
            background:#F8FAFC;
            border:1px solid #D1D5DB;
            border-radius:8px;
            padding:14px 18px;
            margin:20px 0 15px 0;
            font-family:Arial,sans-serif;
            box-sizing:border-box;
            overflow:hidden;
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
                color:{estado_color};
                font-size:16px;
                font-weight:700;
            ">
                {safe_html(tipo)}
            </span>

            <span style="
                float:right;
                font-size:14px;
                color:#6B7280;
            ">
                {safe_html(record.get("fecha", ""))}
            </span>

        </div>
        """
    )

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

            factibilidad_id=fact_id,

            color="#FF7A00"
        )

    else:

        if not oportunidades:

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

                factibilidad_id=fact_id,

                color="#DC2626"
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

                    factibilidad_id=fact_id,

                    color="#FF7A00"
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

    if not geojson_path.exists():

        raise FileNotFoundError(
            "No se encontró test.json "
            "en frontend/ ni en la raíz."
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

if (
    st.session_state.section
    not in section_options
):

    st.session_state.section = (
        "Cotización"
    )

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

        "📍 Coordenadas",

        placeholder=(
            "Ej: 4.6762,-74.0485, "
        ),

        key="location_input"
    )

    mrc_cliente = st.number_input(

        "💰 MRC",

        min_value=0,

        value=0,

        step=100000,

        format="%d",

        key="mrc_cliente"
    )

    if st.button(
        "🔎 Analizar cotización",
        type="primary",
        key="analizar_cotizacion"
    ):

        if not location_input.strip():

            st.error(
                "Ingresa una dirección o unas coordenadas."
            )

            st.stop()

        if mrc_cliente <= 0:

            st.error(
                "El MRC debe ser mayor que cero."
            )

            st.stop()

        result = resolve_input(
            location_input
        )

        if result is None:

            st.error(
                "No se pudo encontrar la ubicación."
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

        density_map = defaultdict(
            int
        )

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

            "lat": lat,

            "lon": lon,

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


    if st.session_state.analysis:

        data = (
            st.session_state.analysis
        )

        lat = data["lat"]

        lon = data["lon"]

        best_point = data[
            "best_point"
        ]

        if data["score"] >= 0:

            st.metric(
                "CAPEX SCORE",
                f"{data['score']:.4f}"
            )

        else:

            st.metric(
                "CAPEX SCORE",
                "N/A"
            )

        if not data.get(
            "negative_site",
            False
        ):

            render_html(
                """
                <div style="
                    width:100%;
                    background:#ECFDF5;
                    border:1px solid #10B981;
                    border-radius:10px;
                    padding:20px;
                    margin:15px 0 20px 0;
                    color:#111827;
                    font-family:Arial,sans-serif;
                    box-sizing:border-box;
                ">

                    <h3 style="
                        color:#047857;
                        margin:0 0 12px 0;
                        font-size:22px;
                    ">
                        🟢 COBERTURA POSITIVA
                    </h3>

                    <p style="
                        line-height:1.6;
                        margin:8px 0;
                    ">
                        Confirmamos cobertura POSITIVA para las sedes en adjunto, sujeta a viabilidad en sitio y a los permisos de uso de infraestructura de terceros, de ser aplicable.
                    </p>

                    <p style="
                        font-weight:700;
                        margin:16px 0 8px 0;
                    ">
                        Términos y Condiciones:
                    </p>

                    <p style="
                        line-height:1.7;
                        margin:0;
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
                        margin:18px 0 0 0;
                        padding-top:12px;
                        border-top:1px solid #A7F3D0;
                        line-height:1.6;
                    ">
                        <strong>NOTA:</strong>
                        Recordar que son 3 conceptos que se facturan:
                        Obras + Conexión + Mensualidad
                    </p>

                </div>
                """
            )

        else:

            render_html(
                """
                <div style="
                    width:100%;
                    background:#FEF2F2;
                    border:1px solid #EF4444;
                    border-radius:10px;
                    padding:18px;
                    margin:15px 0 20px 0;
                    color:#991B1B;
                    font-family:Arial,sans-serif;
                    box-sizing:border-box;
                ">

                    <div style="
                        font-size:22px;
                        font-weight:700;
                        margin-bottom:8px;
                    ">
                        🔴 SITIO NEGATIVO
                    </div>

                    <div style="
                        color:#7F1D1D;
                        line-height:1.6;
                    ">
                        No se encontró infraestructura cercana al cliente.
                    </div>

                </div>
                """
            )

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

            height=650,

            width=None,

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

                geometry_data = last.get(
                    "geometry",
                    {}
                )

                if (
                    geometry_data.get(
                        "type"
                    )
                    == "LineString"
                ):

                    st.session_state.draw_geojson = (
                        geometry_data.get(
                            "coordinates",
                            []
                        )
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

        st.markdown("")

        if st.button(
            "💰 Evaluar Factibilidad",
            type="primary",
            key="ir_factibilidad"
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

        render_html(
            """
            <div style="
                background:#FFF7ED;
                border:1px solid #FDBA74;
                border-radius:8px;
                padding:15px;
                color:#9A3412;
                font-family:Arial,sans-serif;
            ">
                <strong>Primero genera una cotización.</strong>
            </div>
            """
        )

        st.stop()

    data = (
        st.session_state.analysis
    )

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

    valor_unitario = data[
        "valor_unitario"
    ]

    costo_obra = int(
        total_distance
        * valor_unitario
    )

    render_html(
        f"""
        <div style="
            width:100%;
            background:#F8FAFC;
            border:1px solid #D1D5DB;
            border-radius:10px;
            padding:16px 20px;
            margin:10px 0 25px 0;
            font-family:Arial,sans-serif;
            box-sizing:border-box;
        ">

            <div style="
                display:flex;
                flex-wrap:wrap;
                gap:30px;
            ">

                <div>
                    <span style="
                        color:#6B7280;
                        font-size:14px;
                    ">
                        Ciudad
                    </span>

                    <div style="
                        color:#1F2937;
                        font-size:18px;
                        font-weight:700;
                        margin-top:3px;
                    ">
                        {safe_html(data["ciudad"].title())}
                    </div>
                </div>

                <div>
                    <span style="
                        color:#6B7280;
                        font-size:14px;
                    ">
                        Distancia
                    </span>

                    <div style="
                        color:#1F2937;
                        font-size:18px;
                        font-weight:700;
                        margin-top:3px;
                    ">
                        {total_distance:,.2f} m
                    </div>
                </div>

                <div>
                    <span style="
                        color:#6B7280;
                        font-size:14px;
                    ">
                        Valor unitario
                    </span>

                    <div style="
                        color:#1F2937;
                        font-size:18px;
                        font-weight:700;
                        margin-top:3px;
                    ">
                        ${valor_unitario:,.2f} COP/m
                    </div>
                </div>

                <div>
                    <span style="
                        color:#6B7280;
                        font-size:14px;
                    ">
                        Costo de obras
                    </span>

                    <div style="
                        color:#FF7A00;
                        font-size:18px;
                        font-weight:700;
                        margin-top:3px;
                    ">
                        ${costo_obra:,.0f} COP
                    </div>
                </div>

            </div>

        </div>
        """
    )

    operador = st.text_input(

        "Operador",

        placeholder="Ingrese el operador",

        key="fact_operador"
    )

    nombre_servicio = st.text_input(

        "Nombre del servicio",

        placeholder="Ingrese el nombre del servicio",

        key="fact_nombre_servicio"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        mrc = st.number_input(

            "MRC",

            min_value=0,

            value=int(
                data["mrc"]
            ),

            step=100000,

            format="%d",

            disabled=True,

            key="fact_mrc"
        )

    with col2:

        nrc = st.number_input(

            "NRC",

            min_value=0,

            value=0,

            step=100000,

            format="%d",

            key="fact_nrc"
        )

    with col3:

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

    st.number_input(

        "Costo de Obras",

        min_value=0.0,

        value=float(
            costo_obra
        ),

        disabled=True,

        key="fact_costo_obra"
    )

    if st.button(

        "🔎 Evaluar factibilidad",

        type="primary",

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

    resultado = (
        st.session_state.factibilidad_resultado
    )

    if resultado:

        tipo = resultado.get(
            "tipo",
            "POSITIVA"
        )

        if tipo == "POSITIVA":

            render_html(
                """
                <div style="
                    width:100%;
                    background:#ECFDF5;
                    border:1px solid #10B981;
                    border-radius:10px;
                    padding:15px 20px;
                    margin:25px 0 20px 0;
                    color:#047857;
                    font-family:Arial,sans-serif;
                    font-size:20px;
                    font-weight:700;
                ">
                    🟢 FACTIBILIDAD POSITIVA
                </div>
                """
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
                ),

                color="#FF7A00"
            )

        else:

            render_html(
                """
                <div style="
                    width:100%;
                    background:#FEF2F2;
                    border:1px solid #EF4444;
                    border-radius:10px;
                    padding:15px 20px;
                    margin:25px 0 20px 0;
                    color:#991B1B;
                    font-family:Arial,sans-serif;
                    font-size:20px;
                    font-weight:700;
                ">
                    🔴 FACTIBILIDAD NEGATIVA
                </div>

                <div style="
                    color:#374151;
                    font-family:Arial,sans-serif;
                    margin-bottom:15px;
                    line-height:1.5;
                ">
                    Se presentan las alternativas disponibles
                    para convertir la factibilidad en positiva.
                </div>
                """
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
                    ),

                    color="#FF7A00"
                )

        if st.session_state.factibilidad_id:

            render_html(
                f"""
                <div style="
                    width:100%;
                    background:#ECFDF5;
                    border:1px solid #10B981;
                    border-radius:8px;
                    padding:12px 15px;
                    margin-top:20px;
                    color:#065F46;
                    font-family:Arial,sans-serif;
                    font-weight:700;
                    box-sizing:border-box;
                ">
                    ✅ Factibilidad guardada correctamente
                    con ID
                    {safe_html(st.session_state.factibilidad_id)}
                </div>
                """
            )

        else:

            render_html(
                """
                <div style="
                    width:100%;
                    margin-top:25px;
                    margin-bottom:12px;
                    padding:14px 16px;
                    background:#FFF7ED;
                    border:1px solid #FF7A00;
                    border-radius:8px;
                    color:#7C2D12;
                    font-family:Arial,sans-serif;
                    box-sizing:border-box;
                ">
                    <strong>
                        La factibilidad todavía no ha sido enviada.
                    </strong>

                    <br>

                    Presiona el botón para guardarla en el historial.
                </div>
                """
            )

            if st.button(

                "📨 Enviar y guardar factibilidad",

                type="primary",

                key="guardar_factibilidad"
            ):

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

                if fact_id:

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

                else:

                    st.error(
                        "No se pudo guardar la factibilidad."
                    )


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

    if not records:

        render_html(
            """
            <div style="
                background:#F8FAFC;
                border:1px solid #D1D5DB;
                border-radius:8px;
                padding:18px;
                color:#374151;
                font-family:Arial,sans-serif;
                box-sizing:border-box;
            ">
                Todavía no existen factibilidades guardadas.
            </div>
            """
        )

        st.stop()

    render_html(
        f"""
        <div style="
            width:100%;
            background:#F8FAFC;
            border:1px solid #D1D5DB;
            border-radius:8px;
            padding:15px 18px;
            margin-bottom:20px;
            font-family:Arial,sans-serif;
            box-sizing:border-box;
        ">

            <span style="
                color:#FF7A00;
                font-size:22px;
                font-weight:700;
            ">
                Total de factibilidades:
            </span>

            <span style="
                color:#1F2937;
                font-size:22px;
                font-weight:700;
                margin-left:10px;
            ">
                {len(records)}
            </span>

        </div>
        """
    )

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

        if not isinstance(
            cliente,
            dict
        ):

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

    st.session_state.historial_seleccionado = (
        selected
    )

    selected_record = (
        record_by_option.get(
            selected
        )
    )

    if selected_record:

        render_historical_record(
            selected_record
        )

    render_html(
        """
        <div style="
            margin-top:35px;
            margin-bottom:10px;
            color:#FF7A00;
            font-family:Arial,sans-serif;
            font-size:22px;
            font-weight:700;
        ">
            Registros guardados
        </div>
        """
    )

    summary_rows = []

    for record in reversed(records):

        cliente = record.get(
            "datos_cliente",
            {}
        )

        if not isinstance(
            cliente,
            dict
        ):

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

    df_historial = pd.DataFrame(
        summary_rows
    )

    st.dataframe(

        df_historial,

        use_container_width=True,

        hide_index=True
    )


    # =====================================================
    # DESCARGAR HISTORIAL CSV
    # =====================================================

    csv_historial = df_historial.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig"
    )

    st.download_button(

        label="📥 Descargar historial",

        data=csv_historial,

        file_name="historial_factibilidades.csv",

        mime="text/csv",

        key="descargar_historial_csv"
    )