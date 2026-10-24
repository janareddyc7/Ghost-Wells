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
pip install -r requirements-dataset.txt
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

### Export the reviewed crop pilot

The reviewed crop export is local and private. Install `requirements-dataset.txt`, ensure the ignored raw scans and candidate/decision JSON are present, and choose new output directories (the commands refuse to overwrite existing ones). First create a deterministic 4×4-per-sheet spatial sample, review every chip, and save the private decision overlay; then combine it with reviewed model hits:

```bash
pip install -r requirements-dataset.txt
python -m ghostwells.sample_negatives --manifest evidence/pilot_sheets.json --candidates data/usgs/review_candidates_300dpi.json --data-dir data/usgs --output-dir data/usgs/negative-review-v1
python -m ghostwells.build_dataset --manifest evidence/pilot_sheets.json --candidates data/usgs/review_candidates_300dpi.json --decisions data/usgs/candidate_review_decisions.json --negative-queue data/usgs/negative-review-v1/negative_review_queue.csv --negative-decisions data/usgs/negative_review_decisions.json --data-dir data/usgs --output-dir data/usgs/dataset-pilot-v7
```

The spatial sample command leaves all chips pending; review every chip and create `data/usgs/negative_review_decisions.json` before building the combined export. Copy `sample_set_id` from `sample_manifest.json`, set `all_queued_samples_reviewed` to `true` only after reviewing every queue row, provide a `default_note` for samples with no visible well symbol, and list each ambiguous sample ID with its own note in `uncertain`:

```json
{
  "schema_version": 1,
  "sample_set_id": "COPY_FROM_sample_manifest.json",
  "all_queued_samples_reviewed": true,
  "default_status": "no_well_symbol_visible",
  "default_note": "Describe what was actually inspected.",
  "uncertain": {
    "sample_id_from_queue": "Explain why this crop is ambiguous."
  }
}
```

The export verifies source and crop hashes, regenerates reviewed candidate crops from the source PDFs, and records crop hashes and decision notes alongside the full candidate audit. The checked-in source code does not contain the private decision overlays or map chips; maintain those under ignored `data/usgs/`. The current local export has 35 reviewed model-hit crops and 96 sampled map-interior crops (89 with no well symbol visually apparent, 7 uncertain), all reviewed once. These are single-reviewer observations, not ground truth or a recall estimate. Every example is explicitly ineligible for training until independent review, and the dataset is `not_training_ready`. No random crop split is allowed; any future evaluation must hold out entire sheets/counties.

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
