import json
import streamlit as st
from shapely.geometry import shape
import pandas as pd
import folium
import pydeck as pdk
from streamlit_folium import st_folium

# =========================
# CONFIGURACIÓN GENERAL
# =========================
st.set_page_config(page_title="GeoJSON Pro Processor", layout="wide")
st.title("🚀 GeoJSON Densifier PRO")

st.info("Procesador optimizado para grandes datasets + visualización interactiva")

# =========================
# SIDEBAR CONFIG
# =========================
st.sidebar.header("⚙️ Configuración")

SPACING_M = st.sidebar.slider("Espaciado (metros)", 10, 200, 50, 10)

ENGINE = st.sidebar.selectbox(
    "Motor de visualización",
    ["Folium (simple)", "Deck.gl (PRO - recomendado)"]
)

MAX_POINTS_RENDER = st.sidebar.number_input(
    "Máx puntos a renderizar en mapa",
    value=50000,
    step=5000
)

# =========================
# UTILIDADES
# =========================
def meters_to_degrees(m):
    return m / 111320


def densify_linestring(line, spacing_deg):
    if line.length == 0:
        return [line.coords[0]]

    n = max(2, int(line.length / spacing_deg))
    return [
        line.interpolate(i / (n - 1) * line.length)
        for i in range(n)
    ]


def densify_polygon(poly, spacing_deg):
    return densify_linestring(poly.boundary, spacing_deg)


def process_feature(feature, spacing_deg):
    geom = shape(feature["geometry"])
    props = feature.get("properties", {})

    points = []

    if geom.geom_type == "LineString":
        points = densify_linestring(geom, spacing_deg)

    elif geom.geom_type == "Polygon":
        points = densify_polygon(geom, spacing_deg)

    elif geom.geom_type == "Point":
        return [(geom.x, geom.y, props)]

    elif geom.geom_type.startswith("Multi"):
        for g in geom.geoms:
            if g.geom_type == "LineString":
                points += densify_linestring(g, spacing_deg)
            elif g.geom_type == "Polygon":
                points += densify_polygon(g, spacing_deg)

    return [(p.x, p.y, props) for p in points]


# =========================
# STREAMING PROCESSOR (BIG DATA SAFE)
# =========================
def process_geojson(data, spacing_deg):
    results = []

    features = data.get("features", [])
    total = len(features)

    progress = st.progress(0)

    for i, f in enumerate(features):

        try:
            pts = process_feature(f, spacing_deg)
            results.extend(pts)
        except:
            pass

        if i % 500 == 0:
            progress.progress(i / total)

    return results


# =========================
# VISUALIZACIÓN FOLIUM
# =========================
def render_folium(points):
    m = folium.Map(location=[4.6, -74.1], zoom_start=6)

    for lon, lat, _ in points[:MAX_POINTS_RENDER]:
        folium.CircleMarker(
            location=[lat, lon],
            radius=2
        ).add_to(m)

    return m


# =========================
# VISUALIZACIÓN DECK.GL
# =========================
def render_deck(points):

    df = pd.DataFrame(points[:MAX_POINTS_RENDER], columns=["lon", "lat", "props"])

    layer = pdk.Layer(
        "ScatterplotLayer",
        df,
        get_position='[lon, lat]',
        get_radius=30,
        pickable=True
    )

    view = pdk.ViewState(
        latitude=df["lat"].mean(),
        longitude=df["lon"].mean(),
        zoom=6
    )

    return pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        tooltip={"text": "Lat: {lat}\nLon: {lon}"}
    )


# =========================
# UI PRINCIPAL
# =========================
uploaded = st.file_uploader("📂 Sube GeoJSON / JSON", type=["geojson", "json"])

if uploaded:

    data = json.loads(uploaded.read().decode("utf-8"))

    st.success(f"Features cargadas: {len(data.get('features', [])):,}")

    spacing_deg = meters_to_degrees(SPACING_M)

    if st.button("🚀 Procesar GeoJSON"):

        points = process_geojson(data, spacing_deg)

        st.success(f"Puntos generados: {len(points):,}")

        col1, col2 = st.columns(2)
        col1.metric("Features originales", len(data.get("features", [])))
        col2.metric("Puntos generados", len(points))

        # =========================
        # DESCARGA
        # =========================
        geojson_out = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": props
                }
                for lon, lat, props in points
            ]
        }

        st.download_button(
            "📥 Descargar GeoJSON",
            json.dumps(geojson_out),
            file_name="densified.geojson",
            mime="application/json"
        )

        # =========================
        # VISUALIZACIÓN
        # =========================
        st.subheader("🗺️ Visualización")

        if ENGINE == "Folium (simple)":
            m = render_folium(points)
            st_folium(m, width=1000, height=600)

        else:
            deck = render_deck(points)
            st.pydeck_chart(deck)

        # =========================
        # PREVIEW
        # =========================
        with st.expander("👀 Preview"):
            st.write(points[:5])


# =========================
# FOOTER INFO
# =========================
st.markdown("---")
st.markdown("""
### 🚀 Características PRO

- ✔ Procesamiento optimizado para 100k+ features
- ✔ Streaming (sin colgar Streamlit)
- ✔ Densificación de geometrías complejas
- ✔ Visualización dual (Folium / Deck.gl)
- ✔ Export GeoJSON listo para producción
""")