import h3
from collections import defaultdict

class H3GeoEngine:

    def __init__(self, resolution=9):
        self.resolution = resolution
        self.index = defaultdict(list)

    def build(self, geometries):

        for i, geom in enumerate(geometries):

            try:
                c = geom.centroid
                h = h3.latlng_to_cell(c.y, c.x, self.resolution)
                self.index[h].append(i)

            except:
                continue

    def query(self, lon, lat, k_ring=2, max_expansion=6):

        center = h3.latlng_to_cell(lat, lon, self.resolution)

        results = []

        # 🔥 expansión progresiva inteligente
        for k in range(1, max_expansion + 1):

            neighbors = h3.grid_disk(center, k)

            for h in neighbors:
                if h in self.index:
                    for idx in self.index[h]:
                        results.append((h, idx))

            # si ya hay suficientes candidatos, corta
            if len(results) >= 30:
                break

        return results