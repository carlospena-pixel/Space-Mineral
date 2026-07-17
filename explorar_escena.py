import glob
import numpy as np
import rasterio
import matplotlib.pyplot as plt

tci = glob.glob("data/raw/*.SAFE/GRANULE/*/IMG_DATA/R10m/*_TCI_10m.jp2")[0]
print("Archivo encontrado:", tci)

with rasterio.open(tci) as src:
    print("Sistema de coordenadas:", src.crs)
    print("Tamaño real:", src.width, "x", src.height)
    factor = 10
    img = src.read(out_shape=(src.count, src.height // factor, src.width // factor))

rgb = np.transpose(img, (1, 2, 0))

plt.figure(figsize=(8, 8))
plt.imshow(rgb)
plt.axis("off")
plt.savefig("escena_rgb.png", dpi=100, bbox_inches="tight")
print("Listo: se guardo escena_rgb.png")