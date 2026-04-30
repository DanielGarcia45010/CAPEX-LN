import json
import os
from pathlib import Path
from shapely.geometry import shape
import numpy as np
import pickle
from scipy.spatial import cKDTree

# 🔥 ARCHIVO EN DESCARGAS
INPUT = str(Path("C:/Users/1872643/Downloads/test.json"))
OUTPUT = "data/index.pkl"

os.makedirs("data", exist_ok=True)

print(f"Loading file from: {INPUT}")

if not os.path.exists(INPUT):
    raise FileNotFoundError(f"No se encontró el archivo en {INPUT}")

with open(INPUT, "r", encoding="utf-8") as f:
    data = json.load(f)

features = data["features"]

points = []
index = []

print(f"Features: {len(features)}")

for i, f in enumerate(features):

    try:
        geom = shape(f["geometry"])
        c = geom.centroid

        points.append([c.x, c.y])
        index.append(i)

    except:
        continue

    if i % 500 == 0:
        print(f"Processed {i}/{len(features)}")

print("Building KDTree...")

tree = cKDTree(np.array(points))

with open(OUTPUT, "wb") as f:
    pickle.dump((tree, index), f)

print("DONE ✅ index saved:", OUTPUT)