import h3
from collections import defaultdict


class H3GeoEngine:

    def __init__(self, resolution=9):
        self.resolution = resolution
        self.index = defaultdict(list)

    def build(self, geometries):

        self.centroids = []

        for i, geom in enumerate(geometries):
            try:
                c = geom.centroid
                self.centroids.append((c.x, c.y))

                h = h3.latlng_to_cell(c.y, c.x, self.resolution)
                self.index[h].append(i)

            except:
                continue

    def query(self, lon, lat, max_k=6, min_results=40):

        center = h3.latlng_to_cell(lat, lon, self.resolution)
        results = []

        # expansión progresiva controlada
        for k in range(1, max_k + 1):

            for h in h3.grid_disk(center, k):
                if h in self.index:
                    for idx in self.index[h]:
                        results.append((h, idx))

            if len(results) >= min_results:
                break

        return results