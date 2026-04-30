import json
import streamlit as st
import pydeck as pdk
import requests
import time
from shapely.geometry import shape, Point
from shapely.ops import nearest_points
import numpy as np
from scipy.spatial import cKDTree
import pandas as pd

st.set_page_config(page_title="CAPEX EVALUATION", layout="wide")
st.title("CAPEX EVALUATION")

# ---------------- Configuración de APIs ----------------
st.sidebar.header("⚙️ Configuración")

distance_mode = st.sidebar.selectbox(
    "Modo de cálculo de distancia",
    ["Peatonal (ignora direcciones)"],
    help="• Peatonal: Ignora sentidos de calles y restricciones vehiculares"
)

# ---------------- Estrategia de Optimización ----------------
st.sidebar.header("🚀 Optimización")
strategy = st.sidebar.selectbox(
    "Estrategia de búsqueda",
    ["Ultra Rápida", "Híbrida (Recomendada)", "Precisa"]
)

if strategy == "Ultra Rápida":
    max_candidates = st.sidebar.slider("Máximo candidatos", 5, 20, 10)
    st.sidebar.info("⚡ Evalúa solo los más cercanos - Máxima velocidad")
elif strategy == "Híbrida (Recomendada)":
    max_candidates = st.sidebar.slider("Máximo candidatos", 10, 50, 25)
    st.sidebar.info("⚖️ Balance velocidad/precisión")
else:
    max_candidates = st.sidebar.slider("Máximo candidatos", 20, 100, 50)
    st.sidebar.info("🎯 Mejor precisión - Más lento")

# ---------------- Parámetros financieros por ciudad ----------------
CIUDAD_PARAMS = {
    "Barranquilla": {"HabilitacionH": 909453, "DRC": 1408538, "RxM": 7605, "VUAPostes": 75},
    "Cartagena":    {"HabilitacionH": 909453, "DRC": 1408538, "RxM": 7605, "VUAPostes": 75},
    "Bogotá":       {"HabilitacionH": 950000, "DRC": 1500000, "RxM": 8000, "VUAPostes": 80},
    "Medellín":     {"HabilitacionH": 920000, "DRC": 1450000, "RxM": 7800, "VUAPostes": 78},
    "Cali":         {"HabilitacionH": 910000, "DRC": 1420000, "RxM": 7650, "VUAPostes": 76},
    # Agrega los demás según tus datos reales
}

# Ciudades que comparten los mismos parámetros que Barranquilla (placeholder)
CIUDADES_TODAS = [
    "Barranquilla", "Bogotá", "Bucaramanga", "Cali", "Cartagena", "Cúcuta",
    "Ibagué", "Ipiales", "Medellín", "Montería", "Palmira", "Pasto",
    "Popayán", "Santa Marta", "Sincelejo", "Valledupar", "Villavicencio"
]
# Para ciudades sin parámetros definidos, usar valores de Barranquilla como fallback
for ciudad in CIUDADES_TODAS:
    if ciudad not in CIUDAD_PARAMS:
        CIUDAD_PARAMS[ciudad] = CIUDAD_PARAMS["Barranquilla"]

# ---------------- Utilidades Optimizadas ----------------
def build_spatial_index_simple(geometries):
    points = []
    geom_indices = []
    for i, geom in enumerate(geometries):
        if geom.geom_type == "Point":
            points.append([geom.x, geom.y])
            geom_indices.append(i)
        elif geom.geom_type in ["LineString", "LinearRing"]:
            coords = list(geom.coords)
            points.extend([[coords[0][0], coords[0][1]], [coords[-1][0], coords[-1][1]]])
            geom_indices.extend([i, i])
        elif geom.geom_type == "Polygon":
            centroid = geom.centroid
            points.append([centroid.x, centroid.y])
            geom_indices.append(i)
        elif geom.geom_type.startswith("Multi"):
            if len(geom.geoms) > 0:
                first_geom = geom.geoms[0]
                if first_geom.geom_type == "Point":
                    points.append([first_geom.x, first_geom.y])
                else:
                    centroid = first_geom.centroid
                    points.append([centroid.x, centroid.y])
                geom_indices.append(i)

    if points:
        tree = cKDTree(np.array(points))
        return tree, geom_indices
    return None, []


def get_euclidean_distances_fast(geometries, client_lon, client_lat, max_results=50):
    start_time = time.time()
    tree, geom_indices = build_spatial_index_simple(geometries)
    if tree is None:
        return []

    query_point = [client_lon, client_lat]
    k = min(max_results * 2, len(geom_indices))
    distances, indices = tree.query(query_point, k=k)

    seen_geoms = set()
    results = []
    for dist, idx in zip(distances, indices):
        geom_idx = geom_indices[idx]
        if geom_idx not in seen_geoms:
            seen_geoms.add(geom_idx)
            dist_meters = dist * 111320
            results.append((dist_meters, geom_idx, (client_lon, client_lat)))
            if len(results) >= max_results:
                break

    elapsed = time.time() - start_time
    st.success(f"⚡ Filtro euclidiano completado en {elapsed:.2f}s (KDTree)")
    return results


def get_smart_candidate_points_fast(geom, client_lon, client_lat, max_points=2):
    candidates = []
    if geom.geom_type == "Point":
        candidates.append((geom.x, geom.y))
    elif geom.geom_type in ["LineString", "LinearRing"]:
        coords = list(geom.coords)
        if len(coords) >= 2:
            candidates.append((coords[0][0], coords[0][1]))
            if len(coords) > 2:
                mid_idx = len(coords) // 2
                candidates.append((coords[mid_idx][0], coords[mid_idx][1]))
            candidates.append((coords[-1][0], coords[-1][1]))
    elif geom.geom_type == "Polygon":
        try:
            client_point = Point(client_lon, client_lat)
            _, closest_point = nearest_points(client_point, geom.boundary)
            candidates.append((closest_point.x, closest_point.y))
        except Exception:
            centroid = geom.centroid
            candidates.append((centroid.x, centroid.y))
    elif geom.geom_type.startswith("Multi"):
        if len(geom.geoms) > 0:
            sub_candidates = get_smart_candidate_points_fast(geom.geoms[0], client_lon, client_lat, 1)
            candidates.extend(sub_candidates)
    return candidates[:max_points]


# ---------------- Servicios de Routing ----------------
def get_walking_route_osrm_fast(start_lon, start_lat, end_lon, end_lat):
    url = (
        f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
    )
    params = {"overview": "false", "geometries": "geojson"}
    try:
        response = requests.get(url, params=params, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("routes"):
                route = data["routes"][0]
                return route["distance"], route["duration"]
    except Exception:
        pass
    return None, None


def get_walking_route_full_osrm(start_lon, start_lat, end_lon, end_lat):
    url = (
        f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
    )
    params = {"overview": "full", "geometries": "geojson"}
    try:
        response = requests.get(url, params=params, timeout=8)
        if response.status_code == 200:
            data = response.json()
            if data.get("routes"):
                route = data["routes"][0]
                return route["geometry"]["coordinates"], route["distance"], route["duration"]
    except Exception as e:
        return None, None, f"Error: {str(e)}"
    return None, None, "No se pudo obtener la ruta"


# ---------------- Función Principal ----------------
def find_closest_point_ultra_fast(geometries, client_lon, client_lat, max_candidates):
    with st.spinner("⚡ Procesando..."):
        euclidean_results = get_euclidean_distances_fast(
            geometries, client_lon, client_lat, max_candidates
        )

    if not euclidean_results:
        st.error("No se encontraron geometrías válidas")
        return None, None, None, -1, None, 0

    candidates_to_evaluate = []
    for dist_euclidean, geom_idx, _ in euclidean_results:
        geom = geometries[geom_idx]
        candidates = get_smart_candidate_points_fast(geom, client_lon, client_lat, 2)
        for candidate_lon, candidate_lat in candidates:
            candidates_to_evaluate.append((geom_idx, candidate_lon, candidate_lat))

    total_to_evaluate = len(candidates_to_evaluate)
    best_distance = float('inf')
    best_point = None
    best_geometry_idx = -1
    best_duration = None
    successful_routes = 0
    failed_routes = 0

    progress_bar = st.progress(0)
    status_text = st.empty()

    batch_size = 5
    for i in range(0, total_to_evaluate, batch_size):
        batch = candidates_to_evaluate[i:i + batch_size]
        for j, (geom_idx, candidate_lon, candidate_lat) in enumerate(batch):
            current_idx = i + j
            progress = (current_idx + 1) / total_to_evaluate
            progress_bar.progress(progress)
            status_text.text(
                f"⚡ {current_idx + 1}/{total_to_evaluate} | "
                f"✅{successful_routes} | Mejor: {best_distance:.0f}m"
            )

            distance_m, duration_s = get_walking_route_osrm_fast(
                client_lon, client_lat, candidate_lon, candidate_lat
            )

            if distance_m is not None:
                successful_routes += 1
                if distance_m < best_distance:
                    best_distance = distance_m
                    best_point = (candidate_lon, candidate_lat)
                    best_geometry_idx = geom_idx
                    best_duration = duration_s
            else:
                failed_routes += 1

        time.sleep(0.01)

    progress_bar.empty()
    status_text.empty()

    best_route = None
    if best_point and successful_routes > 0:
        st.info("🗺️ Obteniendo ruta completa...")
        best_route, _, _ = get_walking_route_full_osrm(
            client_lon, client_lat, best_point[0], best_point[1]
        )

    return best_distance, best_route, best_point, best_geometry_idx, best_duration, successful_routes


# ---------------- Utilidades para Visualización ----------------
def load_geojson_features(gj: dict):
    feats = []
    for f in gj.get("features", []):
        geom = f.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
        except Exception:
            continue
        feats.append({"geom": g, "props": f.get("properties", {})})
    return feats


def pydeck_layers_from_geojson(gj: dict):
    pts_data, lines_data = [], []
    for f in gj.get("features", []):
        geom = f.get("geometry")
        props = f.get("properties", {}) or {}
        name = props.get("name", "Sin nombre")
        if not geom:
            continue
        t = geom.get("type", "")
        coords = geom.get("coordinates")
        if t == "Point":
            pts_data.append({"position": [coords[0], coords[1]], "name": name})
        elif t == "MultiPoint":
            for lon, lat in coords:
                pts_data.append({"position": [lon, lat], "name": name})
        elif t == "LineString":
            lines_data.append({"path": coords, "name": name})
        elif t == "MultiLineString":
            for path in coords:
                lines_data.append({"path": path, "name": name})
        elif t == "Polygon":
            outer = coords[0] if coords else []
            lines_data.append({"path": outer, "name": name})
        elif t == "MultiPolygon":
            for poly in coords:
                if poly:
                    lines_data.append({"path": poly[0], "name": name})

    layers = []
    if pts_data:
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=pts_data,
            get_position="position", get_radius=6,
            pickable=True, get_fill_color=[0, 122, 255]
        ))
    if lines_data:
        layers.append(pdk.Layer(
            "PathLayer", data=lines_data,
            get_path="path", width_scale=1,
            width_min_pixels=1, pickable=True,
            get_color=[0, 200, 255]
        ))
    return layers


# ---------------- UI Principal ----------------
gj_file = st.file_uploader("Sube tu GeoJSON/KMZ convertido", type=["geojson", "json"])
client = st.text_input("Coordenadas del cliente (lat,lon)", placeholder="10.99384,-74.79639")

if gj_file and client:
    try:
        gj = json.loads(gj_file.read().decode("utf-8"))
    except Exception as e:
        st.error(f"No se pudo leer el GeoJSON: {e}")
        st.stop()

    feats = load_geojson_features(gj)
    if not feats:
        st.error("El GeoJSON no contiene features válidos.")
        st.stop()

    try:
        lat, lon = map(float, client.split(","))
    except Exception:
        st.error("Formato inválido. Usa: lat,lon")
        st.stop()

    geometries = [f["geom"] for f in feats]
    total_geoms = len(geometries)

    if total_geoms > 5000:
        st.warning("⚠️ **Archivo muy grande** - Se recomienda estrategia 'Ultra Rápida'")
    elif total_geoms > 1000:
        st.info("💡 **Archivo grande** - Estrategia 'Híbrida' recomendada")

    if st.button("🚀 Empezar Análisis"):
        start_time = time.time()
        result = find_closest_point_ultra_fast(geometries, lon, lat, max_candidates)
        walking_distance_m, route_coords, closest_point, geom_idx, duration_s, successful_routes = result
        elapsed_time = time.time() - start_time

        if closest_point and walking_distance_m:
            st.success(f"""
✅
- **Distancia:** {walking_distance_m:.0f} metros
- **Coordenadas destino:** {closest_point[1]:.6f}, {closest_point[0]:.6f}
- **Rutas evaluadas:** {successful_routes}
- **Tiempo total:** {elapsed_time:.1f}s
""")

            # Visualización
            with st.spinner("Preparando visualización..."):
                layers = pydeck_layers_from_geojson(gj)

                layers.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"position": [lon, lat], "name": "🔴 Cliente"}],
                    get_position="position", get_radius=15,
                    get_fill_color=[230, 57, 70],
                ))
                layers.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"position": list(closest_point), "name": f"🟢 Destino ({walking_distance_m:.0f}m)"}],
                    get_position="position", get_radius=12,
                    get_fill_color=[40, 167, 69],
                ))
                if route_coords:
                    layers.append(pdk.Layer(
                        "PathLayer",
                        data=[{"path": route_coords, "name": f"Ruta: {walking_distance_m:.0f}m"}],
                        get_path="path", width_scale=6,
                        width_min_pixels=4, get_color=[138, 43, 226],
                    ))

                center_lat = (lat + closest_point[1]) / 2
                center_lon = (lon + closest_point[0]) / 2
                view = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=14)
                st.pydeck_chart(pdk.Deck(
                    layers=layers,
                    initial_view_state=view,
                    tooltip={"text": "{name}"},
                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
                ))

            # ---------------- Sección Financiera ----------------
            st.markdown("---")
            st.subheader("💰 Evaluación Financiera")

            select_ciudad = st.selectbox(
                "Selecciona la ciudad que más se acerque a su ubicación",
                [""] + CIUDADES_TODAS
            )

            if select_ciudad:
                params = CIUDAD_PARAMS[select_ciudad]
                HabilitacionH = params["HabilitacionH"]
                DRC            = params["DRC"]
                RxM            = params["RxM"]
                VUAPostes      = params["VUAPostes"]

                Postes = st.checkbox("¿Se requiere arriendo de postes?", value=True)

                ValorTotalOCext = walking_distance_m * RxM
                VTAPostesMex    = walking_distance_m * VUAPostes
                VTAPostesAno    = VTAPostesMex * 12

                if Postes:
                    Cuantizado = ValorTotalOCext + VTAPostesMex
                else:
                    Cuantizado = ValorTotalOCext
                    VTAPostesMex = 0
                    VTAPostesAno = 0

                # Mostrar resultados financieros
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Ciudad seleccionada", select_ciudad)
                    st.metric("Distancia", f"{walking_distance_m:.0f} m")
                    st.metric("Habilitación H", f"${HabilitacionH:,.0f}")
                    st.metric("DRC", f"${DRC:,.0f}")

                with col2:
                    st.metric("Costo OC externo (RxM)", f"${ValorTotalOCext:,.0f}")
                    if Postes:
                        st.metric("Arriendo postes (mensual)", f"${VTAPostesMex:,.0f}")
                        st.metric("Arriendo postes (anual)",   f"${VTAPostesAno:,.0f}")
                    st.metric("💡 Total Cuantizado", f"${Cuantizado:,.0f}")

                # Tabla resumen
                st.markdown("#### Resumen de costos")
                df_resumen = pd.DataFrame({
                    "Concepto": [
                        "Habilitación H",
                        "DRC",
                        "OC Externo (distancia × RxM)",
                        "Arriendo postes mensual" if Postes else "Arriendo postes (N/A)",
                        "Arriendo postes anual"   if Postes else "Arriendo postes anual (N/A)",
                        "TOTAL CUANTIZADO"
                    ],
                    "Valor ($)": [
                        HabilitacionH,
                        DRC,
                        ValorTotalOCext,
                        VTAPostesMex,
                        VTAPostesAno,
                        Cuantizado
                    ]
                })
                df_resumen["Valor ($)"] = df_resumen["Valor ($)"].apply(lambda x: f"${x:,.0f}")
                st.dataframe(df_resumen, use_container_width=True, hide_index=True)

        else:
            st.error("❌ No se encontró ninguna ruta válida")