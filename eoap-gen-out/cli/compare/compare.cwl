id: 
  file:///home/runner/work/reservoir-drought-eoap/reservoir-drought-eoap/eoap-gen-out/cli/compare/compare.cwl
class: CommandLineTool
inputs:
- id: boundaries
  doc: The winter and summer water_*.geojson files
  inputBinding:
    prefix: --boundaries
  type: File[]
- id: lat
  doc: Latitude of the user's point
  inputBinding:
    prefix: --lat
  type:
  - "null"
  - float
- id: lon
  doc: Longitude of the user's point
  inputBinding:
    prefix: --lon
  type:
  - "null"
  - float
- id: name
  doc: Name of the water body, for the plot title
  inputBinding:
    prefix: --name
  type:
  - "null"
  - string
- id: bank_slope_deg
  doc: Typical bank slope for the volume estimate, degrees
  inputBinding:
    prefix: --bank_slope_deg
  default: 10.0
  type:
  - "null"
  - float
- id: capacity_ml
  doc: Optional full capacity in megalitres (0 = unknown)
  inputBinding:
    prefix: --capacity_ml
  default: 0.0
  type:
  - "null"
  - float
outputs:
- id: results
  outputBinding:
    glob: results
  type: Directory
requirements:
- class: DockerRequirement
  dockerPull: ghcr.io/agstephens/reservoir-drought-eoap/compare:main
- class: InlineJavascriptRequirement
doc: |
  None
cwlVersion: v1.0
baseCommand:
- python
- /app/app.py
