id: reservoir-drought
class: Workflow
inputs:
- id: lat
  label: Latitude
  doc: Latitude (WGS84) of a point roughly in the middle of the water body
  default: 51.067
  type: float
- id: lon
  label: Longitude
  doc: Longitude (WGS84) of a point roughly in the middle of the water body
  default: -3.467
  type: float
- id: year
  label: Year
  doc: Year to analyse
  default: 2026
  type: int
- id: winter_month
  label: Winter month
  doc: Month (1-12) used for the high-water scene
  default: 1
  type: int
- id: summer_month
  label: Summer month
  doc: Month (1-12) used for the low-water scene
  default: 7
  type: int
- id: buffer_km
  label: Search half-width (km)
  doc: Initial half-width of the analysis window; it grows automatically for 
    large lakes
  default: 3.0
  type: float
- id: name
  label: Water body name
  doc: Name used in the plot title (optional)
  default: Wimbleball Lake
  type: string
- id: bank_slope_deg
  label: Bank slope (degrees)
  doc: Typical bank slope used for the simple volume-change estimate
  default: 10.0
  type: float
- id: capacity_ml
  label: Capacity (ML)
  doc: Optional full capacity in megalitres, to express the change as a 
    percentage (0 = unknown)
  default: 21000.0
  type: float
- id: stac_url
  label: STAC API
  doc: STAC API holding the sentinel2_ard collection
  default: 
    https://eodatahub.org.uk/api/catalogue/stac/catalogs/public/catalogs/ceda-stac-catalogue
  type: string
outputs:
- id: stac_output
  outputSource:
  - make_stac/stac_catalog
  type: Directory
requirements:
- class: ScatterFeatureRequirement
- class: ResourceRequirement
  coresMin: 1
  ramMin: 2048
label: Reservoir drought - winter vs summer water extent
doc: >
  Given a point inside an inland water body and a year, selects clear Sentinel-2 ARD
  scenes (EO DataHub / CEDA) for a winter and a summer month, delineates the water
  body in each with MNDWI + Otsu thresholding, and outputs both boundaries as
  GeoJSON, the exposed area, an annotated lat/lon comparison plot and a simple
  volume-change estimate, packaged as a STAC catalogue.
cwlVersion: v1.0
steps:
- id: find_scenes
  in:
  - id: lat
    source: reservoir-drought/lat
  - id: lon
    source: reservoir-drought/lon
  - id: year
    source: reservoir-drought/year
  - id: winter_month
    source: reservoir-drought/winter_month
  - id: summer_month
    source: reservoir-drought/summer_month
  - id: buffer_km
    source: reservoir-drought/buffer_km
  - id: stac_url
    source: reservoir-drought/stac_url
  out:
  - id: scenes
  - id: seasons
  run: 
    /home/runner/work/reservoir-drought-eoap/reservoir-drought-eoap/eoap-gen-out/cli/find_scenes/find_scenes.cwl
- id: extract_water
  in:
  - id: scenes
    source: find_scenes/scenes
  - id: season
    source: find_scenes/seasons
  - id: lat
    source: reservoir-drought/lat
  - id: lon
    source: reservoir-drought/lon
  - id: buffer_km
    source: reservoir-drought/buffer_km
  out:
  - id: boundary
  run: 
    /home/runner/work/reservoir-drought-eoap/reservoir-drought-eoap/eoap-gen-out/cli/extract_water/extract_water.cwl
  scatter:
  - season
  scatterMethod: dotproduct
- id: compare
  in:
  - id: boundaries
    source: extract_water/boundary
  - id: lat
    source: reservoir-drought/lat
  - id: lon
    source: reservoir-drought/lon
  - id: name
    source: reservoir-drought/name
  - id: bank_slope_deg
    source: reservoir-drought/bank_slope_deg
  - id: capacity_ml
    source: reservoir-drought/capacity_ml
  out:
  - id: results
  run: 
    /home/runner/work/reservoir-drought-eoap/reservoir-drought-eoap/eoap-gen-out/cli/compare/compare.cwl
- id: make_stac
  in:
  - id: results
    source: compare/results
  out:
  - id: stac_catalog
  run: 
    /home/runner/work/reservoir-drought-eoap/reservoir-drought-eoap/eoap-gen-out/cli/make_stac/make_stac.cwl
