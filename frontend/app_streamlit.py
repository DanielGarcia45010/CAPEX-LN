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

    possible_paths = [
        ROOT / "frontend" / "styles.css",
        ROOT / "styles.css"
    ]

    for css_path in possible_paths:

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

            break


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

DEFAULT_SESSION = {

    "analysis": None,

    "draw_geojson": None,

    "section": "Cotización",

    "factibilidad_resultado": None,

    "factibilidad_id": None,

    "historial_seleccionado": None
}


for key, value in DEFAULT_SESSION.items():

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

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                initial_data,
                f,
                ensure_ascii=False,
                indent=4
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
# OBTENER SERIAL DE ID
# =========================================================

def extract_serial(fact_id):

    if not fact_id:

        return 0

    match = re.search(
        r"CO(\d+)",
        str(fact_id).upper()
    )

    if match:

        try:

            return int(
                match.group(1)
            )

        except Exception:

            return 0

    return 0


# =========================================================
# NORMALIZAR REGISTRO HISTÓRICO
# =========================================================

def normalize_history_record(record):

    if not isinstance(record, dict):

        return None

    # -----------------------------------------------------
    # Copia para no modificar el objeto original
    # -----------------------------------------------------

    record = dict(record)

    # -----------------------------------------------------
    # ID
    # -----------------------------------------------------

    if not record.get("id"):

        record["id"] = ""

    # -----------------------------------------------------
    # Tipo / Estado
    #
    # Versiones anteriores podían tener solamente:
    # tipo
    #
    # Versiones nuevas tienen:
    # tipo + estado
    # -----------------------------------------------------

    tipo = str(
        record.get(
            "tipo",
            record.get(
                "estado",
                "POSITIVA"
            )
        )
    ).upper()

    if tipo not in [
        "POSITIVA",
        "NEGATIVA"
    ]:

        tipo = "POSITIVA"

    record["tipo"] = tipo

    record["estado"] = tipo

    # -----------------------------------------------------
    # Datos cliente
    # -----------------------------------------------------

    cliente = record.get(
        "datos_cliente",
        {}
    )

    if not isinstance(cliente, dict):

        cliente = {}

    # Compatibilidad con registros antiguos
    if not cliente.get("operador"):

        cliente["operador"] = record.get(
            "operador",
            ""
        )

    if not cliente.get("nombre_servicio"):

        cliente["nombre_servicio"] = record.get(
            "nombre_servicio",
            ""
        )

    if not cliente.get("ciudad"):

        cliente["ciudad"] = record.get(
            "ciudad",
            ""
        )

    if cliente.get("lat") is None:

        cliente["lat"] = record.get(
            "lat",
            0
        )

    if cliente.get("lon") is None:

        cliente["lon"] = record.get(
            "lon",
            0
        )

    record["datos_cliente"] = cliente

    # -----------------------------------------------------
    # Presupuestos
    # -----------------------------------------------------

    presupuesto = record.get(
        "presupuestos",
        {}
    )

    if not isinstance(presupuesto, dict):

        presupuesto = {}

    # Compatibilidad con registros antiguos

    if presupuesto.get("mrc") is None:

        presupuesto["mrc"] = record.get(
            "mrc",
            0
        )

    if presupuesto.get("nrc") is None:

        presupuesto["nrc"] = record.get(
            "nrc",
            0
        )

    if presupuesto.get("term") is None:

        presupuesto["term"] = record.get(
            "term",
            0
        )

    if presupuesto.get("costo_obra") is None:

        presupuesto["costo_obra"] = record.get(
            "costo_obra",
            0
        )

    if presupuesto.get("distancia") is None:

        presupuesto["distancia"] = record.get(
            "distancia",
            0
        )

    if presupuesto.get("payback") is None:

        presupuesto["payback"] = record.get(
            "payback",
            0
        )

    record["presupuestos"] = presupuesto

    # -----------------------------------------------------
    # Oportunidades
    # -----------------------------------------------------

    oportunidades = record.get(
        "oportunidades",
        []
    )

    if not isinstance(
        oportunidades,
        list
    ):

        oportunidades = []

    record["oportunidades"] = oportunidades

    # -----------------------------------------------------
    # Fecha
    # -----------------------------------------------------

    if not record.get("fecha"):

        record["fecha"] = ""

    return record


# =========================================================
# FIRMA ÚNICA
# =========================================================

def build_factibility_fingerprint(record):

    cliente = record.get(
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
            cliente.get(
                "operador",
                ""
            ),

        "nombre_servicio":
            cliente.get(
                "nombre_servicio",
                ""
            ),

        "ciudad":
            cliente.get(
                "ciudad",
                ""
            ),

        "lat":
            cliente.get(
                "lat",
                0
            ),

        "lon":
            cliente.get(
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
# GUARDAR JSON
# =========================================================

def save_history(data):

    temp_file = HISTORY_FILE.with_suffix(
        ".tmp"
    )

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

    temp_file.replace(
        HISTORY_FILE
    )


# =========================================================
# CARGAR HISTORIAL
# =========================================================

def load_history():

    initialize_history_file()

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            raw_data = json.load(f)

    except Exception:

        raw_data = {
            "ultimo_serial": 0,
            "factibilidades": []
        }

    # -----------------------------------------------------
    # Compatibilidad con JSON que era directamente una lista
    # -----------------------------------------------------

    if isinstance(raw_data, list):

        records = raw_data

    elif isinstance(raw_data, dict):

        records = raw_data.get(
            "factibilidades",
            []
        )

    else:

        records = []

    normalized_records = []

    max_serial = 0

    for record in records:

        normalized = normalize_history_record(
            record
        )

        if normalized is None:

            continue

        normalized_records.append(
            normalized
        )

        max_serial = max(
            max_serial,
            extract_serial(
                normalized.get("id")
            )
        )

    # -----------------------------------------------------
    # Serial guardado
    # -----------------------------------------------------

    if isinstance(raw_data, dict):

        saved_serial = extract_serial(
            raw_data.get(
                "ultimo_serial",
                0
            )
        )

    else:

        saved_serial = 0

    ultimo_serial = max(
        saved_serial,
        max_serial
    )

    data = {

        "ultimo_serial":
            ultimo_serial,

        "factibilidades":
            normalized_records
    }

    # -----------------------------------------------------
    # Actualizar fingerprints faltantes
    # -----------------------------------------------------

    changed = False

    for record in data["factibilidades"]:

        if not record.get("fingerprint"):

            record["fingerprint"] = (
                build_factibility_fingerprint(
                    record
                )
            )

            changed = True

    # -----------------------------------------------------
    # Guardar migración si hubo cambios
    # -----------------------------------------------------

    if (
        not isinstance(raw_data, dict)
        or changed
        or saved_serial != ultimo_serial
    ):

        save_history(data)

    return data


# =========================================================
# GENERAR ID
# =========================================================

def get_next_factibilidad_id():

    history = load_history()

    max_existing = max(
        [
            extract_serial(
                item.get("id")
            )
            for item
            in history.get(
                "factibilidades",
                []
            )
        ]
        or [0]
    )

    current_serial = max(
        int(
            history.get(
                "ultimo_serial",
                0
            )
        ),
        max_existing
    )

    next_serial = (
        current_serial + 1
    )

    return (
        f"CO{next_serial:06d}",
        next_serial
    )


# =========================================================
# REGISTRAR FACTIBILIDAD
# =========================================================

def register_factibilidad(record):

    history = load_history()

    fingerprint = build_factibility_fingerprint(
        record
    )

    # -----------------------------------------------------
    # EVITAR DUPLICADOS
    # -----------------------------------------------------

    for existing in history["factibilidades"]:

        existing_fingerprint = existing.get(
            "fingerprint"
        )

        # Compatibilidad con registros viejos
        if not existing_fingerprint:

            existing_fingerprint = (
                build_factibility_fingerprint(
                    existing
                )
            )

        if (
            existing_fingerprint
            ==
            fingerprint
        ):

            return (
                existing.get(
                    "id",
                    ""
                ),
                False
            )

    # -----------------------------------------------------
    # GENERAR SIGUIENTE SERIAL
    # -----------------------------------------------------

    _, next_serial = (
        get_next_factibilidad_id()
    )

    fact_id = (
        f"CO{next_serial:06d}"
    )

    record = normalize_history_record(
        record
    )

    record["id"] = fact_id

    record["fingerprint"] = (
        fingerprint
    )

    record["fecha"] = (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    record["estado"] = record.get(
        "tipo",
        "POSITIVA"
    )

    history["ultimo_serial"] = (
        next_serial
    )

    history["factibilidades"].append(
        record
    )

    save_history(
        history
    )

    return (
        fact_id,
        True
    )


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
            costs_df["Ciudad"]
            == "bogota"
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
        *
        R
        *
        math.atan2(
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

    if term <= 0:

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
# GENERAR 3 OPORTUNIDADES
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

    term1 = max(
        1,
        int(term_entrada)
    )

    mrc1 = math.ceil(
        (2 * costo)
        / term1
    )

    if mrc1 <= mrc_entrada:

        mrc1 = (
            mrc_entrada + 1
        )

    payback1 = (
        costo / mrc1
        if mrc1 > 0
        else 0
    )

    opportunities.append({

        "oportunidad": 1,

        "term": term1,

        "mrc": int(mrc1),

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

    term2 = max(
        1,
        int(term_entrada * 1.5)
    )

    mrc2 = int(
        mrc1 * 0.75
    )

    if mrc2 <= 0:

        mrc2 = 1

    if mrc2 >= mrc1:

        mrc2 = max(
            1,
            mrc1 - 1
        )

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
        (
            costo
            - nrc2
        )
        / mrc2
        if mrc2 > 0
        else 0
    )

    opportunities.append({

        "oportunidad": 2,

        "term": term2,

        "mrc": int(mrc2),

        "nrc": int(nrc2),

        "paybackMeses":
            round(
                payback2,
                2
            )
    })

    # -----------------------------------------------------
    # OPCIÓN 3
    # -----------------------------------------------------

    term3 = max(
        1,
        int(term_entrada * 2)
    )

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
        (
            costo
            - nrc3
        )
        / mrc3
        if mrc3 > 0
        else 0
    )

    opportunities.append({

        "oportunidad": 3,

        "term": term3,

        "mrc": int(mrc3),

        "nrc": int(nrc3),

        "paybackMeses":
            round(
                payback3,
                2
            )
    })

    return opportunities


# =========================================================
# ESCAPAR HTML
# =========================================================

def safe_html(value):

    if value is None:

        return ""

    return html.escape(
        str(value)
    )


# =========================================================
# TABLA PRINCIPAL DE FACTIBILIDAD
#
# TODO EL CUADRO ES UNA SOLA TABLA HTML.
#
# Esto evita que Streamlit interprete <tr>/<td>
# como texto o elementos independientes.
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

    st.markdown(
        f"""
        <div class="capex-feasibility-wrapper"
             style="
                width:100%;
                margin-top:15px;
                margin-bottom:25px;
                font-family:Arial,sans-serif;
             ">

            <table
                class="capex-feasibility-table"
                style="
                    width:100%;
                    border-collapse:collapse;
                    border-spacing:0;
                    table-layout:fixed;
                    background:#FFFFFF;
                    margin:0;
                    padding:0;
                    color:#000000;
                    font-family:Arial,sans-serif;
                "
            >

                <!-- ===================================== -->
                <!-- TITULO + ID                           -->
                <!-- ===================================== -->

                <tr>

                    <td
                        style="
                            width:calc(100% - 145px);
                            background:{color};
                            color:#FFFFFF;
                            text-align:center;
                            vertical-align:middle;
                            font-size:23px;
                            font-weight:700;
                            padding:7px 10px;
                            border:1px solid #000000;
                            height:44px;
                            box-sizing:border-box;
                        "
                    >
                        {titulo}
                    </td>

                    <td
                        style="
                            width:145px;
                            min-width:145px;
                            background:#000000;
                            color:#FFFFFF;
                            text-align:center;
                            vertical-align:middle;
                            font-size:21px;
                            font-weight:700;
                            padding:7px 12px;
                            border:1px solid #000000;
                            white-space:nowrap;
                            box-sizing:border-box;
                        "
                    >
                        {fact_id}
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- DATOS CLIENTE                         -->
                <!-- ===================================== -->

                <tr>

                    <td
                        colspan="2"
                        style="
                            background:#F2F2F2;
                            color:{color};
                            text-align:center;
                            font-size:21px;
                            font-weight:700;
                            padding:5px;
                            border:1px solid #000000;
                        "
                    >
                        Datos del Cliente
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- OPERADOR                              -->
                <!-- ===================================== -->

                <tr>

                    <td
                        style="
                            width:33%;
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:18px;
                            font-weight:700;
                            padding:7px;
                            border:1px solid #000000;
                        "
                    >
                        Operador:
                    </td>

                    <td
                        style="
                            width:67%;
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:18px;
                            padding:7px 10px;
                            border:1px solid #000000;
                        "
                    >
                        {operador}
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- NOMBRE SERVICIO                       -->
                <!-- ===================================== -->

                <tr>

                    <td
                        style="
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:18px;
                            font-weight:700;
                            padding:7px;
                            border:1px solid #000000;
                        "
                    >
                        Nombre del servicio:
                    </td>

                    <td
                        style="
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:18px;
                            padding:7px 10px;
                            border:1px solid #000000;
                        "
                    >
                        {nombre_servicio}
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- DIRECCION / CIUDAD                    -->
                <!-- ===================================== -->

                <tr>

                    <td
                        style="
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:18px;
                            font-weight:700;
                            padding:7px;
                            border:1px solid #000000;
                        "
                    >
                        Dirección/Ciudad:
                    </td>

                    <td
                        style="
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:18px;
                            padding:7px 10px;
                            border:1px solid #000000;
                        "
                    >
                        {ciudad}
                        ({lat_text}, {lon_text})
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- PRESUPUESTOS                          -->
                <!-- ===================================== -->

                <tr>

                    <td
                        colspan="2"
                        style="
                            background:#F2F2F2;
                            color:{color};
                            text-align:center;
                            font-size:21px;
                            font-weight:700;
                            padding:5px;
                            border:1px solid #000000;
                        "
                    >
                        Presupuestos y Condiciones
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- MRC                                   -->
                <!-- ===================================== -->

                <tr>

                    <td
                        style="
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:18px;
                            font-weight:700;
                            padding:7px;
                            border:1px solid #000000;
                        "
                    >
                        MRC (Recurrente mensual)
                    </td>

                    <td
                        style="
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:18px;
                            padding:7px 10px;
                            border:1px solid #000000;
                        "
                    >
                        {mrc_text}
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- NRC                                   -->
                <!-- ===================================== -->

                <tr>

                    <td
                        style="
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:18px;
                            font-weight:700;
                            padding:7px;
                            border:1px solid #000000;
                        "
                    >
                        NRC (No recurrente)
                    </td>

                    <td
                        style="
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:18px;
                            padding:7px 10px;
                            border:1px solid #000000;
                        "
                    >
                        {nrc_text}
                    </td>

                </tr>


                <!-- ===================================== -->
                <!-- TIEMPO CONTRATACION                   -->
                <!-- ===================================== -->

                <tr>

                    <td
                        style="
                            background:#FFF1E0;
                            color:#000000;
                            text-align:center;
                            vertical-align:middle;
                            font-size:18px;
                            font-weight:700;
                            padding:7px;
                            border:1px solid #000000;
                        "
                    >
                        Tiempo Contratación (Meses)
                    </td>

                    <td
                        style="
                            background:#FFFFFF;
                            color:#000000;
                            text-align:left;
                            vertical-align:middle;
                            font-size:18px;
                            padding:7px 10px;
                            border:1px solid #000000;
                        "
                    >
                        {term_text}
                    </td>

                </tr>

            </table>

        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# RENDER HISTORIAL
# =========================================================

def render_historical_record(record):

    record = normalize_history_record(
        record
    )

    if record is None:

        st.error(
            "El registro histórico no es válido."
        )

        return

    fact_id = record.get(
        "id",
        ""
    )

    tipo = str(
        record.get(
            "estado",
            record.get(
                "tipo",
                "POSITIVA"
            )
        )
    ).upper()

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
    # ENCABEZADO DEL HISTORIAL
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

    # -----------------------------------------------------
    # POSITIVA
    # -----------------------------------------------------

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

        return

    # -----------------------------------------------------
    # NEGATIVA
    # -----------------------------------------------------

    if not oportunidades:

        st.warning(
            "Esta factibilidad negativa no contiene "
            "oportunidades guardadas."
        )

        return

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

menu_options = [
    "Cotización",
    "Factibilidad",
    "Historial"
]

if (
    st.session_state.section
    not in menu_options
):

    st.session_state.section = (
        "Cotización"
    )

section = st.sidebar.radio(

    "Menú",

    menu_options,

    index=menu_options.index(
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

        density_map = defaultdict(
            int
        )

        for h, idx in candidates:

            density_map[h] += 1

        for h, idx in candidates:

            geometry = geometries[idx]

            centroid = (
                geometry.centroid
            )

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
        # DISTANCIA MAXIMA
        # -------------------------------------------------

        if best_point is not None:

            best_distance = haversine(

                lon,
                lat,

                best_point[0],
                best_point[1]
            )

            MAX_DISTANCE = 5000

            if (
                best_distance
                >
                MAX_DISTANCE
            ):

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
                int(
                    mrc_cliente
                ),

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
    # RESULTADO
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
            and
            "all_drawings"
            in output
        ):

            drawings = (
                output[
                    "all_drawings"
                ]
            )

            if drawings:

                last = drawings[-1]

                if (
                    last["geometry"]["type"]
                    ==
                    "LineString"
                ):

                    st.session_state.draw_geojson = (
                        last[
                            "geometry"
                        ]["coordinates"]
                    )

        # -------------------------------------------------
        # DISTANCIA
        # -------------------------------------------------

        total = 0

        if (
            st.session_state.draw_geojson
            and
            len(
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
        # FACTIBILIDAD
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
        and
        len(
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
        *
        valor_unitario
    )

    # =====================================================
    # INFORMACION
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

    st.write(
        f"🏗️ Valor Obras: "
        f"${costo_obra:,.0f} COP"
    )

    # =====================================================
    # CLIENTE
    # =====================================================

    operador = st.text_input(
        "Operador"
    )

    nombre_servicio = st.text_input(
        "Nombre del servicio"
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

        disabled=True
    )

    # =====================================================
    # NRC
    # =====================================================

    nrc = st.number_input(

        "NRC",

        value=0,

        min_value=0,

        step=100000
    )

    # =====================================================
    # TERM
    #
    # Se permite cualquier cantidad de meses.
    # =====================================================

    term = st.number_input(

        "Tiempo Contratación (Meses)",

        min_value=1,

        value=12,

        step=1
    )

    # =====================================================
    # COSTO OBRAS
    # =====================================================

    st.number_input(

        "Costo de Obras",

        value=float(
            costo_obra
        ),

        disabled=True
    )

    # =====================================================
    # EVALUAR
    # =====================================================

    if st.button(
        "Evaluar factibilidad"
    ):

        mrc = int(
            mrc
        )

        nrc = int(
            nrc
        )

        term = int(
            term
        )

        costo_obra = int(
            costo_obra
        )

        feasible = evaluate_positive(

            costo_obra,

            nrc,

            mrc,

            term
        )

        payback = (

            (
                costo_obra
                -
                nrc
            )
            /
            mrc

        ) if mrc > 0 else 999999

        # =================================================
        # POSITIVA
        # =================================================

        if feasible:

            st.session_state.factibilidad_resultado = {

                "tipo":
                    "POSITIVA",

                "estado":
                    "POSITIVA",

                "operador":
                    operador,

                "nombre_servicio":
                    nombre_servicio,

                "mrc":
                    mrc,

                "nrc":
                    nrc,

                "term":
                    term,

                "payback":
                    payback,

                "costo_obra":
                    costo_obra,

                "distancia":
                    total_distance
            }

            st.session_state.factibilidad_id = None

            st.rerun()

        # =================================================
        # NEGATIVA
        # =================================================

        else:

            ops = (
                generate_negative_options(

                    costo_obra,

                    mrc,

                    term
                )
            )

            st.session_state.factibilidad_resultado = {

                "tipo":
                    "NEGATIVA",

                "estado":
                    "NEGATIVA",

                "operador":
                    operador,

                "nombre_servicio":
                    nombre_servicio,

                "mrc":
                    mrc,

                "nrc":
                    nrc,

                "term":
                    term,

                "payback":
                    payback,

                "costo_obra":
                    costo_obra,

                "distancia":
                    total_distance,

                "oportunidades":
                    ops
            }

            st.session_state.factibilidad_id = None

            st.rerun()

    # =====================================================
    # RESULTADO
    # =====================================================

    resultado = (
        st.session_state.factibilidad_resultado
    )

    if resultado:

        tipo = str(
            resultado.get(
                "estado",
                resultado.get(
                    "tipo",
                    "POSITIVA"
                )
            )
        ).upper()

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
                f"Factibilidad guardada correctamente "
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
                type="primary"
            ):

                # -----------------------------------------
                # REGISTRO
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
    # RESUMEN
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
    # OPCIONES
    # =====================================================

    history_options = []

    record_by_option = {}

    for item in reversed(records):

        item = normalize_history_record(
            item
        )

        item_id = item.get(
            "id",
            ""
        )

        cliente = item.get(
            "datos_cliente",
            {}
        )

        servicio = cliente.get(
            "nombre_servicio",
            ""
        )

        fecha = item.get(
            "fecha",
            ""
        )

        option = (
            f"{item_id} | "
            f"{servicio} | "
            f"{fecha}"
        )

        history_options.append(
            option
        )

        record_by_option[
            option
        ] = item

    # =====================================================
    # SELECCION
    # =====================================================

    selected = st.selectbox(

        "Selecciona una factibilidad",

        options=history_options,

        key="historial_selector"
    )

    selected_record = (
        record_by_option.get(
            selected
        )
    )

    # =====================================================
    # MOSTRAR COMPLETO
    # =====================================================

    if selected_record:

        render_historical_record(
            selected_record
        )

    # =====================================================
    # RESUMEN
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

        record = normalize_history_record(
            record
        )

        cliente = record.get(
            "datos_cliente",
            {}
        )

        resumen_estado = record.get(
            "estado",
            record.get(
                "tipo",
                ""
            )
        )

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
                resumen_estado,

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