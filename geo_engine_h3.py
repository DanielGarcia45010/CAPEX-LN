import h3
from collections import defaultdict
from shapely.geometry import Point

class GeoEngineH3:

    def __init__(self, resolution=8):
        self.resolution = resolution
        self.index = defaultdict(list)
        self.geometries = []

    def _to_h3(self, lon, lat):
        return h3.latlng_to_cell(lat, lon, self.resolution)

    def build(self, geometries):

        self.index.clear()
        self.geometries = geometries

        for i, geom in enumerate(geometries):

            try:

                if geom.geom_type == "Point":
                    h = self._to_h3(geom.x, geom.y)
                    self.index[h].append(i)

                elif geom.geom_type in ["LineString", "LinearRing"]:
                    coords = list(geom.coords)
                    for lon, lat in coords[::max(1, len(coords)//5)]:
                        h = self._to_h3(lon, lat)
                        self.index[h].append(i)

                elif geom.geom_type == "Polygon":
                    c = geom.centroid
                    h = self._to_h3(c.x, c.y)
                    self.index[h].append(i)

                elif geom.geom_type.startswith("Multi"):
                    for g in geom.geoms:
                        c = g.centroid
                        h = self._to_h3(c.x, c.y)
                        self.index[h].append(i)

            except:
                continue

    def query(self, lon, lat, k=30):

        center = self._to_h3(lon, lat)

        neighbors = h3.grid_disk(center, 1)

        candidates = set()

        for cell in neighbors:
            if cell in self.index:
                candidates.update(self.index[cell])

        return list(candidates)