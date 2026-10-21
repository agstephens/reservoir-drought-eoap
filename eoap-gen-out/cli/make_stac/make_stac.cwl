id: 
  eoap-gen-out/cli/make_stac/make_stac.cwl
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
  dockerPull: ghcr.io/owner/reservoir-drought-eoap/make_stac:main
- class: InlineJavascriptRequirement
doc: |
  None
cwlVersion: v1.0
baseCommand:
- python
- /app/app.py
