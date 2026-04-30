import pickle

class GeoEngine:

    def __init__(self, path="data/index.pkl"):

        with open(path, "rb") as f:
            self.tree, self.geom_index = pickle.load(f)

    def query(self, lon, lat, k=25):

        dist, idx = self.tree.query([lon, lat], k=k)

        results = []

        for d, i in zip(dist, idx):
            results.append((d * 111320, self.geom_index[i]))

        return results