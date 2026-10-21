"""Step 1 - find the best winter and summer Sentinel-2 ARD scenes for a water body.

Searches the EODH (CEDA) Sentinel-2 ARD STAC collection around a user-supplied
point for a winter and a summer month of a given year, keeps only acquisitions
inside a sensible time-of-day window (good sun elevation), and picks the scene
in each season with the least cloud *over the area of interest* (not just the
scene-level cloud cover), using the ARD cloud and valid-pixel masks.

Writes:
    scenes.json   - details of the chosen winter and summer scenes
    seasons.txt   - "winter" and "summer", one per line (drives the scatter step)
"""

import calendar
import datetime as dt
import json
import math

import click
import numpy as np
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds

# CEDA's Sentinel-2 ARD, as served through the EO DataHub resource catalogue.
DEFAULT_STAC = (
    "https://eodatahub.org.uk/api/catalogue/stac/catalogs/public/catalogs/"
    "ceda-stac-catalogue"
)


def solar_elevation(lat: float, lon: float, when: dt.datetime) -> float:
    """Approximate solar elevation in degrees (NOAA formulae, +/- ~0.5 deg)."""
    doy = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60 + when.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (
        0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g)
    )
    eqtime = 229.18 * (
        0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
        - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g)
    )
    tst = hour * 60 + eqtime + 4 * lon  # true solar time, minutes (UTC input)
    ha = math.radians(tst / 4 - 180)
    phi = math.radians(lat)
    cos_zen = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zen))))


def aoi_window(src, lat: float, lon: float, buffer_m: float):
    """Window of `src` covering a square of +/- buffer_m around the point."""
    x, y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(lon, lat)
    return from_bounds(x - buffer_m, y - buffer_m, x + buffer_m, y + buffer_m, src.transform)


def aoi_quality(item, lat: float, lon: float, buffer_m: float) -> tuple[float, float]:
    """Return (cloud_fraction, valid_fraction) over the AOI from the ARD masks."""
    with rasterio.open(item.assets["valid_pixels"].href) as src:
        valid = src.read(1, window=aoi_window(src, lat, lon, buffer_m), boundless=True, fill_value=0)
    valid = valid == 1
    valid_frac = float(valid.mean()) if valid.size else 0.0
    if valid_frac == 0:
        return 1.0, 0.0
    with rasterio.open(item.assets["cloud"].href) as src:
        cloud = src.read(1, window=aoi_window(src, lat, lon, buffer_m), boundless=True, fill_value=0)
        nodata = src.nodata
    cloudy = cloud > 0
    if nodata is not None:
        cloudy &= cloud != nodata
    cloud_frac = float(cloudy[valid].mean())
    return cloud_frac, valid_frac


def date_range(year: int, month: int, extend_days: int) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(
        year, month, calendar.monthrange(year, month)[1], 23, 59, 59, tzinfo=dt.timezone.utc
    )
    pad = dt.timedelta(days=extend_days)
    return start - pad, end + pad


def pick_scene(client, collection, lat, lon, year, month, season, opts) -> dict:
    start, end = date_range(year, month, opts["extend_days"])
    search = client.search(
        collections=[collection],
        intersects={"type": "Point", "coordinates": [lon, lat]},
        datetime=[start, end],
        max_items=200,
    )
    items = list(search.items())
    click.echo(f"[{season}] {len(items)} scenes found {start:%Y-%m-%d} -> {end:%Y-%m-%d}")

    candidates = []
    for it in items:
        when = it.datetime
        utc_hour = when.hour + when.minute / 60
        if not (opts["utc_start_hour"] <= utc_hour <= opts["utc_end_hour"]):
            continue  # outside the daylight / high-sun acquisition window
        scene_cloud = it.properties.get("eo:cloud_cover", 0.0) or 0.0
        if scene_cloud > opts["max_scene_cloud"]:
            continue
        # Prefer dates inside the requested month, then lower scene cloud
        outside_month = 0 if when.month == month else 1
        candidates.append((outside_month, scene_cloud, it))

    if not candidates:
        raise click.ClickException(
            f"No {season} scenes passed the time-of-day / cloud filters. "
            "Try a larger extend_days or max_scene_cloud."
        )

    candidates.sort(key=lambda c: (c[0], c[1]))
    best = None
    for outside_month, scene_cloud, it in candidates[: opts["max_candidates"]]:
        try:
            cloud_frac, valid_frac = aoi_quality(it, lat, lon, opts["buffer_m"])
        except Exception as exc:  # unreadable asset: skip it
            click.echo(f"  skip {it.id}: {exc}")
            continue
        score = cloud_frac + (1 - valid_frac) + 0.05 * outside_month
        click.echo(
            f"  {it.datetime:%Y-%m-%d %H:%M}Z scene cloud {scene_cloud:5.1f}% "
            f"AOI cloud {cloud_frac:6.1%} valid {valid_frac:6.1%}"
        )
        if best is None or score < best[0]:
            best = (score, it, cloud_frac, valid_frac)
        if cloud_frac == 0 and valid_frac > 0.99 and not outside_month:
            break  # cannot do better than a perfectly clear in-month scene

    if best is None:
        raise click.ClickException(f"Could not read any {season} candidate scene.")

    _, it, cloud_frac, valid_frac = best
    sun = solar_elevation(lat, lon, it.datetime)
    click.echo(f"[{season}] chose {it.id} (sun elevation {sun:.1f} deg)")
    return {
        "season": season,
        "item_id": it.id,
        "item_href": it.get_self_href(),
        "datetime": it.datetime.isoformat().replace("+00:00", "Z"),
        "sun_elevation_deg": round(sun, 1),
        "scene_cloud_cover": it.properties.get("eo:cloud_cover"),
        "aoi_cloud_fraction": round(cloud_frac, 4),
        "aoi_valid_fraction": round(valid_frac, 4),
        "platform": it.properties.get("Platform Number"),
        "relative_orbit": it.properties.get("Start Relative Orbit Number"),
        "reflectance_href": it.assets["cog"].href,
        "cloud_href": it.assets["cloud"].href,
        "valid_href": it.assets["valid_pixels"].href,
    }


@click.command()
@click.option("--lat", type=float, help="Latitude of a point inside the water body")
@click.option("--lon", type=float, help="Longitude of a point inside the water body")
@click.option("--year", type=int, help="Year to analyse")
@click.option("--winter_month", type=int, default=1, help="Winter (high water) month, 1-12")
@click.option("--summer_month", type=int, default=7, help="Summer (low water) month, 1-12")
@click.option("--extend_days", type=int, default=14, help="Also search this many days either side of each month")
@click.option("--buffer_km", type=float, default=3.0, help="Half-width of the area of interest, km")
@click.option("--utc_start_hour", type=float, default=10.0, help="Earliest acceptable acquisition time (UTC hour)")
@click.option("--utc_end_hour", type=float, default=13.0, help="Latest acceptable acquisition time (UTC hour)")
@click.option("--max_scene_cloud", type=float, default=80.0, help="Ignore scenes cloudier than this (%)")
@click.option("--max_candidates", type=int, default=6, help="Number of scenes per season to check at AOI level")
@click.option("--stac_url", type=str, default=DEFAULT_STAC, help="STAC API holding Sentinel-2 ARD")
@click.option("--collection", type=str, default="sentinel2_ard", help="Collection id")
def main(lat, lon, year, winter_month, summer_month, extend_days, buffer_km,
         utc_start_hour, utc_end_hour, max_scene_cloud, max_candidates, stac_url, collection):
    # click options are left optional so argparse2tool can build the CWL;
    # enforce the required ones here instead
    if lat is None or lon is None or year is None:
        raise click.UsageError("Required: --lat, --lon, --year")
    client = pystac_client.Client.open(stac_url)
    opts = dict(
        extend_days=extend_days, buffer_m=buffer_km * 1000, utc_start_hour=utc_start_hour,
        utc_end_hour=utc_end_hour, max_scene_cloud=max_scene_cloud, max_candidates=max_candidates,
    )
    scenes = {
        "request": {"lat": lat, "lon": lon, "year": year, "buffer_km": buffer_km,
                    "stac_url": stac_url, "collection": collection},
        "winter": pick_scene(client, collection, lat, lon, year, winter_month, "winter", opts),
        "summer": pick_scene(client, collection, lat, lon, year, summer_month, "summer", opts),
    }
    with open("scenes.json", "w") as f:
        json.dump(scenes, f, indent=2)
    with open("seasons.txt", "w") as f:
        f.write("winter\nsummer")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
