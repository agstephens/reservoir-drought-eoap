"""Create a synthetic winter/summer pair of Sentinel-2-ARD-like rasters for offline testing.

The fake reservoir is a dendritic valley lake around the given point on the
British National Grid. Each scene gets a 10-band reflectance COG (B02..B12,
like the CEDA ARD `cog` asset), a cloud mask and a valid-pixel mask, plus a
scenes.json in the format written by find_scenes.py.

    python tests/make_synthetic.py --out tests/synthetic
"""

import json
import os

import click
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from scipy import ndimage


def lake_depth(shape, rng):
    """Depth-like field: a main arm plus side valleys, deeper towards the dam."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    depth = np.full(shape, -1e3)
    arms = [  # (row0, col0, row1, col1, half-width px)
        (420, 300, 250, 330, 28), (250, 330, 120, 280, 20), (250, 330, 190, 460, 16),
        (330, 315, 360, 190, 14), (160, 300, 90, 380, 10),
    ]
    for r0, c0, r1, c1, hw in arms:
        n = 200
        rs, cs = np.linspace(r0, r1, n), np.linspace(c0, c1, n)
        line = np.zeros(shape, bool)
        line[rs.astype(int), cs.astype(int)] = True
        dist = ndimage.distance_transform_edt(~line)
        depth = np.maximum(depth, hw - dist)
    depth += ndimage.gaussian_filter(rng.normal(0, 4, shape), 6)
    depth *= 1 + (yy - 120) / h  # deeper near the dam end (south)
    return depth


@click.command()
@click.option("--out", default="tests/synthetic")
@click.option("--lat", type=float, default=51.067)
@click.option("--lon", type=float, default=-3.467)
def main(out, lat, lon):
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(1)
    shape = (600, 600)  # 6 km x 6 km at 10 m
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True).transform(lon, lat)
    # Place the grid so the user's point lands in the main arm (row ~300, col ~320)
    tfm = from_origin(round(x - 3200, -1), round(y + 3000, -1), 10, 10)
    depth = lake_depth(shape, rng)

    scenes = {"request": {"lat": lat, "lon": lon, "year": 2026, "buffer_km": 3.0}}
    for season, level, date, sun in (("winter", 0.0, "2026-01-03T11:23:59Z", 16.6),
                                      ("summer", 7.0, "2026-07-09T11:21:31Z", 60.8)):
        water = depth > level
        exposed = (depth > 0) & ~water
        refl = np.empty((10, *shape), "float32")
        land = np.array([450, 800, 600, 1300, 2600, 3000, 3200, 3300, 1900, 900])
        mud = np.array([900, 1100, 1250, 1400, 1500, 1550, 1600, 1650, 1700, 1300])
        wat = np.array([500, 650, 400, 300, 200, 180, 150, 140, 90, 60])
        for b in range(10):
            refl[b] = land[b]
            refl[b][exposed] = mud[b]
            refl[b][water] = wat[b]
        refl *= rng.normal(1, 0.06, refl.shape)
        if season == "winter":  # low sun: darken a north-facing slope a little
            refl[:, 50:150, :] *= 0.6
        refl = np.clip(refl, 1, 10000).astype("uint16")
        cloud = np.zeros(shape, "uint8")
        cloud[30:80, 480:560] = 1  # small cloud away from the lake
        valid = np.ones(shape, "uint8")

        profile = dict(driver="GTiff", width=shape[1], height=shape[0], crs="EPSG:27700",
                       transform=tfm, tiled=True, blockxsize=256, blockysize=256, compress="deflate")
        paths = {k: os.path.abspath(f"{out}/{season}_{k}.tif") for k in ("refl", "cloud", "valid")}
        with rasterio.open(paths["refl"], "w", count=10, dtype="uint16", nodata=0, **profile) as dst:
            dst.write(refl)
        for k, arr in (("cloud", cloud), ("valid", valid)):
            with rasterio.open(paths[k], "w", count=1, dtype="uint8", **profile) as dst:
                dst.write(arr, 1)
        scenes[season] = {
            "season": season, "item_id": f"synthetic-{season}", "item_href": None,
            "datetime": date, "sun_elevation_deg": sun, "scene_cloud_cover": 1.0,
            "aoi_cloud_fraction": float(cloud.mean()), "aoi_valid_fraction": 1.0,
            "reflectance_href": paths["refl"], "cloud_href": paths["cloud"], "valid_href": paths["valid"],
        }
        print(f"{season}: true water area {water.sum() * 100 / 1e6:.3f} km2")
    with open(f"{out}/scenes.json", "w") as f:
        json.dump(scenes, f, indent=2)


if __name__ == "__main__":
    main()
