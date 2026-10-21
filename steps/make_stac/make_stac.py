"""Step 4 - wrap the results in a STAC catalogue for the EODH workspace.

eoap-gen does not create STAC metadata itself: the EODH ADES expects the
workflow's final Directory output to contain a STAC catalog.json that links to
every file you want to appear in your workspace. This step builds one:

    catalog.json
    reservoir-water-extent/collection.json
        water-winter/   item + water_winter.geojson
        water-summer/   item + water_summer.geojson
        water-change/   item + comparison.png, exposed_area.geojson, summary.json
"""

import datetime as dt
import json
import os
import shutil

import click
import pystac
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

GEOJSON = "application/geo+json"
COLLECTION_ID = "reservoir-water-extent"
EXTENSIONS = [
    "https://stac-extensions.github.io/file/v2.1.0/schema.json",
    "https://stac-extensions.github.io/view/v1.0.0/schema.json",
]


def read_fc(path):
    with open(path) as f:
        feat = json.load(f)["features"][0]
    return shape(feat["geometry"]), feat["properties"]


def add_file(item, key, src, media_type, roles, title):
    # Files sit next to the item JSON written by normalize_hrefs("./")
    dest_dir = os.path.join(COLLECTION_ID, item.id)
    os.makedirs(dest_dir, exist_ok=True)
    dest = shutil.copy(src, dest_dir)
    item.add_asset(key, pystac.Asset(
        href=f"./{os.path.basename(dest)}", media_type=media_type, roles=roles, title=title,
        extra_fields={"file:size": os.path.getsize(dest)},
    ))


@click.command()
@click.option("--results", type=str, help="results directory from the compare step")
def main(results):
    # click options are left optional so argparse2tool can build the CWL;
    # enforce the required ones here instead
    if results is None:
        raise click.UsageError("Required: --results")
    now = pystac.utils.datetime_to_str(dt.datetime.now(dt.timezone.utc))
    with open(os.path.join(results, "summary.json")) as f:
        summary = json.load(f)

    items = []
    geoms = []
    for season in ("winter", "summer"):
        path = os.path.join(results, f"water_{season}.geojson")
        geom, props = read_fc(path)
        geoms.append(geom)
        item = pystac.Item(
            id=f"water-{season}",
            geometry=mapping(geom),
            bbox=list(geom.bounds),
            datetime=pystac.utils.str_to_datetime(props["datetime"]),
            stac_extensions=EXTENSIONS,
            properties={
                "title": f"{season.title()} water extent",
                "description": f"Water body boundary from Sentinel-2 ARD ({props['method']})",
                "created": now, "updated": now,
                "constellation": "sentinel-2",
                "water:area_m2": props["area_m2"],
                "water:perimeter_m": props["perimeter_m"],
                "water:mndwi_threshold": props["mndwi_threshold"],
                "view:sun_elevation": props["sun_elevation_deg"],
                "sentinel2:source_item": props["source_item_id"],
            },
        )
        if props.get("source_item_href"):
            item.add_link(pystac.Link("derived_from", props["source_item_href"], "application/json"))
        add_file(item, "boundary", path, GEOJSON, ["data"], f"{season.title()} water boundary (EPSG:4326)")
        items.append(item)

    footprint = unary_union(geoms)
    start = pystac.utils.str_to_datetime(summary["winter"]["datetime"])
    end = pystac.utils.str_to_datetime(summary["summer"]["datetime"])
    lo, hi = sorted((start, end))
    ve = summary["volume_estimate"]
    change = pystac.Item(
        id="water-change",
        geometry=mapping(box(*footprint.bounds)),
        bbox=list(footprint.bounds),
        datetime=None,
        start_datetime=lo,
        end_datetime=hi,
        stac_extensions=EXTENSIONS[:1],
        properties={
            "title": f"{summary.get('name') or 'Water body'}: winter vs summer change",
            "created": now, "updated": now,
            "water:area_change_m2": summary["area_change_m2"],
            "water:area_change_percent": summary["area_change_percent"],
            "water:level_drop_estimate_m": ve["level_drop_m"],
            "water:volume_change_estimate_m3": ve["volume_change_m3"],
        },
    )
    add_file(change, "plot", os.path.join(results, "comparison.png"), pystac.MediaType.PNG,
             ["overview", "visual"], "Annotated comparison of winter and summer shorelines")
    add_file(change, "exposed_area", os.path.join(results, "exposed_area.geojson"), GEOJSON,
             ["data"], "Area that was water in winter and dry in summer")
    add_file(change, "summary", os.path.join(results, "summary.json"), pystac.MediaType.JSON,
             ["metadata"], "Areas, change statistics and simple volume estimate")
    items.append(change)

    collection = pystac.Collection(
        id=COLLECTION_ID,
        title="Reservoir water extent (winter vs summer)",
        description="Water boundaries delineated from Sentinel-2 ARD and their seasonal change.",
        extent=pystac.Extent(
            pystac.SpatialExtent([list(footprint.bounds)]),
            pystac.TemporalExtent([[lo, hi]]),
        ),
        license="other",
    )
    for it in items:
        collection.add_item(it)

    catalog = pystac.Catalog(id="catalog", description="Reservoir drought workflow outputs")
    catalog.add_child(collection)
    catalog.normalize_hrefs("./")
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)
    click.echo(f"STAC catalogue written with {len(items)} items")


if __name__ == "__main__":
    main()
