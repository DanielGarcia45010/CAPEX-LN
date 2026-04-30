import json
import streamlit as st
import pandas as pd
import pydeck as pdk
from shapely.geometry import shape

st.set_page_config(page_title="GeoJSON Pro Densifier", layout="wide")
st.title("🚀 GeoJSON Densifier PRO v2")

# ---------------- CONFIG ----------------
st.sidebar.header("⚙️ Configuración")

SPACING = st.sidebar.slider("Espaciado (aprox grados)", 0.0001, 0.01, 0.001, 0.0001)
MAX_RENDER = st.sidebar.number_input("Máx puntos en mapa", 1000, 200000, 50000, 1000)

ENGINE = st.sidebar.selectbox(
    "Motor visualización",
    ["PyDeck (recomendado)", "Solo tabla"]
)

# ---------------- DENSIFICADOR REAL ----------------
def densify(geom, step):

    if geom.geom_type == "Point":
        yield geom.x, geom.y

    elif geom.geom_type == "LineString":

        length = geom.length
        n = max(2, int(length / step))

        for i in range(n):
            p = geom.interpolate(i / (n - 1) * length)
            yield p.x, p.y

    elif geom.geom_type == "Polygon":
        yield from densify(geom.boundary, step)

    elif geom.geom_type.startswith("Multi"):
        for g in geom.geoms:
            yield from densify(g, step)


# ---------------- LOAD ----------------
file = st.file_uploader("Sube GeoJSON", type=["geojson", "json"])

if file:

    data = json.loads(file.read())

    points = []
    features = data.get("features", [])

    progress = st.progress(0)
    status = st.empty()

    total = len(features)

    for i, f in enumerate(features):

        try:
            geom = shape(f["geometry"])

            for p in densify(geom, SPACING):
                points.append(p)

        except:
            continue

        if i % 50 == 0:
            progress.progress((i + 1) / total)
            status.text(f"Procesando {i+1}/{total} | puntos: {len(points)}")

    progress.progress(1.0)
    status.empty()

    st.success(f"Total puntos generados: {len(points):,}")

    # ---------------- LIMITAR PARA RENDIMIENTO ----------------
    render_points = points[:MAX_RENDER]

    df = pd.DataFrame(render_points, columns=["lon", "lat"])

    st.write(df.head())

    # ---------------- MAPA ----------------
    if ENGINE == "PyDeck (recomendado)":

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[lon, lat]",
            get_radius=15,
            pickable=True
        )

        view = pdk.ViewState(
            latitude=df["lat"].mean(),
            longitude=df["lon"].mean(),
            zoom=8
        )

        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view))

    else:
        st.dataframe(df)