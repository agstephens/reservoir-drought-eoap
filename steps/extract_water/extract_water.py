"""Step 2 - delineate the water body around a point in one Sentinel-2 ARD scene.

Method (deliberately simple):
  1. Read green (B03) and SWIR-1 (B11) reflectance for a square window around
     the point, straight from the ARD Cloud-Optimised GeoTIFF (10 m, British
     National Grid), plus the ARD cloud and valid-pixel masks.
  2. Compute the Modified Normalised Difference Water Index
     MNDWI = (green - swir) / (green + swir); water is bright, land/vegetation dark.
  3. Pick a threshold automatically with Otsu's method (clamped to a sane range).
  4. Clean the mask (open, fill small holes), keep only the connected water body
     that contains (or is nearest to) the user's point.
  5. Polygonise and write a GeoJSON boundary (EPSG:4326) with area/perimeter.

If the water body touches the edge of the window the window is doubled and the
step repeats, so the user does not need to know the size of the lake.

Writes: water_<season>.geojson
"""

import json

import click
import numpy as np
import rasterio
import shapely
from pyproj import Transformer
from rasterio.features import shapes
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import mapping, shape
from shapely import transform as _shp_transform

from shapely.ops import unary_union

def shp_transform(func, geom):
    """Reproject a shapely geometry with a pyproj Transformer.transform."""
    return _shp_transform(geom, lambda xy: np.column_stack(func(xy[:, 0], xy[:, 1])))


GREEN, SWIR1 = 2, 9  # 1-based band indexes in the ARD reflectance COG (B02..B12)


def otsu(values: np.ndarray, bins: int = 256) -> float:
    """Otsu's threshold for a 1-D array of finite values."""
    hist, edges = np.histogram(values, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centres) / np.maximum(w0, 1)
    m1 = (np.sum(hist * centres) - np.cumsum(hist * centres)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centres[np.argmax(between)])


def read_window(href, x, y, half, bands=None):
    with rasterio.open(href) as src:
        win = from_bounds(x - half, y - half, x + half, y + half, src.transform)
        data = src.read(bands or 1, window=win, boundless=True, fill_value=0)
        return data, src.window_transform(win), src.crs


def delineate(scene: dict, lat: float, lon: float, half: float, snap_m: float) -> dict:
    with rasterio.open(scene["reflectance_href"]) as src:
        crs = src.crs
    to_grid = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x, y = to_grid.transform(lon, lat)

    refl, tfm, _ = read_window(scene["reflectance_href"], x, y, half, [GREEN, SWIR1])
    cloud, _, _ = read_window(scene["cloud_href"], x, y, half)
    valid, _, _ = read_window(scene["valid_href"], x, y, half)

    green, swir = refl.astype("float32")
    ok = (valid == 1) & (green > 0) & (swir > 0) & (cloud == 0)
    mndwi = np.where(ok, (green - swir) / (green + swir), np.nan)
    if ok.sum() < 100:
        raise click.ClickException("Area of interest is almost entirely cloud / no data.")

    thr = float(np.clip(otsu(mndwi[ok]), -0.15, 0.35))
    water = ok & (mndwi > thr)
    water = ndimage.binary_opening(water, iterations=1)
    # Fill holes smaller than ~0.5 ha (boats, buoys, mixed pixels); keep real islands
    holes = ndimage.binary_fill_holes(water) & ~water
    lab_h, n_h = ndimage.label(holes)
    if n_h:
        sizes = ndimage.sum(holes, lab_h, range(1, n_h + 1))
        water |= np.isin(lab_h, np.where(sizes < 50)[0] + 1)

    labels, n = ndimage.label(water)  # 4-connectivity: narrow rivers do not leak in
    if n == 0:
        raise click.ClickException("No water found around the point.")
    fcol, frow = ~tfm * (x, y)  # inverse affine gives (col, row)
    row, col = int(frow), int(fcol)
    target = labels[row, col] if 0 <= row < labels.shape[0] and 0 <= col < labels.shape[1] else 0
    if target == 0:  # point not on water (e.g. low summer level): snap to nearest water
        dist, (ri, ci) = ndimage.distance_transform_edt(labels == 0, return_indices=True)
        if dist[row, col] * abs(tfm.a) > snap_m:
            raise click.ClickException(
                f"No water within {snap_m:.0f} m of the point; check lat/lon."
            )
        target = labels[ri[row, col], ci[row, col]]
    body = labels == target

    touches_edge = bool(body[0].any() or body[-1].any() or body[:, 0].any() or body[:, -1].any())
    polys = [shape(g) for g, v in shapes(body.astype("uint8"), mask=body, transform=tfm) if v == 1]
    geom = unary_union(polys)
    return {
        "geom_grid": geom,
        "crs": crs,
        "threshold": thr,
        "touches_edge": touches_edge,
        "cloud_fraction_aoi": float(1 - ok[valid == 1].mean()) if (valid == 1).any() else 1.0,
        "pixel_size_m": abs(tfm.a),
    }


@click.command()
@click.option("--scenes", type=str, help="scenes.json from find_scenes")
@click.option("--season", type=str, help="winter or summer")
@click.option("--lat", type=float, help="Latitude of a point inside the water body")
@click.option("--lon", type=float, help="Longitude of a point inside the water body")
@click.option("--buffer_km", type=float, default=3.0, help="Initial half-width of the search window, km")
@click.option("--snap_m", type=float, default=750.0, help="Max distance to snap the point to water, m")
def main(scenes, season, lat, lon, buffer_km, snap_m):
    # click options are left optional so argparse2tool can build the CWL;
    # enforce the required ones here instead
    if scenes is None or season is None or lat is None or lon is None:
        raise click.UsageError("Required: --scenes, --season, --lat, --lon")
    with open(scenes) as f:
        scene = json.load(f)[season]

    half = buffer_km * 1000
    for _ in range(4):  # grow the window if the lake is bigger than it
        res = delineate(scene, lat, lon, half, snap_m)
        if not res["touches_edge"]:
            break
        click.echo(f"Water body reaches window edge at {half/1000:.1f} km; enlarging window.")
        half *= 2

    geom = res["geom_grid"]
    to_wgs = Transformer.from_crs(res["crs"], "EPSG:4326", always_xy=True)
    simple = geom.simplify(res["pixel_size_m"] / 2, preserve_topology=True)
    geom_ll = shapely.set_precision(shp_transform(to_wgs.transform, simple), 1e-7)

    props = {
        "season": season,
        "datetime": scene["datetime"],
        "source_item_id": scene["item_id"],
        "source_item_href": scene["item_href"],
        "sun_elevation_deg": scene["sun_elevation_deg"],
        "area_m2": round(geom.area, 1),  # measured on the 10 m grid (BNG, metres)
        "perimeter_m": round(simple.length, 1),  # of the de-staircased outline
        "mndwi_threshold": round(res["threshold"], 4),
        "aoi_cloud_or_nodata_fraction": round(res["cloud_fraction_aoi"], 4),
        "reaches_window_edge": res["touches_edge"],
        "method": "MNDWI (B03,B11) + Otsu threshold, connected component at point",
        "grid_crs": str(res["crs"]),
    }
    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(geom_ll), "properties": props}],
    }
    out = f"water_{season}.geojson"
    with open(out, "w") as f:
        json.dump(fc, f)
    click.echo(f"{season}: {props['area_m2']/1e6:.3f} km2, threshold {props['mndwi_threshold']} -> {out}")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
