import streamlit as st
import json
import pydeck as pdk
from shapely.geometry import shape

from geo_engine import GeoEngine

st.set_page_config(layout="wide")
st.title("🚀 CAPEX ENGINE PRO - NETWORK VIEW")

# ---------------- ENGINE ----------------
engine = GeoEngine()

# ---------------- LOAD GEOMETRIES ----------------
@st.cache_data
def load_geometries():
    path = "test.json"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [shape(f["geometry"]) for f in data["features"]]

geometries = load_geometries()

st.success(f"📦 Geometries loaded: {len(geometries):,}")

# ---------------- BUILD INDEX ----------------
if engine.tree is None:
    with st.spinner("⚙️ Building spatial index..."):
        engine.build(geometries)
    st.success("✅ Index ready")

# ---------------- INPUT ----------------
coords = st.text_input("📍 lat,lon", "10.99384,-74.79639")

if coords:

    lat, lon = map(float, coords.split(","))

    results = engine.query(lon, lat)

    st.write("🔎 Candidates:", len(results))

    # ---------------- FIND BEST ----------------
    best = None
    best_d = float("inf")

    for dist, idx in results:

        g = geometries[idx]

        try:
            c = g.centroid

            # distancia simple (rápida)
            d = ((lon - c.x)**2 + (lat - c.y)**2) ** 0.5 * 111320

            if d < best_d:
                best_d = d
                best = (c.x, c.y)

        except:
            continue

    # ---------------- MAP ----------------
    if best:

        st.success(f"🏁 Best distance: {best_d:.0f} m")

        layers = []

        # 🔴 CLIENTE
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": [lon, lat]}],
            get_position="position",
            get_radius=60,
            get_fill_color=[255, 0, 0],
        ))

        # 🟢 RED EXISTENTE (INFRAESTRUCTURA)
        network_points = []

        for g in geometries:

            try:

                if g.geom_type == "Point":
                    network_points.append([g.x, g.y])

                elif g.geom_type in ["LineString", "LinearRing"]:
                    coords_list = list(g.coords)
                    network_points.append(coords_list[0])
                    network_points.append(coords_list[-1])

                elif g.geom_type == "Polygon":
                    c = g.centroid
                    network_points.append([c.x, c.y])

            except:
                continue

        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": p} for p in network_points],
            get_position="position",
            get_radius=25,
            get_fill_color=[0, 200, 0],   # 🟢 VERDE = RED
            pickable=False
        ))

        # 🔵 CONEXIÓN CLIENTE → RED
        layers.append(pdk.Layer(
            "LineLayer",
            data=[{
                "source": [lon, lat],
                "target": list(best)
            }],
            get_source_position="source",
            get_target_position="target",
            get_color=[0, 120, 255],
            get_width=3
        ))

        # ---------------- VIEW ----------------
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=lat,
                longitude=lon,
                zoom=12
            )
        ))