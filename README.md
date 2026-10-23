# Ghost Wells

Ghost Wells investigates whether historical Ohio topographic maps can reveal oil and gas well symbols missing from modern records. It turns map evidence into reviewable leads. A detection is never a confirmed well or a measure of danger.

## Current state

This repository is an initial, runnable foundation. The public interface uses explicitly labeled sample data. No Ohio well detections, ODNR matches, model accuracy, or agency partnership have been validated here yet. The first research gate is the Ohio symbol survey in [PLAN.md](PLAN.md).

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
python -m ghostwells survey --input examples/sheets.csv --output reports/survey.json
python -m unittest discover -s tests
```

The CSV schema is documented in `examples/sheets.csv`. `review_status=reviewed` is required before counts are considered evidence. Rows marked `pending` are excluded from confirmed symbol counts. Use local source IDs and edition metadata for provenance. Do not put precise candidate coordinates in public files.

## Structure

- `src/`: accessible review dashboard and design system
- `ghostwells/`: small, dependency free Stage 0 survey CLI
- `examples/`: synthetic schema example, never field evidence
- `tests/`: survey behavior tests
- `PLAN.md`: milestones, evidence gates, decisions, and release checklist

## Data and safety

Public screens contain aggregate or sample information only. Precise candidate locations, source crops, and reviewer decisions need a private access controlled workflow before real leads are handled. Do not visit, excavate, or publicize a candidate location. ODNR alone can confirm a well in the field. This is an independent project, not an ODNR product.

## License

Code is licensed under MIT; third party data, imagery, models, and map scans retain their own terms. Check each source before redistribution.
