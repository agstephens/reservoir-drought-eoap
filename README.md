# Reservoir drought — an `eoap-gen` example for EO DataHub

An EO Application Package that measures how much a lake or reservoir has shrunk
between winter and summer, built from plain Python scripts with
[`eoap-gen`](https://github.com/EO-DataHub/eoap-gen).

You give it **a point in the middle of a water body** and **a year**. It:

1. **finds scenes** – searches the EODH Sentinel-2 ARD catalogue (`sentinel2_ard`,
   CEDA) for a winter month (default January) and a summer month (default July),
   keeps only acquisitions in a 10:00–13:00 UTC window, and chooses the scene with
   the least cloud *over the lake itself* using the ARD cloud and valid-pixel masks;
2. **delineates the water** in each scene (run as a CWL scatter, one job per season) –
   MNDWI from B03/B11, an automatic Otsu threshold, a little morphological clean-up,
   and the connected water body under (or nearest to) your point. The window grows
   automatically if the lake is bigger than the initial 3 km half-width;
3. **compares** the two – an annotated longitude/latitude plot of both shorelines and
   the exposed bed (no basemap), the exposed area as GeoJSON, and a `summary.json`
   with areas, % change and a simple volume estimate;
4. **writes a STAC catalogue** linking every output, which is what the EODH ADES
   needs to put results into your workspace.

The defaults are **Wimbleball Lake, Exmoor** (51.067 N, 3.467 W), which the Environment
Agency classed as *exceptionally low* (54 % full) at the end of July 2026. EODH has a
1.9 %-cloud scene on 3 Jan 2026 and a 1.5 %-cloud scene on 9 Jul 2026 for this tile
(T30UVB, relative orbit 37), so the January → July 2026 run should be clean.

```
find_scenes ─► extract_water ×2 (winter, summer; scattered) ─► compare ─► make_stac ─► stac_output/
```

## Does eoap-gen make the STAC for you?

No. `eoap-gen` turns each script's CLI into a CWL `CommandLineTool`, writes a
Dockerfile per step and wires them into a workflow, but it does not create any STAC
metadata. The ADES expects the workflow's final `Directory` output to contain a
`catalog.json`, so this package has its own last step, `steps/make_stac/make_stac.py`,
that produces:

```
catalog.json
reservoir-water-extent/collection.json
  water-winter/  water-winter.json  water_winter.geojson
  water-summer/  water-summer.json  water_summer.geojson
  water-change/  water-change.json  comparison.png  exposed_area.geojson  summary.json
```

Each season item carries the acquisition datetime, the boundary polygon as its
geometry, area/perimeter/threshold, sun elevation and a `derived_from` link to the
source Sentinel-2 ARD item. The change item spans both dates.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `lat`, `lon` | 51.067, -3.467 | A point roughly in the middle of the water body (WGS84) |
| `year` | 2026 | Year to analyse |
| `winter_month`, `summer_month` | 1, 7 | Months to compare (the search also looks 14 days either side) |
| `buffer_km` | 3.0 | Initial half-width of the analysis window; grows if needed |
| `name` | Wimbleball Lake | Used in the plot title |
| `bank_slope_deg` | 10 | Bank slope assumed for the volume estimate |
| `capacity_ml` | 21000 | Full capacity in megalitres, to express the change as a % (0 = unknown) |
| `stac_url` | EODH CEDA catalogue | Any STAC API with the `sentinel2_ard` collection, e.g. `https://api.stac.ceda.ac.uk` |

Sentinel-2 ARD on EODH covers the UK only. Other reservoirs that were very low in
summer 2026 and make good tests: Blagdon Lake and Hanningfield (both also "exceptionally
low" at the end of July) and Tittesworth (about 50 % in late July). Pick the point from
a map so it lands on water; the step will snap to water up to 750 m away.

## The volume estimate (simple, by design)

Treat the reservoir as a basin whose banks slope uniformly at angle θ:

- mean shoreline retreat **r = (A_winter − A_summer) / mean perimeter**
- level drop **Δh = r · tan θ**
- volume change **ΔV = Δh · (A_winter + A_summer) / 2**

It's shown for θ and for 0.5θ–1.5θ so the uncertainty is visible on the plot. For a
steep Exmoor valley 10° is reasonable; flatter lowland reservoirs (Hanningfield,
Blagdon) are closer to 3–5°. If you know the true level change from the water company,
use that instead: `ΔV ≈ Δh_true · mean area`.

## Build and deploy

1. Push this repo to GitHub (the repo name must be lower-case so the ghcr image names are valid).
2. The workflow in `.github/workflows/build.yml` calls EODH's reusable
   `generate-reusable.yml`. It regenerates `eoap-gen-out/` (CWL + Dockerfiles),
   commits it, and pushes one image per step to `ghcr.io/<owner>/<repo>/<step>:<branch>`.
   Make those packages public (or give the ADES pull access).
3. To deploy automatically, add the secrets `ADES_USER` and `ADES_TOKEN` and the
   repository variable `DEPLOY_TO_ADES=true`. Otherwise deploy
   `eoap-gen-out/cli/workflow-packed.cwl` with `pyeodh` (see EODH's `ades.ipynb`):

```python
import pyeodh
ades = pyeodh.Client(username="you", token="...").get_ades()
ades.deploy_process(cwl_yaml=open("eoap-gen-out/cli/workflow-packed.cwl").read())
job = ades.get_process("reservoir-drought").execute(
    {"lat": 51.067, "lon": -3.467, "year": 2026}
)
```

The `eoap-gen-out/` included here was generated locally with
`--docker-url-base=ghcr.io/owner/reservoir-drought-eoap --docker-tag=main`; the
GitHub workflow overwrites it with your own registry path.

## Generate and test locally

```bash
pipx install git+https://github.com/EO-DataHub/eoap-gen
eoap-gen generate --config=config.yml --output=eoap-gen-out \
  --docker-url-base=ghcr.io/<owner>/<repo> --docker-tag=main

# Offline test of the algorithm on a synthetic reservoir (no network needed)
pip install -r steps/extract_water/requirements.txt -r steps/compare/requirements.txt \
            -r steps/make_stac/requirements.txt pystac-client
python tests/make_synthetic.py --out tests/synthetic
python tests/test_find_scenes.py
mkdir -p run && cd run
python ../steps/extract_water/extract_water.py --scenes ../tests/synthetic/scenes.json --season winter --lat 51.067 --lon -3.467
python ../steps/extract_water/extract_water.py --scenes ../tests/synthetic/scenes.json --season summer --lat 51.067 --lon -3.467
python ../steps/compare/compare.py --boundaries water_winter.geojson water_summer.geojson --lat 51.067 --lon -3.467
python ../steps/make_stac/make_stac.py --results results

# Real run against EODH (needs network)
python ../steps/find_scenes/find_scenes.py --lat 51.067 --lon -3.467 --year 2026
```

`examples/synthetic-output/` holds the outputs of that synthetic run, so you can see
what the plot and STAC catalogue look like.

## Notes and gotchas found while building this

- **Keep `click==8.1.8`.** `eoap-gen` uses `argparse2tool` to read the CLI, and with
  click ≥ 8.2 it writes `default: Sentinel.UNSET` into the CWL, which then fails to
  pack. Requirements are also passed to `pip` unquoted, so use `==` pins, not `<`.
- **Avoid `required=True` and positional `nargs=-1` arguments.** `required=True` trips the
  same Sentinel bug; a positional argument gets *no* `inputBinding`, so CWL silently
  never passes the files. The scripts use optional `--options` and check for missing
  values themselves; the two boundaries arrive as `--boundaries a b` (`nargs=2`).
- **Use underscores in option names** (`--bank_slope_deg`), so the CWL input ids match
  the ids in `config.yml`.
- **One source per step input.** `eoap-gen` doesn't add `MultipleInputFeatureRequirement`,
  so `compare` collects everything into one `results/` directory for `make_stac`.
- **Time of day:** Sentinel-2 is sun-synchronous and crosses the UK at about 11:20 UTC,
  so the 10–13 UTC window mainly guards against bad timestamps. What really changes
  is sun elevation (~15° in January vs ~60° in July at 51° N); it is recorded and shown on
  the plot. Low winter sun means long hill shadows, which is why MNDWI (green/SWIR)
  is used rather than NDWI (green/NIR).
- **Same grid:** all CEDA ARD scenes are on the British National Grid at 10 m, so the
  winter and summer windows line up pixel for pixel with no resampling.
- **ARD cloud masks aren't perfect**; check `aoi_cloud_or_nodata_fraction` in each
  boundary's properties and look at the plot before trusting a number.
