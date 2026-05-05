import json
import os
import numpy as np
import pickle
from shapely.geometry import shape
from scipy.spatial import cKDTree

INPUT = "test.json"
OUTPUT = "data/index.pkl"

os.makedirs("data", exist_ok=True)

with open(INPUT, "r", encoding="utf-8") as f:
    data = json.load(f)

points = []
index = []
centroids = []

for i, f in enumerate(data["features"]):

    try:
        geom = shape(f["geometry"])
        c = geom.centroid

        points.append([c.x, c.y])
        centroids.append((c.x, c.y))
        index.append(i)

    except:
        continue

tree = cKDTree(np.array(points))

with open(OUTPUT, "wb") as f:
    pickle.dump((tree, index, centroids), f)