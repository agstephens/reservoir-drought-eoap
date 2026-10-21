id: 
  file:///home/runner/work/reservoir-drought-eoap/reservoir-drought-eoap/eoap-gen-out/cli/extract_water/extract_water.cwl
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
  - "null"
  - string
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
- id: buffer_km
  doc: Initial half-width of the search window, km
  inputBinding:
    prefix: --buffer_km
  default: 3.0
  type:
  - "null"
  - float
- id: snap_m
  doc: Max distance to snap the point to water, m
  inputBinding:
    prefix: --snap_m
  default: 750.0
  type:
  - "null"
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
doc: |
  None
cwlVersion: v1.0
baseCommand:
- python
- /app/app.py
