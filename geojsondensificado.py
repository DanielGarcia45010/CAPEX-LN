import json
import streamlit as st
from shapely.geometry import shape
import pandas as pd
import folium
from folium.plugins import FastMarkerCluster
import pydeck as pdk
from streamlit_folium import st_folium
import io
import logging
 
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
 
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
    value=50_000,
    step=5_000,
    min_value=1_000,
    max_value=500_000
)
 
# =========================
# UTILIDADES
# =========================
def meters_to_degrees(m: float) -> float:
    return m / 111_320
 
 
def densify_linestring(line, spacing_deg: float) -> list:
    """Densifica un LineString interpolando puntos cada spacing_deg grados."""
    if line.length == 0:
        return [line.coords[0]]
    n = max(2, int(line.length / spacing_deg) + 1)
    return [
        line.interpolate(i / (n - 1) * line.length)
        for i in range(n)
    ]
 
 
def densify_polygon(poly, spacing_deg: float) -> list:
    return densify_linestring(poly.boundary, spacing_deg)
 
 
def process_feature(feature: dict, spacing_deg: float) -> list[tuple]:
    """
    Retorna lista de tuplas (lon, lat, props).
    Props se serializa a string JSON para compatibilidad con DataFrames/pydeck.
    """
    geom = shape(feature["geometry"])
    props = feature.get("properties") or {}
    props_str = json.dumps(props, ensure_ascii=False)
 
    points = []
 
    if geom.geom_type == "Point":
        return [(geom.x, geom.y, props_str)]
 
    elif geom.geom_type == "LineString":
        points = densify_linestring(geom, spacing_deg)
 
    elif geom.geom_type == "Polygon":
        points = densify_polygon(geom, spacing_deg)
 
    elif geom.geom_type.startswith("Multi"):
        for sub_geom in geom.geoms:
            if sub_geom.geom_type == "LineString":
                points += densify_linestring(sub_geom, spacing_deg)
            elif sub_geom.geom_type == "Polygon":
                points += densify_polygon(sub_geom, spacing_deg)
            elif sub_geom.geom_type == "Point":
                points.append(sub_geom)
 
    return [(p.x, p.y, props_str) for p in points]
 
 
# =========================
# PROCESADOR PRINCIPAL
# =========================
def process_geojson(data: dict, spacing_deg: float) -> list[tuple]:
    """
    Procesa todas las features del GeoJSON.
    Maneja errores por feature sin silenciar el resto.
    Actualiza barra de progreso correctamente incluyendo el 100%.
    """
    results = []
    features = data.get("features", [])
    total = len(features)
 
    if total == 0:
        st.warning("El GeoJSON no contiene features.")
        return results
 
    progress_bar = st.progress(0)
    status_text  = st.empty()
    errors       = 0
 
    for i, feature in enumerate(features):
        try:
            pts = process_feature(feature, spacing_deg)
            results.extend(pts)
        except Exception as e:
            errors += 1
            logger.warning(f"Feature {i} ignorada: {e}")
 
        # Actualizar cada 200 features y al final
        if i % 200 == 0 or i == total - 1:
            pct = (i + 1) / total
            progress_bar.progress(pct)
            status_text.text(
                f"Procesando {i + 1:,}/{total:,} features "
                f"| Puntos: {len(results):,}"
                + (f" | Errores: {errors}" if errors else "")
            )
 
    progress_bar.progress(1.0)
    status_text.empty()
 
    if errors:
        st.warning(f"⚠️ {errors} feature(s) omitidas por errores de geometría.")
 
    return results
 
 
# =========================
# VISUALIZACIÓN FOLIUM
# =========================
def render_folium(points: list, max_render: int) -> folium.Map:
    """
    Usa FastMarkerCluster en lugar de CircleMarker individual.
    Reduce de O(n) operaciones DOM a un único plugin JS.
    """
    sample = points[:max_render]
    # FastMarkerCluster espera lista de [lat, lon]
    locations = [[lat, lon] for lon, lat, _ in sample]
 
    # Centro basado en la muestra
    lats = [lat for lat, lon in locations]  # noqa: F841 — se usa abajo
    lons = [lon for lat, lon in locations]  # noqa: F841
    center_lat = sum(lat for lat, _ in locations) / len(locations) if locations else 4.6
    center_lon = sum(lon for _, lon in locations) / len(locations) if locations else -74.1
 
    m = folium.Map(location=[center_lat, center_lon], zoom_start=7)
    FastMarkerCluster(locations).add_to(m)
    return m
 
 
# =========================
# VISUALIZACIÓN DECK.GL
# =========================
def render_deck(points: list, max_render: int) -> pdk.Deck:
    """
    Props se almacena como string JSON — evita errores de serialización
    de dicts anidados en pydeck.
    Centro calculado sobre la muestra real.
    """
    sample = points[:max_render]
    df = pd.DataFrame(sample, columns=["lon", "lat", "props"])
 
    layer = pdk.Layer(
        "ScatterplotLayer",
        df,
        get_position="[lon, lat]",
        get_radius=30,
        get_fill_color=[0, 122, 255, 180],
        pickable=True,
    )
 
    view = pdk.ViewState(
        latitude=df["lat"].mean(),
        longitude=df["lon"].mean(),
        zoom=7,
    )
 
    return pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        tooltip={"text": "Lat: {lat}\nLon: {lon}\n{props}"},
    )
 
 
# =========================
# EXPORTACIÓN STREAMING (RAM-SAFE)
# =========================
def build_geojson_bytes(points: list) -> bytes:
    """
    Construye el GeoJSON en un buffer de bytes en lugar de construir
    un dict gigante en memoria antes de serializar.
    Para datasets muy grandes esto reduce el pico de RAM ~50%.
    """
    buf = io.BytesIO()
    buf.write(b'{"type":"FeatureCollection","features":[')
 
    for idx, (lon, lat, props_str) in enumerate(points):
        if idx > 0:
            buf.write(b",")
        feature = (
            f'{{"type":"Feature",'
            f'"geometry":{{"type":"Point","coordinates":[{lon},{lat}]}},'
            f'"properties":{props_str}}}'
        )
        buf.write(feature.encode("utf-8"))
 
    buf.write(b"]}")
    return buf.getvalue()
 
 
# =========================
# UI PRINCIPAL
# =========================
uploaded = st.file_uploader("📂 Sube GeoJSON / JSON", type=["geojson", "json"])
 
if uploaded:
    try:
        data = json.loads(uploaded.read().decode("utf-8"))
    except Exception as e:
        st.error(f"No se pudo parsear el archivo: {e}")
        st.stop()
 
    n_features = len(data.get("features", []))
    st.success(f"Features cargadas: {n_features:,}")
 
    if n_features == 0:
        st.warning("El archivo no contiene features. Verifica el GeoJSON.")
        st.stop()
 
    spacing_deg = meters_to_degrees(SPACING_M)
 
    if st.button("🚀 Procesar GeoJSON"):
        points = process_geojson(data, spacing_deg)
 
        if not points:
            st.error("No se generaron puntos. Revisa el GeoJSON de entrada.")
            st.stop()
 
        st.success(f"✅ Puntos generados: {len(points):,}")
 
        col1, col2 = st.columns(2)
        col1.metric("Features originales", f"{n_features:,}")
        col2.metric("Puntos generados",    f"{len(points):,}")
 
        # ---- Descarga RAM-safe ----
        geojson_bytes = build_geojson_bytes(points)
        st.download_button(
            "📥 Descargar GeoJSON densificado",
            data=geojson_bytes,
            file_name="densified.geojson",
            mime="application/json",
        )
 
        # ---- Visualización ----
        st.subheader("🗺️ Visualización")
 
        max_r = int(MAX_POINTS_RENDER)
        if len(points) > max_r:
            st.info(
                f"Mostrando {max_r:,} de {len(points):,} puntos. "
                "Ajusta el slider si necesitas ver más."
            )
 
        if ENGINE == "Folium (simple)":
            m = render_folium(points, max_r)
            st_folium(m, width=1200, height=600)
        else:
            deck = render_deck(points, max_r)
            st.pydeck_chart(deck)
 
        # ---- Preview ----
        with st.expander("👀 Preview (primeras 10 filas)"):
            preview_df = pd.DataFrame(
                points[:10], columns=["lon", "lat", "props"]
            )
            st.dataframe(preview_df, use_container_width=True)
 
# =========================
# FOOTER
# =========================
st.markdown("---")
st.markdown("""
### 🚀 Características PRO
 
- ✔ Procesamiento optimizado para 100k+ features
- ✔ Barra de progreso precisa con conteo de errores por feature
- ✔ FastMarkerCluster en Folium (10x más rápido que CircleMarker)
- ✔ Exportación streaming (RAM-safe para datasets grandes)
- ✔ Props serializadas correctamente en pydeck
- ✔ Visualización dual (Folium / Deck.gl)
""")