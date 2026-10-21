id: 
  eoap-gen-out/cli/find_scenes/find_scenes.cwl
class: CommandLineTool
inputs:
- id: lat
  doc: Latitude of a point inside the water body
  inputBinding:
    prefix: --lat
  type:
  - "null"
  - float
- id: lon
  doc: Longitude of a point inside the water body
  inputBinding:
    prefix: --lon
  type:
  - "null"
  - float
- id: year
  doc: Year to analyse
  inputBinding:
    prefix: --year
  type:
  - "null"
  - int
- id: winter_month
  doc: Winter (high water) month, 1-12
  inputBinding:
    prefix: --winter_month
  default: 1
  type:
  - "null"
  - int
- id: summer_month
  doc: Summer (low water) month, 1-12
  inputBinding:
    prefix: --summer_month
  default: 7
  type:
  - "null"
  - int
- id: extend_days
  doc: Also search this many days either side of each month
  inputBinding:
    prefix: --extend_days
  default: 14
  type:
  - "null"
  - int
- id: buffer_km
  doc: Half-width of the area of interest, km
  inputBinding:
    prefix: --buffer_km
  default: 3.0
  type:
  - "null"
  - float
- id: utc_start_hour
  doc: Earliest acceptable acquisition time (UTC hour)
  inputBinding:
    prefix: --utc_start_hour
  default: 10.0
  type:
  - "null"
  - float
- id: utc_end_hour
  doc: Latest acceptable acquisition time (UTC hour)
  inputBinding:
    prefix: --utc_end_hour
  default: 13.0
  type:
  - "null"
  - float
- id: max_scene_cloud
  doc: Ignore scenes cloudier than this (%)
  inputBinding:
    prefix: --max_scene_cloud
  default: 80.0
  type:
  - "null"
  - float
- id: max_candidates
  doc: Number of scenes per season to check at AOI level
  inputBinding:
    prefix: --max_candidates
  default: 6
  type:
  - "null"
  - int
- id: stac_url
  doc: STAC API holding Sentinel-2 ARD
  inputBinding:
    prefix: --stac_url
  default: 
    https://eodatahub.org.uk/api/catalogue/stac/catalogs/public/catalogs/ceda-stac-catalogue
  type:
  - "null"
  - string
- id: collection
  doc: Collection id
  inputBinding:
    prefix: --collection
  default: sentinel2_ard
  type:
  - "null"
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
  dockerPull: ghcr.io/owner/reservoir-drought-eoap/find_scenes:main
- class: InlineJavascriptRequirement
doc: |
  None
cwlVersion: v1.0
baseCommand:
- python
- /app/app.py
