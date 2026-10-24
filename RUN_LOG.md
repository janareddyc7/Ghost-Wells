# Run log

## 2026-10-23 — Initial USGS pilot acquisition

Operator: Codex visual review, single reviewer.

Inputs: Six official USGS GeoPDFs listed with URLs, source IDs, and SHA-256 hashes in `evidence/pilot_sheets.json`; stored under ignored `data/usgs/`.

Code commit at start: `ef8e897`. Model: none. Parameters: targeted human inspection of map interiors and collars, no full count.

Result: Labeled examples observed on Lowell, Findlay, North Baltimore, Medina, and Lodi. Macksburg collar says unlabeled wells are oil wells. No ODNR comparison or candidate output. Details and limits: `EVIDENCE.md`.

Next action: full-sheet inventory including lookalikes and independent review; update survey CSV only after those checks.

## 2026-10-23 — Local review-chip preparation

Operator: Codex; one rendered chip visually inspected, no symbol review performed.

Inputs: Six source PDFs listed in `evidence/pilot_sheets.json`; hashes verified before rendering. Code commit at start: `8c4f4d2`.

Parameters: PyMuPDF, 2.5 pixels per PDF point, 512-pixel square chips, 64-pixel overlap, JPEG quality 90.

Result: 594 chips generated under ignored `data/usgs/tiles/` (about 46.6 MB), with rendered-page pixel origins recorded in the local tile manifest. Added `review_queue.json` with all 594 chips explicitly pending, plus a browser annotation desk for seven symbol/lookalike classes, local progress, undo, overlap duplicate warning, reviewed-chip tracking, and JSON export. Fixed duplicate suppression to 24 rendered pixels and made counts reflect only the loaded tile set. No annotation marks, reviewed chips, symbol counts, model results, or geographic coordinates were produced. One Findlay tile was visually inspected for content/origin alignment; independent review is still pending.

Verification: `npm run check` passed (typecheck, lint, format check, production build); `python -m ghostwells verify --manifest evidence/pilot_sheets.json --data-dir data/usgs` passed. The tiling command completed successfully. Review status: 0/594 chips reviewed; 0 marks; counts unavailable.

Next action: load the local tile folder in Sheet Survey, annotate all interiors, reconcile overlap duplicates, then have a second reviewer check a documented sample before counting.

## 2026-10-23 — Published U-Net candidate exploration

Operator: Codex; one high-resolution candidate crop sheet and full-sheet overlays visually inspected. This is a model triage run, not a completed annotation review.

Inputs: Six hash-verified GeoPDFs in `evidence/pilot_sheets.json`. Published model from DOE/NETL EDX DOI `10.18141/2452768`; catalog MD5 `44932be2a2fa9690bf3b5572747a158e`; local SHA-256 is recorded in the ignored candidate JSON. Model loaded under TensorFlow 2.15.

Parameters: Page rendering scale 4.1666667 pixels per PDF point (300 dpi), 256-pixel patches, 25-pixel overlap, ResNet preprocessing, probability threshold 0.5, 4-connected components, minimum component area 45 pixels, batch size 16.

Result: 909 raw components: Macksburg 150, Lowell 14, Findlay 52, North Baltimore 59, Medina 7, Lodi 627. The lower-resolution 180-dpi pass produced 29 components and was visually rejected as a useful candidate pass because many hits were contours, text, and collars. The 300-dpi Findlay candidate crop sheet shows a mixture of circle-like marks and false positives; Lodi's high volume remains unreviewed. No mark is promoted to a confirmed well and no sheet is complete.

Outputs (ignored/private): `data/usgs/review_candidates.json`, `data/usgs/review_candidates_300dpi.json`, and `data/usgs/full_pages/*_native_overlay.jpg` plus candidate crop sheets. Model results have not been geographically transformed. Ohio transfer accuracy is unknown; no independent review was performed.

Next action: establish map-neatline masks, screen candidate and negative crops, calculate Ohio precision/recall against visual review, and only then decide whether model output can safely prioritize full annotation.

## Entry template

Date/time:

Operator:

Input manifest and hash:

Code commit:

Model/version:

Parameters:

Counts (sheets, symbols, matches, unmatched, reviewed):

Errors and exclusions:

Review sample and decision:

Output paths (private paths only for precise leads):

Next action:
