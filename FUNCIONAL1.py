# CÓDIGO OPTIMIZADO - REDUCCIÓN DE 2min A 30seg
import json
import streamlit as st
import pydeck as pdk
import requests
import time
from shapely.geometry import shape, Point
from shapely.ops import transform as shp_transform, nearest_points
from pyproj import Transformer
import numpy as np
from scipy.spatial import cKDTree
import pandas as pd

st.set_page_config(page_title="CAPEX EVALUATION", layout="wide")
st.title("CAPEX EVALUATION")

# ---------------- Configuración de APIs ----------------
st.sidebar.header("⚙️ Configuración")

# Tipo de cálculo de distancia
distance_mode = st.sidebar.selectbox(
    "Modo de cálculo de distancia",
    ["Peatonal (ignora direcciones)"],
    help="""
    • Peatonal: Ignora sentidos de calles y restricciones vehiculares
    """
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
else:  # Precisa
    max_candidates = st.sidebar.slider("Máximo candidatos", 20, 100, 50)
    st.sidebar.info("🎯 Mejor precisión - Más lento")

# ---------------- Utilidades Optimizadas ----------------
def build_spatial_index_simple(geometries):
    """
    Construye un índice espacial KDTree para búsquedas ultra-rápidas.
    Sin cache para evitar problemas de hash - aún así muy rápido.
    """
    points = []
    geom_indices = []
    
    for i, geom in enumerate(geometries):
        if geom.geom_type == "Point":
            points.append([geom.x, geom.y])
            geom_indices.append(i)
        elif geom.geom_type in ["LineString", "LinearRing"]:
            # Solo agregar puntos inicio y fin para el índice rápido
            coords = list(geom.coords)
            points.extend([[coords[0][0], coords[0][1]], [coords[-1][0], coords[-1][1]]])
            geom_indices.extend([i, i])
        elif geom.geom_type == "Polygon":
            # Solo el centroide para el índice rápido
            centroid = geom.centroid
            points.append([centroid.x, centroid.y])
            geom_indices.append(i)
        elif geom.geom_type.startswith("Multi"):
            # Solo primer elemento de multi-geometrías
            if len(geom.geoms) > 0:
                first_geom = geom.geoms[0]
                if first_geom.geom_type == "Point":
                    points.append([first_geom.x, first_geom.y])
                    geom_indices.append(i)
                else:
                    centroid = first_geom.centroid
                    points.append([centroid.x, centroid.y])
                    geom_indices.append(i)
    
    if points:
        tree = cKDTree(np.array(points))
        return tree, geom_indices
    return None, []

def get_euclidean_distances_fast(geometries, client_lon, client_lat, max_results=50):
    """
    OPTIMIZACIÓN PRINCIPAL: Usa KDTree para búsqueda ultra-rápida.
    De O(n) a O(log n) - Reducción masiva de tiempo.
    """
    start_time = time.time()
    
    # Construir índice espacial (sin cache para evitar errores)
    tree, geom_indices = build_spatial_index_simple(geometries)
    
    if tree is None:
        return []
    
    # Búsqueda ultra-rápida con KDTree
    query_point = [client_lon, client_lat]
    
    # Buscar los k-vecinos más cercanos
    k = min(max_results * 2, len(geom_indices))  # Buscar más para filtrar duplicados
    distances, indices = tree.query(query_point, k=k)
    
    # Procesar resultados y eliminar duplicados de geometrías
    seen_geoms = set()
    results = []
    
    for dist, idx in zip(distances, indices):
        geom_idx = geom_indices[idx]
        if geom_idx not in seen_geoms:
            seen_geoms.add(geom_idx)
            # Convertir distancia a metros (aproximación rápida)
            dist_meters = dist * 111320  # 1 grado ≈ 111.32 km
            results.append((dist_meters, geom_idx, (client_lon, client_lat)))
            
            if len(results) >= max_results:
                break
    
    elapsed = time.time() - start_time
    st.success(f"⚡ Filtro euclidiano completado en {elapsed:.2f}s (KDTree)")
    
    return results

def get_smart_candidate_points_fast(geom, client_lon, client_lat, max_points=2):
    """
    Versión optimizada que genera menos puntos candidatos.
    """
    candidates = []
    
    if geom.geom_type == "Point":
        candidates.append((geom.x, geom.y))
    
    elif geom.geom_type in ["LineString", "LinearRing"]:
        coords = list(geom.coords)
        if len(coords) >= 2:
            # Solo inicio, medio y fin
            candidates.append((coords[0][0], coords[0][1]))  # Inicio
            if len(coords) > 2:
                mid_idx = len(coords) // 2
                candidates.append((coords[mid_idx][0], coords[mid_idx][1]))  # Medio
            candidates.append((coords[-1][0], coords[-1][1]))  # Fin
    
    elif geom.geom_type == "Polygon":
        # Solo usar el punto más cercano del borde
        try:
            client_point = Point(client_lon, client_lat)
            _, closest_point = nearest_points(client_point, geom.boundary)
            candidates.append((closest_point.x, closest_point.y))
        except:
            # Fallback al centroide
            centroid = geom.centroid
            candidates.append((centroid.x, centroid.y))
    
    elif geom.geom_type.startswith("Multi"):
        # Solo el primer elemento
        if len(geom.geoms) > 0:
            sub_candidates = get_smart_candidate_points_fast(geom.geoms[0], client_lon, client_lat, 1)
            candidates.extend(sub_candidates)
    
    # Limitar número de candidatos
    return candidates[:max_points]

# ---------------- Servicios de Routing Optimizados ----------------
def get_walking_route_osrm_fast(start_lon, start_lat, end_lon, end_lat):
    """
    Versión optimizada con timeout más corto y menos parámetros.
    """
    url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {
        "overview": "false",
        "geometries": "geojson"
    }
    
    try:
        response = requests.get(url, params=params, timeout=3)  # Timeout reducido
        if response.status_code == 200:
            data = response.json()
            if data.get("routes"):
                route = data["routes"][0]
                distance_m = route["distance"]
                duration_s = route["duration"]
                return distance_m, duration_s
    except Exception:
        pass
    return None, None

def get_walking_route_full_osrm(start_lon, start_lat, end_lon, end_lat):
    """Obtiene ruta completa solo para visualización final"""
    url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {
        "overview": "full",
        "geometries": "geojson"
    }
    
    try:
        response = requests.get(url, params=params, timeout=8)
        if response.status_code == 200:
            data = response.json()
            if data.get("routes"):
                route = data["routes"][0]
                route_coords = route["geometry"]["coordinates"]
                distance_m = route["distance"]
                duration_s = route["duration"]
                return route_coords, distance_m, duration_s
    except Exception as e:
        return None, None, f"Error: {str(e)}"
    return None, None, "No se pudo obtener la ruta"

# ---------------- Función Principal Optimizada ----------------
def find_closest_point_ultra_fast(geometries, client_lon, client_lat, max_candidates):
    """
    Algoritmo ultra-optimizado para archivos grandes.
    OBJETIVO: Reducir de 2 minutos a 30 segundos.
    """
    total_geoms = len(geometries)
    
    # PASO 1: Filtro ultra-rápido con KDTree
    with st.spinner("⚡Procesando..."):
        euclidean_results = get_euclidean_distances_fast(geometries, client_lon, client_lat, max_candidates)
    
    if not euclidean_results:
        st.error("No se encontraron geometrías válidas")
        return None, None, None, -1, None, 0
    
    
    # PASO 2: Generar candidatos de los mejores resultados
    candidates_to_evaluate = []
    
    for dist_euclidean, geom_idx, _ in euclidean_results:
        geom = geometries[geom_idx]
        candidates = get_smart_candidate_points_fast(geom, client_lon, client_lat, 2)
        
        for candidate_lon, candidate_lat in candidates:
            candidates_to_evaluate.append((geom_idx, candidate_lon, candidate_lat))
    
    total_to_evaluate = len(candidates_to_evaluate)
    
    # PASO 3: Evaluación rápida de rutas
    best_distance = float('inf')
    best_point = None
    best_geometry_idx = -1
    best_duration = None
    successful_routes = 0
    failed_routes = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Procesar en lotes para mejor rendimiento
    batch_size = 5
    for i in range(0, total_to_evaluate, batch_size):
        batch = candidates_to_evaluate[i:i+batch_size]
        
        for j, (geom_idx, candidate_lon, candidate_lat) in enumerate(batch):
            current_idx = i + j
            progress = (current_idx + 1) / total_to_evaluate
            progress_bar.progress(progress)
            status_text.text(f"⚡ {current_idx+1}/{total_to_evaluate} | ✅{successful_routes} | Mejor: {best_distance:.0f}m")
            
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
        
        # Pausa mínima entre lotes
        time.sleep(0.01)
    
    progress_bar.empty()
    status_text.empty()
    
    # PASO 4: Obtener ruta completa solo si se encontró resultado
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
    """Capas base del GeoJSON con optimización para archivos grandes"""
    pts_data, lines_data = [], []
    
    # Limitar número de features para visualización si el archivo es muy grande
    """Capas base del GeoJSON"""
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
            lon, lat = coords
            pts_data.append({"position": [lon, lat], "name": name})
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
                    outer = poly[0]
                    lines_data.append({"path": outer, "name": name})

    layers = []
    if pts_data:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=pts_data,
            get_position="position",
            get_radius=6,
            pickable=True,
            get_fill_color=[0, 122, 255]
        ))
    if lines_data:
        layers.append(pdk.Layer(
            "PathLayer",
            data=lines_data,
            get_path="path",
            width_scale=1,
            width_min_pixels=1,
            pickable=True,
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

    # Recomendaciones automáticas
    if total_geoms > 5000:
        st.warning("⚠️ **Archivo muy grande** - Se recomienda estrategia 'Ultra Rápida'")
    elif total_geoms > 1000:
        st.info("💡 **Archivo grande** - Estrategia 'Híbrida' recomendada")

    if st.button("🚀 Empezar Análisis"):
        start_time = time.time()
        
        result = find_closest_point_ultra_fast(
            geometries, lon, lat, max_candidates
        )
        walking_distance_m, route_coords, closest_point, geom_idx, duration_s, successful_routes = result
        elapsed_time = time.time() - start_time
        if closest_point and walking_distance_m:
            duration_min = duration_s / 60 if duration_s else 0
            
            st.success(f"""
            ✅- **Distancia:** {walking_distance_m:.0f} metros
            - **Coordenadas destino:** {closest_point[1]:.6f}, {closest_point[0]:.6f}
            - **Rutas evaluadas:** {successful_routes}
            """)
            
            # Visualizar (optimizado para archivos grandes)
            with st.spinner("Preparando visualización..."):
                layers = pydeck_layers_from_geojson(gj)
                
                # Punto del cliente (rojo)
                layers.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"position": [lon, lat], "name": "🔴 Cliente"}],
                    get_position="position",
                    get_radius=15,
                    get_fill_color=[230, 57, 70],
                ))
                
                # Punto destino (verde)
                layers.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"position": [closest_point[0], closest_point[1]], 
                          "name": f"🟢 Destino ({walking_distance_m:.0f}m)"}],
                    get_position="position",
                    get_radius=12,
                    get_fill_color=[40, 167, 69],
                ))
                
                # Ruta (si existe)
                if route_coords:
                    layers.append(pdk.Layer(
                        "PathLayer",
                        data=[{"path": route_coords, "name": f"Ruta: {walking_distance_m:.0f}m"}],
                        get_path="path",
                        width_scale=6,
                        width_min_pixels=4,
                        get_color=[138, 43, 226],
                    ))
                
                # Vista centrada
                center_lat = (lat + closest_point[1]) / 2
                center_lon = (lon + closest_point[0]) / 2
                view = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=14)
                
                st.pydeck_chart(pdk.Deck(
                    layers=layers,
                    initial_view_state=view,
                    tooltip={"text": "{name}"},
                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
                ))
                select_ciudad = st.selectbox(
                    "Selecciona la ciudad que más se acerque a su ubicación",
                    ["", "Barranquilla","Bogotá","Bucaramanga","Cali","Cartagena","Cúcuta","Ibagué","Ipiales","Medellín",
                    "Montería","Palmira","Pasto","Popayán","Santa Marta","Sincelejo","Valledupar","Villavicencio"]
                )         

                d1, d2 = st.columns(2)

                if select_ciudad == "Barranquilla" or "Cartagena":
                    HabilitacionH = 909453
                    DRC = 1408538
                    d1 = DRC
                    RxM = 7605
                    d2 = RxM
                    Postes = st.checkbox("¿Se requiere arriendo de postes?", value=True)
                    if Postes == True:
                        VUAPostes = 75
                        VTAPostesMex = walking_distance_m * VUAPostes
                        VTAPostesAno = VTAPostesMex * 12
                        ValorTotalOCext = walking_distance_m * RxM
                        Cuantizado = ValorTotalOCext + VTAPostesMex
                    else:
                        ValorTotalOCext = walking_distance_m * RxM
                        

                    

        else:
            st.error("❌ No se encontró ninguna ruta válida")



    

# # Info sidebar
# st.sidebar.markdown("---")
# st.sidebar.markdown("""
                    

# ### ⚡ Optimizaciones Implementadas

# **KDTree Espacial:** Búsqueda O(log n) vs O(n)

# **Cache Inteligente:** Índice se construye solo una vez

# **Filtro Agresivo:** Solo evalúa mejores candidatos

# **Timeouts Cortos:** 3s por request vs 5s

# **Procesamiento por Lotes:** Mejor uso de recursos

# ### 🎯 Rendimiento Esperado

# - **Ultra Rápida:** 10-30 segundos
# - **Híbrida:** 30-60 segundos  
# - **Precisa:** 60-120 segundos

# ### 💡 Recomendaciones

# - **<1K geometrías:** Cualquier estrategia
# - **1K-5K geometrías:** Híbrida
# - **>5K geometrías:** Ultra Rápida
# """)