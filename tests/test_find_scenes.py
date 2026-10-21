"""Offline test of find_scenes.py scene selection using local fake STAC items."""

import datetime as dt
import json
import os
import subprocess
import sys

import pystac

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "steps", "find_scenes"))
import find_scenes  # noqa: E402


def make_item(item_id, when, cloud_cover, refl, cloud, valid):
    it = pystac.Item(item_id, {"type": "Point", "coordinates": [-3.467, 51.067]},
                     [-3.5, 51.0, -3.4, 51.1], when, {"eo:cloud_cover": cloud_cover})
    for k, h in (("cog", refl), ("cloud", cloud), ("valid_pixels", valid)):
        it.add_asset(k, pystac.Asset(h))
    it.set_self_href(f"https://example/{item_id}.json")
    return it


def test_selection(tmp_path=None):
    syn = os.path.join(HERE, "synthetic")
    if not os.path.exists(os.path.join(syn, "scenes.json")):
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_synthetic.py"), "--out", syn])
    s = json.load(open(os.path.join(syn, "scenes.json")))
    w, su = s["winter"], s["summer"]
    # A cloudy-over-the-lake copy of the cloud mask, to check AOI-level selection
    import numpy as np
    import rasterio
    cloudy = os.path.join(syn, "cloudy_cloud.tif")
    with rasterio.open(w["cloud_href"]) as src:
        prof = src.profile
        arr = np.ones((src.height, src.width), "uint8")
    with rasterio.open(cloudy, "w", **prof) as dst:
        dst.write(arr, 1)
    utc = dt.timezone.utc
    items = [
        # low scene cloud, but cloud over the lake -> must lose
        make_item("jan-10", dt.datetime(2026, 1, 10, 11, 21, tzinfo=utc), 0.5, w["reflectance_href"], cloudy, w["valid_href"]),
        make_item("jan-03", dt.datetime(2026, 1, 3, 11, 24, tzinfo=utc), 1.9, w["reflectance_href"], w["cloud_href"], w["valid_href"]),
        # wrong time of day -> filtered out
        make_item("jan-05-night", dt.datetime(2026, 1, 5, 22, 0, tzinfo=utc), 0.0, w["reflectance_href"], w["cloud_href"], w["valid_href"]),
        make_item("jul-09", dt.datetime(2026, 7, 9, 11, 21, tzinfo=utc), 1.5, su["reflectance_href"], su["cloud_href"], su["valid_href"]),
    ]

    class FakeSearch:
        def __init__(self, dates):
            self.dates = dates

        def items(self):
            lo, hi = self.dates
            return [i for i in items if lo <= i.datetime <= hi]

    class FakeClient:
        def search(self, collections, intersects, datetime, max_items):
            return FakeSearch(datetime)

    opts = dict(extend_days=14, buffer_m=3000, utc_start_hour=10, utc_end_hour=13,
                max_scene_cloud=80, max_candidates=6)
    win = find_scenes.pick_scene(FakeClient(), "sentinel2_ard", 51.067, -3.467, 2026, 1, "winter", opts)
    summ = find_scenes.pick_scene(FakeClient(), "sentinel2_ard", 51.067, -3.467, 2026, 7, "summer", opts)
    assert win["item_id"] == "jan-03", win
    assert summ["item_id"] == "jul-09", summ
    assert 14 < win["sun_elevation_deg"] < 19, win["sun_elevation_deg"]
    assert 58 < summ["sun_elevation_deg"] < 63, summ["sun_elevation_deg"]
    print("winter:", win["item_id"], win["sun_elevation_deg"], "summer:", summ["item_id"], summ["sun_elevation_deg"])


if __name__ == "__main__":
    test_selection()
    print("OK")
