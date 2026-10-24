# Ghost Wells

Ghost Wells investigates whether historical Ohio topographic maps can reveal oil and gas well symbols missing from modern records. It turns map evidence into reviewable leads. A detection is never a confirmed well or a measure of danger.

## Current state

This repository is an initial, runnable foundation. [Targeted visual inspection](EVIDENCE.md) of six official Ohio historical map editions found labeled well symbols on five sheets. The project owner reports completing the full-map tile annotation in the local browser desk, but its JSON export is not currently in this workspace, so map coverage and counts have not yet been independently checked here. Ohio detector metrics, ODNR matches, and agency partnership are not validated. The interface's map artwork is illustrative.

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

For candidate adjudication, open Sheet Survey and load the complete `data/usgs/candidate-review-all-v4/` folder in the independent review desk. It hides the AI screen, checks the active crop and contact sheet SHA-256 before enabling a decision, saves progress in browser-local storage, and exports a reviewer-attested JSON file. This is a local workflow, not account authentication or a shared review server; keep the queue, scans, and export private.

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

The export verifies source and crop hashes, regenerates candidate crops from the source PDFs, and records crop hashes and decision notes alongside the full candidate audit. The checked-in source code does not contain the private decision overlays, codebook, or map chips; maintain those under ignored `data/usgs/`.

As of 24 October 2026, the private pilot contains 909/909 candidate decision records: 35 earlier single-review decisions and a one-pass AI visual screen of the remaining 874 candidates. That screen recorded 573 provisional symbol candidates, 159 provisional lookalikes, and 142 uncertain crops. It also produced 732 provisional candidates for explicitly exploratory training experiments and retained the earlier 96-chip spatial sample. These are triage labels, not ground truth; they do not establish map-wide well counts, model precision/recall, or field-confirmed locations. The dataset remains `not_training_ready`, with zero independently reviewed training-eligible examples and no split. See the location-free aggregate snapshot in [candidate_review_summary.json](evidence/candidate_review_summary.json).

To apply the private coded screen, after the review batch and private codebook are available, run:

```bash
python -m ghostwells.apply_review_codes --manifest evidence/pilot_sheets.json --candidates data/usgs/review_candidates_300dpi.json --source-decisions data/usgs/candidate_review_decisions.json --queue data/usgs/candidate-review-all-v4/review_queue.csv --batch-manifest data/usgs/candidate-review-all-v4/batch_manifest.json --codebook data/usgs/candidate-review-all-v4/ai_review_codes_v1.json --output data/usgs/candidate_review_decisions_ai_v3.json
```

Then build the private crop export using the AI overlay as `--decisions`. The builder writes `provisional_training_candidates.csv` for weak-label experiments only; its rows prohibit evaluation use, group by source sheet for any later split, and remain ineligible until independent human adjudication. Do not use candidate-only chips as validation data. Any future evaluation must hold out entire sheets/counties.

After you complete the blind candidate review and export `ghost-wells-independent-review.json`, validate and merge it without discarding the AI history. The owner reports completing this review, but the export is not yet present in this workspace; no labels or counts are treated as imported until the file passes validation:

```bash
python -m ghostwells.apply_independent_review --ai-decisions data/usgs/candidate_review_decisions_ai_v3.json --queue data/usgs/candidate-review-all-v4/review_queue.csv --batch-manifest data/usgs/candidate-review-all-v4/batch_manifest.json --review data/usgs/ghost-wells-independent-review.json --output data/usgs/candidate_review_decisions_independent_v1.json
```

Use that merged overlay as `--decisions` when rebuilding the private crop dataset. Only a complete blind review with both clear classes produces `exploratory_fit_ready`; `independent_training_examples.csv` is for fitting a binary candidate-patch classifier only. It is not a new U-Net detector, evaluation set, recall estimate, or verification of physical wells. No split or evaluation metrics are generated automatically.

### Fit-only classifier and held-out detector evaluation

Install `requirements-training.txt` only after the private blind-review JSON has been imported and the dataset manifest reports `exploratory_fit_ready`. Prepare a county-disjoint split plan from [the template](examples/evaluation_split_plan.template.json), assigning every sheet exactly once. Freeze the split before viewing metrics. The plan’s blindness flag must be true only if the full-map annotation was completed without seeing the detector candidate layer.

Rebuild the dataset with the imported review, then fit a small candidate-patch classifier on training-counties only. The trainer verifies the manifest and every crop hash; it records only in-sample training history and creates no validation metrics:

```bash
python -m ghostwells.build_dataset --manifest evidence/pilot_sheets.json --candidates data/usgs/review_candidates_300dpi.json --decisions data/usgs/candidate_review_decisions_independent_v1.json --negative-queue data/usgs/negative-review-v1/negative_review_queue.csv --negative-decisions data/usgs/negative_review_decisions.json --data-dir data/usgs --output-dir data/usgs/dataset-training-prep-reviewed-v1
python -m ghostwells.train_patch_classifier --dataset-dir data/usgs/dataset-training-prep-reviewed-v1 --split-plan data/usgs/evaluation_split_plan.json --source-manifest evidence/pilot_sheets.json --output-dir data/usgs/training-runs/candidate-patch-v1
```

To measure the frozen published detector, export the full map-tile annotations from the browser desk. The evaluator requires complete reviewed-tile coverage for held-out sheets, no unresolved uncertain marks there, source-hash agreement, a county-disjoint frozen split, and a blind-inventory attestation. It reports one-to-one precision/recall/F1 at 50/100/200 m-equivalent distances using printed map scale; these are not georeferencing-validated ground distances. The report contains private source provenance and must stay under ignored `data/usgs/`:

```bash
python -m ghostwells.evaluate_detector --annotations data/usgs/ghost-wells-review-annotations.json --tile-manifest data/usgs/tiles/tile_manifest.json --candidates data/usgs/review_candidates_300dpi.json --source-manifest evidence/pilot_sheets.json --split-plan data/usgs/evaluation_split_plan.json --output data/usgs/evaluation/detector-heldout-v1.json
```

The current checked-in tile queue still says `pending_human_review` because the browser’s completed review is not imported into the project files yet. Re-export the browser-local annotation state if needed; do not interpret the current 594 pending tile records as evidence that no review was performed.

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
