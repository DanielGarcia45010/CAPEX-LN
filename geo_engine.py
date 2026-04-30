import numpy as np
from scipy.spatial import cKDTree


class GeoEngine:

    def __init__(self):
        self.tree = None
        self.geom_index = None

    def build(self, geometries):

        points = []
        index = []

        for i, g in enumerate(geometries):

            try:
                if g.geom_type == "Point":
                    points.append([g.x, g.y])
                    index.append(i)

                elif g.geom_type in ["LineString", "LinearRing"]:
                    c = list(g.coords)
                    if len(c) > 0:
                        points.append(c[0])
                        index.append(i)
                    if len(c) > 1:
                        points.append(c[-1])
                        index.append(i)

                elif g.geom_type == "Polygon":
                    c = g.centroid
                    points.append([c.x, c.y])
                    index.append(i)

                elif g.geom_type.startswith("Multi"):
                    for sub in g.geoms:
                        c = sub.centroid
                        points.append([c.x, c.y])
                        index.append(i)

            except:
                continue

        if len(points) == 0:
            self.tree = None
            self.geom_index = []
            return

        self.tree = cKDTree(np.array(points))
        self.geom_index = index

    def query(self, lon, lat, k=25):

        if self.tree is None:
            return []

        dist, idx = self.tree.query([lon, lat], k=min(k, len(self.geom_index)))

        results = []

        for d, i in zip(dist, idx):
            try:
                results.append((d * 111320, self.geom_index[i]))
            except:
                continue

        return results