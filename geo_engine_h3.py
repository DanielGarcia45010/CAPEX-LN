import h3
from collections import defaultdict
from shapely.geometry import shape

class H3GeoEngine:

    def __init__(self, resolution=9):
        self.resolution = resolution
        self.index = defaultdict(list)  # h3_cell -> geometries

    def build(self, geometries):

        for i, geom in enumerate(geometries):

            try:
                c = geom.centroid
                h = h3.latlng_to_cell(c.y, c.x, self.resolution)
                self.index[h].append(i)

            except:
                continue

    def query(self, lon, lat, k_ring=2):

        center = h3.latlng_to_cell(lat, lon, self.resolution)

        neighbors = h3.grid_disk(center, k_ring)

        results = []

        for h in neighbors:
            if h in self.index:
                for idx in self.index[h]:
                    results.append((h, idx))

        return results