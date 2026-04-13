# geojson_densifier.py
import json
import streamlit as st
from shapely.geometry import shape, Point
import numpy as np

st.set_page_config(page_title="Densificador de GeoJSON", layout="wide")
st.title("🔄 Densificador de GeoJSON - LineStrings a Puntos")

st.info("""
**Problema:** Tu KMZ tiene LineStrings largos que hacen difícil encontrar el punto más cercano exacto.

**Solución:** Esta herramienta convierte LineStrings largos en múltiples puntos distribuidos uniformemente.
""")

# Configuración
st.sidebar.header("⚙️ Configuración")

point_spacing = st.sidebar.slider(
    "Espaciado entre puntos (metros)", 
    10, 200, 50, 10,
    help="Distancia aproximada entre puntos generados"
)

preserve_original = st.sidebar.checkbox(
    "Preservar geometrías originales", 
    value=False,
    help="Mantener LineStrings/Polygons originales además de los puntos"
)

def estimate_points_per_meter(geom):
    """Estima cuántos puntos necesitamos basado en la longitud"""
    if geom.geom_type in ["LineString", "LinearRing"]:
        return geom.length
    elif geom.geom_type == "Polygon":
        return geom.boundary.length
    return 0

def densify_linestring(linestring, spacing_degrees):
    """Convierte un LineString en múltiples puntos equidistantes"""
    points = []
    total_length = linestring.length
    
    if total_length == 0:
        return [Point(linestring.coords[0])]
    
    # Calcular número de puntos basado en el espaciado deseado
    num_points = max(2, int(total_length / spacing_degrees))
    
    for i in range(num_points):
        distance = (i / (num_points - 1)) * total_length if num_points > 1 else 0
        point = linestring.interpolate(distance)
        points.append(point)
    
    return points

def densify_polygon(polygon, spacing_degrees):
    """Convierte un Polygon en múltiples puntos alrededor del perímetro"""
    boundary = polygon.boundary
    return densify_linestring(boundary, spacing_degrees)

def meters_to_degrees_approx(meters, lat):
    """Conversión aproximada de metros a grados"""
    # 1 grado de latitud ≈ 111,320 metros
    # 1 grado de longitud ≈ 111,320 * cos(lat) metros
    lat_deg = meters / 111320
    return lat_deg

def densify_geojson(geojson_data, spacing_meters):
    """Densifica un GeoJSON convirtiendo LineStrings y Polygons en puntos"""
    
    new_features = []
    stats = {
        "original_features": 0,
        "new_points": 0,
        "linestrings_processed": 0,
        "polygons_processed": 0,
        "points_preserved": 0
    }
    
    for feature in geojson_data.get("features", []):
        stats["original_features"] += 1
        geom_data = feature.get("geometry")
        properties = feature.get("properties", {})
        
        if not geom_data:
            continue
            
        geom = shape(geom_data)
        
        # Estimar latitud promedio para conversión
        if hasattr(geom, 'bounds'):
            avg_lat = (geom.bounds[1] + geom.bounds[3]) / 2
        else:
            avg_lat = 0
            
        spacing_degrees = meters_to_degrees_approx(spacing_meters, avg_lat)
        
        # Preservar geometrías originales si se solicita
        if preserve_original:
            new_features.append(feature)
        
        # Procesar según tipo de geometría
        if geom.geom_type == "Point":
            if not preserve_original:
                new_features.append(feature)
            stats["points_preserved"] += 1
            
        elif geom.geom_type == "LineString":
            points = densify_linestring(geom, spacing_degrees)
            stats["linestrings_processed"] += 1
            
            for i, point in enumerate(points):
                new_feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [point.x, point.y]
                    },
                    "properties": {
                        **properties,
                        "densified_from": "LineString",
                        "point_index": i,
                        "total_points": len(points)
                    }
                }
                new_features.append(new_feature)
                stats["new_points"] += 1
                
        elif geom.geom_type == "Polygon":
            points = densify_polygon(geom, spacing_degrees)
            stats["polygons_processed"] += 1
            
            for i, point in enumerate(points):
                new_feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [point.x, point.y]
                    },
                    "properties": {
                        **properties,
                        "densified_from": "Polygon",
                        "point_index": i,
                        "total_points": len(points)
                    }
                }
                new_features.append(new_feature)
                stats["new_points"] += 1
                
        elif geom.geom_type.startswith("Multi"):
            # Procesar cada sub-geometría
            for sub_geom in geom.geoms:
                if sub_geom.geom_type == "LineString":
                    points = densify_linestring(sub_geom, spacing_degrees)
                    stats["linestrings_processed"] += 1
                elif sub_geom.geom_type == "Polygon":
                    points = densify_polygon(sub_geom, spacing_degrees)
                    stats["polygons_processed"] += 1
                else:
                    continue
                    
                for i, point in enumerate(points):
                    new_feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [point.x, point.y]
                        },
                        "properties": {
                            **properties,
                            "densified_from": f"Multi{sub_geom.geom_type}",
                            "point_index": i,
                            "total_points": len(points)
                        }
                    }
                    new_features.append(new_feature)
                    stats["new_points"] += 1
    
    # Crear nuevo GeoJSON
    densified_geojson = {
        "type": "FeatureCollection",
        "features": new_features
    }
    
    return densified_geojson, stats

# UI Principal
uploaded_file = st.file_uploader("Sube tu GeoJSON original", type=["geojson", "json"])

if uploaded_file:
    try:
        geojson_data = json.loads(uploaded_file.read().decode("utf-8"))
        
        # Mostrar estadísticas del archivo original
        original_features = len(geojson_data.get("features", []))
        st.info(f"📄 **Archivo original:** {original_features} features")
        
        # Analizar tipos de geometría
        geom_types = {}
        total_length_estimate = 0
        
        for feature in geojson_data.get("features", []):
            geom_data = feature.get("geometry")
            if geom_data:
                geom_type = geom_data.get("type")
                geom_types[geom_type] = geom_types.get(geom_type, 0) + 1
                
                # Estimar longitud total para predicción
                try:
                    geom = shape(geom_data)
                    total_length_estimate += estimate_points_per_meter(geom)
                except:
                    pass
        
        # Mostrar análisis
        st.write("**Tipos de geometría encontrados:**")
        for geom_type, count in geom_types.items():
            st.write(f"- {geom_type}: {count}")
        
        # Predicción de puntos
        if total_length_estimate > 0:
            spacing_degrees_approx = meters_to_degrees_approx(point_spacing, 0)
            estimated_points = int(total_length_estimate / spacing_degrees_approx)
            st.info(f"🎯 **Puntos estimados a generar:** ~{estimated_points:,}")
        
        if st.button("🔄 Densificar GeoJSON"):
            with st.spinner("Procesando geometrías..."):
                densified_geojson, stats = densify_geojson(geojson_data, point_spacing)
            
            # Mostrar resultados
            st.success("✅ **Densificación completada!**")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Features originales", stats["original_features"])
                st.metric("LineStrings procesados", stats["linestrings_processed"])
            with col2:
                st.metric("Puntos generados", stats["new_points"])
                st.metric("Polygons procesados", stats["polygons_processed"])
            with col3:
                st.metric("Total features final", len(densified_geojson["features"]))
                st.metric("Puntos preservados", stats["points_preserved"])
            
            # Botón de descarga
            json_string = json.dumps(densified_geojson, indent=2)
            st.download_button(
                label="📥 Descargar GeoJSON Densificado",
                data=json_string,
                file_name=f"densified_{uploaded_file.name}",
                mime="application/json"
            )
            
            # Mostrar preview del resultado
            with st.expander("👀 Preview del GeoJSON densificado"):
                st.json(densified_geojson["features"][:3])  # Mostrar solo primeros 3
                if len(densified_geojson["features"]) > 3:
                    st.write(f"... y {len(densified_geojson['features']) - 3} features más")
            
    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")

# Información adicional
st.markdown("---")
st.markdown("""
### 💡 **Cómo usar:**

1. **Sube tu GeoJSON** original (el que convertiste desde KMZ)
2. **Ajusta el espaciado** entre puntos (50m es bueno para zonas urbanas)
3. **Haz clic en Densificar** y espera el procesamiento
4. **Descarga el resultado** y úsalo en tu aplicación principal

### 🎯 **Ventajas del GeoJSON densificado:**

- ✅ **Puntos precisos** en lugar de líneas largas
- ✅ **Mejor precisión** en cálculo de distancias
- ✅ **Resultados más predecibles**
- ✅ **Menos ambigüedad** sobre dónde está el punto más cercano

### ⚠️ **Consideraciones:**

- **Archivos más grandes:** Más puntos = más datos
- **Ajusta el espaciado:** 50m para urbano, 100m+ para rural
- **Prueba primero:** Con una muestra pequeña
""")