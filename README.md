# Ghost Wells

Ghost Wells investigates whether historical Ohio topographic maps can reveal oil and gas well symbols missing from modern records. It turns map evidence into reviewable leads. A detection is never a confirmed well or a measure of danger.

## Current state

This repository is an initial, runnable foundation. [Targeted visual inspection](EVIDENCE.md) of six official Ohio historical map editions found labeled well symbols on five sheets. Full-sheet symbol counts, automated Ohio detections, ODNR matches, model accuracy, and agency partnership have not been validated here. The active research gate is a systematic Ohio symbol survey in [PLAN.md](PLAN.md). The interface's map artwork is illustrative.

## Run the interface

Requires Node.js 20 or newer.

```bash
npm install
npm run dev
```

Run `npm run check` before committing. The app opens at the local URL printed by Vite.

## Run the survey helper

Requires Python 3.10 or newer. The CLI accepts a manually reviewed CSV inventory of historical sheets. It reports symbol counts and coverage without making up detections.

```bash
python -m ghostwells survey --input evidence/survey_inventory.csv --output reports/survey.json
python -m ghostwells verify --manifest evidence/pilot_sheets.json --data-dir data/usgs
python -m unittest discover -s tests
```

To prepare private image chips for point-by-point annotation, install the optional research dependency and generate overlapping tiles:

```bash
pip install -r requirements-research.txt
python -m ghostwells tiles --manifest evidence/pilot_sheets.json --data-dir data/usgs --output-dir data/usgs/tiles
```

Then open Sheet Survey in the app, load the `data/usgs/tiles` folder in the local annotation desk, and export reviewer annotations. The app stores progress in browser-local storage. Exports include pixel coordinates only; keep them private and do not commit them.

### Published U-Net candidate pass

The original research team released a pretrained U-Net and inference notebook through [DOE/NETL EDX (DOI 10.18141/2452768)](https://edx.netl.doe.gov/dataset/u-net-based-usgs-quadrangles-oil-and-gas-well-symbols-identification). The model file is 294 MB, licensed CC BY on the catalog, and is intentionally not committed. Download `unet_model.h5` from that catalog into `data/research_model/`, then verify its MD5 is `44932be2a2fa9690bf3b5572747a158e`. Install `requirements-inference.txt` and run:

```bash
python -m ghostwells candidates --manifest evidence/pilot_sheets.json --data-dir data/usgs --model data/research_model/unet_model.h5 --output data/usgs/review_candidates.json
```

This uses a 300-dpi-equivalent render and reproduces the published 256-pixel patches, 25-pixel overlap, ResNet preprocessing, 0.5 probability threshold, and 45-pixel component-area floor. The JSON contains pixel-space model candidates only. On the six current Ohio sheets, the run produced 909 raw components, including 627 on Lodi; this is a warning that Ohio transfer and false-positive behavior need review, not a well count. The model was not validated on these Ohio editions, so candidate output is not a complete annotation, a confirmed well, or a geospatial location. Review candidates and matched negatives before reporting counts.

The CSV schema is documented in `examples/sheets.csv`. `review_status=reviewed` is required before counts are considered evidence. Rows marked `pending` are excluded from confirmed symbol counts. Download the six scans from the official URLs in `evidence/pilot_sheets.json` before running `verify`; raw files stay ignored by Git. Do not put precise candidate coordinates in public files.

## Structure

- `src/`: accessible review dashboard and design system
- `ghostwells/`: small, dependency free Stage 0 survey CLI
- `examples/`: synthetic schema example, never field evidence
- `evidence/`: official source metadata, hashes, and scoped observations
- `tests/`: survey behavior tests
- `PLAN.md`: milestones, evidence gates, decisions, and release checklist

## Data and safety

Public screens contain aggregate or sample information only. Precise candidate locations, source crops, and reviewer decisions need a private access controlled workflow before real leads are handled. Do not visit, excavate, or publicize a candidate location. ODNR alone can confirm a well in the field. This is an independent project, not an ODNR product.

## License

Code is licensed under MIT; third party data, imagery, models, and map scans retain their own terms. Check each source before redistribution.
