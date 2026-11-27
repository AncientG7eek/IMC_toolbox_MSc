# Test fixtures

Place small real-world files here for integration tests:

- `mcd/` — one tiny `.mcd` with at least two acquisitions
  - `20210305_NE_mockData1.mcd` is the Bodenmiller Lab mock dataset
    (CC-BY-4.0), sourced from
    https://github.com/BodenmillerGroup/TestData
- `ome/` — OME TIFFs:
  - `2021_52_ROI9_fullstacks.tiff` — one OME image with all 41 channels
    described together (stored as a 64×64 crop)
  - `S00T1_ROI2.ome.tiff` — one channel per page (49 pages, each a 64×64
    crop)
- `panels/` — a small standalone CSV panel and an XLSX panel
- `clinical/` — a small clinical CSV and an XLSX table

Keep the files small (a few channels and a low-resolution image region).
Integration tests will read from this directory and should be skipped if a
required fixture is missing.
