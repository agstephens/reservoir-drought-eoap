"""Step 3 - compare winter and summer water boundaries.

Produces, in ./results/:
    water_winter.geojson, water_summer.geojson  - the input boundaries (copied)
    exposed_area.geojson                         - land exposed between the dates
    comparison.png                               - annotated lat/lon plot
    summary.json                                 - areas, change and volume estimate

Volume estimate (deliberately simple, order-of-magnitude only):
    mean shoreline retreat  r  = (A_winter - A_summer) / mean perimeter
    level drop             dh  = r * tan(bank slope)
    volume change          dV  = dh * (A_winter + A_summer) / 2
i.e. the reservoir is treated as a basin whose banks slope uniformly at the
given angle. The result is shown for the chosen slope and for half/1.5x that
slope so the uncertainty is visible.
"""

import json
import math
import os
import shutil

import click
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch, PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from pyproj import Transformer  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402
from shapely import transform as _shp_transform  # noqa: E402


def shp_transform(func, geom):
    """Reproject a shapely geometry with a pyproj Transformer.transform."""
    return _shp_transform(geom, lambda xy: np.column_stack(func(xy[:, 0], xy[:, 1])))


# Validated categorical hues (slot 1 blue, slot 2 orange) + neutral ink
WINTER, WINTER_FILL = "#2a78d6", "#cde2fb"
SUMMER = "#eb6834"
EXPOSED = "#c9a66b"
INK, INK_2, INK_3 = "#1f1f1e", "#55544f", "#8a8983"


def load(path):
    with open(path) as f:
        feat = json.load(f)["features"][0]
    return shape(feat["geometry"]), feat["properties"]


def volume_change(a_w, a_s, p_w, p_s, slope_deg):
    retreat = (a_w - a_s) / ((p_w + p_s) / 2)
    dh = retreat * math.tan(math.radians(slope_deg))
    return retreat, dh, dh * (a_w + a_s) / 2


def polys(geom):
    return list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]


def draw(ax, geom, **kw):
    """Fill polygons, honouring holes (islands) via a compound path."""
    for p in polys(geom):
        if p.is_empty:
            continue
        verts, codes = [], []
        for ring in [p.exterior, *p.interiors]:
            xy = list(ring.coords)
            verts += xy
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(xy) - 2) + [MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(verts, codes), **kw))


def outline(ax, geom, **kw):
    for p in polys(geom):
        ax.plot(*p.exterior.xy, **kw)
        kw.pop("label", None)
        for ring in p.interiors:
            ax.plot(*ring.xy, **kw)


def deg_fmt(hemi_pos, hemi_neg):
    return FuncFormatter(lambda v, _: f"{abs(v):.3f}°{hemi_pos if v >= 0 else hemi_neg}")


@click.command()
@click.option("--boundaries", nargs=2, type=str, help="The winter and summer water_*.geojson files")
@click.option("--lat", type=float, help="Latitude of the user's point")
@click.option("--lon", type=float, help="Longitude of the user's point")
@click.option("--name", type=str, default="", help="Name of the water body, for the plot title")
@click.option("--bank_slope_deg", type=float, default=10.0, help="Typical bank slope for the volume estimate, degrees")
@click.option("--capacity_ml", type=float, default=0.0, help="Optional full capacity in megalitres (0 = unknown)")
def main(boundaries, lat, lon, name, bank_slope_deg, capacity_ml):
    # click options are left optional so argparse2tool can build the CWL;
    # enforce the required ones here instead
    if boundaries is None or lat is None or lon is None:
        raise click.UsageError("Required: --lat, --lon")
    os.makedirs("results", exist_ok=True)
    data = {}
    for path in boundaries:
        geom, props = load(path)
        data[props["season"]] = (geom, props)
        shutil.copy(path, os.path.join("results", os.path.basename(path)))
    (g_w, p_w), (g_s, p_s) = data["winter"], data["summer"]

    # Geometry in metres on the ARD grid for the change polygon
    to_grid = Transformer.from_crs("EPSG:4326", p_w["grid_crs"], always_xy=True)
    to_ll = Transformer.from_crs(p_w["grid_crs"], "EPSG:4326", always_xy=True)
    gw_m, gs_m = (shp_transform(to_grid.transform, g) for g in (g_w, g_s))
    exposed_m = gw_m.difference(gs_m).buffer(0)
    exposed_ll = shp_transform(to_ll.transform, exposed_m)

    a_w, a_s = p_w["area_m2"], p_s["area_m2"]
    d_area = a_w - a_s
    retreat, dh, dv = volume_change(a_w, a_s, p_w["perimeter_m"], p_s["perimeter_m"], bank_slope_deg)
    _, dh_lo, dv_lo = volume_change(a_w, a_s, p_w["perimeter_m"], p_s["perimeter_m"], bank_slope_deg * 0.5)
    _, dh_hi, dv_hi = volume_change(a_w, a_s, p_w["perimeter_m"], p_s["perimeter_m"], bank_slope_deg * 1.5)

    summary = {
        "name": name,
        "point": {"lat": lat, "lon": lon},
        "winter": {k: p_w[k] for k in ("datetime", "source_item_id", "area_m2", "perimeter_m", "sun_elevation_deg")},
        "summer": {k: p_s[k] for k in ("datetime", "source_item_id", "area_m2", "perimeter_m", "sun_elevation_deg")},
        "area_change_m2": round(-d_area, 1),
        "area_change_percent": round(-100 * d_area / a_w, 2),
        "exposed_area_m2": round(exposed_m.area, 1),
        "volume_estimate": {
            "method": "uniform bank slope: dh = (dA / mean perimeter) * tan(slope); dV = dh * mean area",
            "bank_slope_deg": bank_slope_deg,
            "mean_shoreline_retreat_m": round(retreat, 1),
            "level_drop_m": round(dh, 2),
            "level_drop_range_m": [round(dh_lo, 2), round(dh_hi, 2)],
            "volume_change_m3": round(-dv),
            "volume_change_range_m3": [round(-dv_hi), round(-dv_lo)],
            "volume_change_megalitres": round(-dv / 1000, 0),
        },
    }
    if capacity_ml > 0:
        summary["volume_estimate"]["volume_change_percent_of_capacity"] = round(-100 * dv / 1000 / capacity_ml, 1)

    with open("results/summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open("results/exposed_area.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": mapping(exposed_ll),
            "properties": {"description": "Water in winter, dry in summer",
                           "area_m2": round(exposed_m.area, 1),
                           "start_datetime": p_w["datetime"], "end_datetime": p_s["datetime"]}}]}, f)

    # ------------------------------------------------------------------ plot
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.edgecolor": INK_3, "axes.labelcolor": INK_2,
                         "xtick.color": INK_2, "ytick.color": INK_2})
    fig = plt.figure(figsize=(12.5, 8), dpi=150)
    ax = fig.add_axes([0.08, 0.13, 0.55, 0.74])
    side = fig.add_axes([0.67, 0.13, 0.31, 0.74])
    side.axis("off")
    draw(ax, g_w, facecolor=WINTER_FILL, lw=0, zorder=1)
    draw(ax, exposed_ll, facecolor=EXPOSED, edgecolor="#8c6d3a", hatch="////", lw=0, alpha=0.85, zorder=2)
    outline(ax, g_w, color=WINTER, lw=2, zorder=4)
    outline(ax, g_s, color=SUMMER, lw=2, ls=(0, (4, 2)), zorder=5)
    ax.plot(lon, lat, marker="+", ms=12, mew=2, color=INK, zorder=6)
    ax.annotate("input point", (lon, lat), xytext=(8, 8), textcoords="offset points",
                color=INK, fontsize=9, zorder=7,
                path_effects=[patheffects.withStroke(linewidth=3, foreground="white")])

    # Correct aspect so 1 km north = 1 km east on the page
    ax.set_aspect(1 / math.cos(math.radians(lat)))
    minx, miny, maxx, maxy = g_w.union(g_s).bounds
    padx, pady = (maxx - minx) * 0.08, (maxy - miny) * 0.08
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)
    ax.xaxis.set_major_formatter(deg_fmt("E", "W"))
    ax.yaxis.set_major_formatter(deg_fmt("N", "S"))
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(color="#e4e3df", lw=0.6, zorder=0)
    ax.tick_params(axis="x", labelrotation=30)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # Scale bar (1 km or less) and north arrow, in axes corner
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    km_deg = 1 / (111.32 * math.cos(math.radians(lat)))
    span_km = (x1 - x0) / km_deg
    bar_km = next(b for b in (5, 2, 1, 0.5, 0.25, 0.1) if b <= span_km / 4)
    bx, by = x0 + 0.04 * (x1 - x0), y0 + 0.05 * (y1 - y0)
    ax.plot([bx, bx + bar_km * km_deg], [by, by], color=INK, lw=3, solid_capstyle="butt")
    ax.text(bx + bar_km * km_deg / 2, by + 0.015 * (y1 - y0),
            f"{bar_km:g} km", ha="center", va="bottom", color=INK, fontsize=9)
    ax.annotate("N", xy=(0.96, 0.95), xytext=(0.96, 0.85), xycoords="axes fraction",
                ha="center", va="center", fontsize=11, fontweight="bold", color=INK,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.5))

    d_w, d_s = p_w["datetime"][:10], p_s["datetime"][:10]
    t_w, t_s = p_w["datetime"][11:16], p_s["datetime"][11:16]
    handles = [
        Patch(facecolor=WINTER_FILL, edgecolor="none", label="Water on both dates"),
        Line2D([], [], color=WINTER, lw=2,
               label=f"Winter shoreline\n{d_w} {t_w} UTC · {a_w/1e6:.3f} km²"),
        Line2D([], [], color=SUMMER, lw=2, ls=(0, (4, 2)),
               label=f"Summer shoreline\n{d_s} {t_s} UTC · {a_s/1e6:.3f} km²"),
        Patch(facecolor=EXPOSED, edgecolor="#8c6d3a", hatch="////",
              label=f"Exposed bed (water lost)\n{exposed_m.area/1e6:.3f} km²"),
    ]
    side.legend(handles=handles, loc="upper left", frameon=False, fontsize=9.5,
                labelcolor=INK, title="Key", title_fontsize=10.5, alignment="left",
                handlelength=2.6, borderaxespad=0)

    ve = summary["volume_estimate"]
    lines = [
        f"Surface area change: {-d_area/1e6:+.3f} km²  ({summary['area_change_percent']:+.1f}%)",
        f"Mean shoreline retreat: {retreat:.0f} m",
        f"Est. level drop: {dh:.1f} m  (range {dh_lo:.1f}–{dh_hi:.1f} m)",
        f"Est. volume change: {-dv/1e6:+.2f} million m³\n    ({-dv/1000:+,.0f} megalitres)",
        f"    range {-dv_hi/1e6:+.2f} to {-dv_lo/1e6:+.2f} million m³",
    ]
    if capacity_ml > 0:
        lines.append(f"   ≈ {ve['volume_change_percent_of_capacity']:+.0f}% of {capacity_ml:,.0f} ML capacity")
    lines.append(f"Volume assumes uniform {bank_slope_deg:g}° banks\n(range {bank_slope_deg*0.5:g}–{bank_slope_deg*1.5:g}°); order of magnitude only")
    side.text(0, 0.60, "Change, winter → summer", transform=side.transAxes,
              fontsize=10.5, fontweight="bold", color=INK, va="bottom")
    side.text(0, 0.58, "\n".join(lines), transform=side.transAxes, ha="left", va="top",
              fontsize=9.5, color=INK, linespacing=1.6,
              bbox=dict(boxstyle="round,pad=0.6", facecolor="#f6f5f2", edgecolor="#d8d7d2"))

    title = name or f"Water body at {lat:.4f}°, {lon:.4f}°"
    fig.suptitle(f"{title}: winter vs summer water extent", x=0.02, ha="left",
                 fontsize=15, fontweight="bold", color=INK, y=0.975)
    fig.text(0.02, 0.925,
             f"Sentinel-2 ARD (CEDA, via EO DataHub) · MNDWI + Otsu threshold · "
             f"sun elevation {p_w['sun_elevation_deg']:.0f}° (winter), {p_s['sun_elevation_deg']:.0f}° (summer)",
             fontsize=9.5, color=INK_2, ha="left")
    fig.savefig("results/comparison.png", facecolor="white")
    click.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
