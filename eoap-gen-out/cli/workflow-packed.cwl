$graph:
- id: compare
  class: CommandLineTool
  inputs:
  - id: boundaries
    doc: The winter and summer water_*.geojson files
    inputBinding:
      prefix: --boundaries
    type:
      type: array
      items: File
  - id: lat
    doc: Latitude of the user's point
    inputBinding:
      prefix: --lat
    type:
    - 'null'
    - float
  - id: lon
    doc: Longitude of the user's point
    inputBinding:
      prefix: --lon
    type:
    - 'null'
    - float
  - id: name
    doc: Name of the water body, for the plot title
    inputBinding:
      prefix: --name
    type:
    - 'null'
    - string
  - id: bank_slope_deg
    doc: Typical bank slope for the volume estimate, degrees
    inputBinding:
      prefix: --bank_slope_deg
    default: 10.0
    type:
    - 'null'
    - float
  - id: capacity_ml
    doc: Optional full capacity in megalitres (0 = unknown)
    inputBinding:
      prefix: --capacity_ml
    default: 0.0
    type:
    - 'null'
    - float
  requirements:
  - class: DockerRequirement
    dockerPull: ghcr.io/agstephens/reservoir-drought-eoap/compare:main
  - class: InlineJavascriptRequirement
  doc: "None\n"
  baseCommand:
  - python
  - /app/app.py
  outputs:
  - id: results
    outputBinding:
      glob: results
    type: Directory
- id: extract_water
  class: CommandLineTool
  inputs:
  - id: scenes
    doc: scenes.json from find_scenes
    inputBinding:
      prefix: --scenes
    type: File
  - id: season
    doc: winter or summer
    inputBinding:
      prefix: --season
    type:
    - 'null'
    - string
  - id: lat
    doc: Latitude of a point inside the water body
    inputBinding:
      prefix: --lat
    type:
    - 'null'
    - float
  - id: lon
    doc: Longitude of a point inside the water body
    inputBinding:
      prefix: --lon
    type:
    - 'null'
    - float
  - id: buffer_km
    doc: Initial half-width of the search window, km
    inputBinding:
      prefix: --buffer_km
    default: 3.0
    type:
    - 'null'
    - float
  - id: snap_m
    doc: Max distance to snap the point to water, m
    inputBinding:
      prefix: --snap_m
    default: 750.0
    type:
    - 'null'
    - float
  outputs:
  - id: boundary
    outputBinding:
      glob: water_*.geojson
    type: File
  requirements:
  - class: DockerRequirement
    dockerPull: ghcr.io/agstephens/reservoir-drought-eoap/extract_water:main
  - class: InlineJavascriptRequirement
  doc: "None\n"
  baseCommand:
  - python
  - /app/app.py
- id: find_scenes
  class: CommandLineTool
  inputs:
  - id: lat
    doc: Latitude of a point inside the water body
    inputBinding:
      prefix: --lat
    type:
    - 'null'
    - float
  - id: lon
    doc: Longitude of a point inside the water body
    inputBinding:
      prefix: --lon
    type:
    - 'null'
    - float
  - id: year
    doc: Year to analyse
    inputBinding:
      prefix: --year
    type:
    - 'null'
    - int
  - id: winter_month
    doc: Winter (high water) month, 1-12
    inputBinding:
      prefix: --winter_month
    default: 1
    type:
    - 'null'
    - int
  - id: summer_month
    doc: Summer (low water) month, 1-12
    inputBinding:
      prefix: --summer_month
    default: 7
    type:
    - 'null'
    - int
  - id: extend_days
    doc: Also search this many days either side of each month
    inputBinding:
      prefix: --extend_days
    default: 14
    type:
    - 'null'
    - int
  - id: buffer_km
    doc: Half-width of the area of interest, km
    inputBinding:
      prefix: --buffer_km
    default: 3.0
    type:
    - 'null'
    - float
  - id: utc_start_hour
    doc: Earliest acceptable acquisition time (UTC hour)
    inputBinding:
      prefix: --utc_start_hour
    default: 10.0
    type:
    - 'null'
    - float
  - id: utc_end_hour
    doc: Latest acceptable acquisition time (UTC hour)
    inputBinding:
      prefix: --utc_end_hour
    default: 13.0
    type:
    - 'null'
    - float
  - id: max_scene_cloud
    doc: Ignore scenes cloudier than this (%)
    inputBinding:
      prefix: --max_scene_cloud
    default: 80.0
    type:
    - 'null'
    - float
  - id: max_candidates
    doc: Number of scenes per season to check at AOI level
    inputBinding:
      prefix: --max_candidates
    default: 6
    type:
    - 'null'
    - int
  - id: stac_url
    doc: STAC API holding Sentinel-2 ARD
    inputBinding:
      prefix: --stac_url
    default: 
      https://eodatahub.org.uk/api/catalogue/stac/catalogs/public/catalogs/ceda-stac-catalogue
    type:
    - 'null'
    - string
  - id: collection
    doc: Collection id
    inputBinding:
      prefix: --collection
    default: sentinel2_ard
    type:
    - 'null'
    - string
  outputs:
  - id: scenes
    outputBinding:
      glob: scenes.json
    type: File
  - id: seasons
    outputBinding:
      glob: seasons.txt
      loadContents: true
      outputEval: $(self[0].contents.split('\n'))
    type:
      items: string
      type: array
  requirements:
  - class: DockerRequirement
    dockerPull: ghcr.io/agstephens/reservoir-drought-eoap/find_scenes:main
  - class: InlineJavascriptRequirement
  doc: "None\n"
  baseCommand:
  - python
  - /app/app.py
- id: make_stac
  class: CommandLineTool
  inputs:
  - id: results
    doc: results directory from the compare step
    inputBinding:
      prefix: --results
    type: Directory
  outputs:
  - id: stac_catalog
    outputBinding:
      glob: .
    type: Directory
  requirements:
  - class: DockerRequirement
    dockerPull: ghcr.io/agstephens/reservoir-drought-eoap/make_stac:main
  - class: InlineJavascriptRequirement
  doc: "None\n"
  baseCommand:
  - python
  - /app/app.py
- id: reservoir-drought
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
  doc: "Given a point inside an inland water body and a year, selects clear Sentinel-2
    ARD scenes (EO DataHub / CEDA) for a winter and a summer month, delineates the
    water body in each with MNDWI + Otsu thresholding, and outputs both boundaries
    as GeoJSON, the exposed area, an annotated lat/lon comparison plot and a simple
    volume-change estimate, packaged as a STAC catalogue.\n"
  steps:
  - id: find_scenes
    in:
    - id: lat
      source: lat
    - id: lon
      source: lon
    - id: year
      source: year
    - id: winter_month
      source: winter_month
    - id: summer_month
      source: summer_month
    - id: buffer_km
      source: buffer_km
    - id: stac_url
      source: stac_url
    out:
    - id: scenes
    - id: seasons
    run: '#find_scenes'
  - id: extract_water
    in:
    - id: scenes
      source: find_scenes/scenes
    - id: season
      source: find_scenes/seasons
    - id: lat
      source: lat
    - id: lon
      source: lon
    - id: buffer_km
      source: buffer_km
    out:
    - id: boundary
    run: '#extract_water'
    scatter:
    - season
    scatterMethod: dotproduct
  - id: compare
    in:
    - id: boundaries
      source: extract_water/boundary
    - id: lat
      source: lat
    - id: lon
      source: lon
    - id: name
      source: name
    - id: bank_slope_deg
      source: bank_slope_deg
    - id: capacity_ml
      source: capacity_ml
    out:
    - id: results
    run: '#compare'
  - id: make_stac
    in:
    - id: results
      source: compare/results
    out:
    - id: stac_catalog
    run: '#make_stac'
cwlVersion: v1.0
