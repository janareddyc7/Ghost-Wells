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

## 2026-10-23 — Conservative page-edge screen

Operator: Codex; source-page overview inspection and one labeled Findlay detail crop. This is a triage pass, not complete visual review.

Input: `data/usgs/review_candidates_300dpi.json` (ignored/private); 909 components across six sheets. Added `ghostwells/candidate_review.py`, which emits a deterministic CSV queue with stable per-sheet candidate IDs, rendered-page coordinates, normalized coordinates, model component area, a conservative page-frame zone, and a pending review status.

Screen: Broad normalized page envelope (x 0.06–0.94, y 0.03–0.94), with a 0.015 normalized boundary buffer. Result: 908 map-interior/manual-review, 1 frame-edge/manual-review, 0 outside-frame/exclude. All 909 remain pending; no candidate has been accepted or rejected as a well. The envelope is deliberately broad and is not an exact map neatline, so this run does not substantiate collar removal. The one Findlay detail crop confirms the printed “Oil Well” label context but does not by itself validate model detections.

Output: `data/usgs/candidate_review_queue.csv` (ignored/private; precise page-pixel leads are not committed). The broad-envelope result above was an initial screen and was superseded on 2026-10-24 by per-sheet frame tracing below.

Next: trace exact per-sheet neatlines from source pages, then visually review candidate crops and matched negatives. Keep all candidate statuses pending until source-map evidence is inspected; measure Ohio precision/recall before using the layer to prioritize annotation.

## 2026-10-24 — Per-sheet frame tracing and first candidate review

Operator: Codex, single visual reviewer. Candidate crop decisions are preliminary and not independently checked.

Inputs: same six hash-verified GeoPDFs and 909-component 300-dpi candidate set. Each page's map-frame rectangle was manually traced from its rendered source overview and recorded in `evidence/map_frame_bounds.json`, with a 0.5%-of-page uncertainty buffer. This is a coarse rectangular screen; irregular/rotated neatlines and close edge symbols need human context. It is not a georeference.

Frame triage: 894 candidates fall in the rectangular interior, 10 in the boundary buffer, and 5 outside. Crops of all 15 boundary/exterior cases were inspected. The five exterior cases are clear collar/coordinate/page-furniture false positives and were rejected as well-symbol detections. All 10 frame-edge candidates remain uncertain for full-sheet or second-review context.

First interior-sheet review: inspected all 14 Lowell and all 7 Medina candidate crops against the original maps. Recorded 3 visually aligned open-circle symbols, 4 clear non-well lookalikes, and 13 crop-level uncertainties across these two sheets. No independent review and no matched-negative sample were performed; these labels are not a precision estimate. The Findlay “Oil Well” crop remains a contextual positive example, not a candidate label.

Private decision overlay: `data/usgs/candidate_review_decisions.json`; regenerated queue: `data/usgs/candidate_review_queue.csv`. Current totals across 909: 3 `confirmed_symbol`, 4 `rejected_lookalike`, 5 `rejected_collar_or_page_furniture`, 23 `uncertain`, and 874 `pending`. Both precise files are ignored and must remain private. Reproduce with `python -m ghostwells.candidate_review data/usgs/review_candidates_300dpi.json data/usgs/candidate_review_queue.csv --decisions data/usgs/candidate_review_decisions.json`.

Next: obtain a second reviewer on the 15 boundary cases and the 21 Lowell/Medina candidates, then continue sheet-by-sheet crop review with a matched sample of model-negative areas. Do not compute model metrics from these selected candidate-only crops.

## 2026-10-24 — Provenance-checked crop pilot export

Operator: Codex; local single-reviewer decisions only. No new labels were added during export.

Added `ghostwells/build_dataset.py` and pinned the optional crop dependencies in `requirements-dataset.txt`. The builder verifies all six source PDF SHA-256 hashes and rendered dimensions before creating output, binds the dataset ID to source manifest, raw candidates, review decisions, map-frame bounds, model hash, render scale, and crop size, then regenerates 256×256 source-map crops for every reviewed candidate. It writes `candidate_audit.csv`, `reviewed_examples.csv`, crop PNGs with individual SHA-256 values, and `dataset_manifest.json`. Existing output directories are never overwritten.

This initial candidate-only export was superseded by the combined pilot recorded below. Local output remains ignored/private.

Verification: builder completed after correcting the raster dimension preflight to use the same ceil-to-pixel convention as inference; source hashes matched, the audit and crop counts matched review records, all 35 crops are 256×256, and the crop file paths exist. Builder code and dependency runtime versions are included in the dataset identity. A clean repeat produced the same dataset ID and output hashes. `npm run check` and all seven Python tests passed after formatting the frame configuration; source-manifest verification passed.

## 2026-10-24 — Spatial negative-review pilot

Added `ghostwells/sample_negatives.py`, which selects a deterministic jittered 4×4 grid sample on each of the six map interiors, only where the center clears all model candidate locations by at least 256 rendered pixels. The resulting 96 chips were inspected once at full crop resolution. In 89, no standalone open-circle well symbol was visually apparent; seven ambiguous crops were retained as uncertain with individual notes. This is a qualitative single-reviewer screen: samples are not confirmed negatives, do not establish model recall, and remain ineligible for training until independent review.

Extended the dataset builder to validate the sample queue, map-frame provenance, candidate exclusion distance, crop dimensions, and crop hashes before creating the combined export. Dataset identity includes the negative queue, decision overlay, sampler manifest, source/manifests, builder implementation, model hash, and renderer runtime versions. Current local private output: `data/usgs/dataset-pilot-v7/`, dataset ID `6125081fb6f45212`; 909 candidate audit rows, 35 reviewed candidate crops, 96 spatial-review crops (131 crops total), all 256×256. The candidate statuses remain 3 confirmed symbols, 4 lookalikes, 5 collar/page-furniture exclusions, 23 uncertain, and 874 pending. A final label-eligibility audit now marks every crop ineligible for training until independent review; the manifest records zero training-eligible examples. No split is assigned and status remains **not training ready**. Private scans, queues, overlays, crops, and exports remain ignored by Git.

Final verification: a second build reproduced the same dataset ID and all output hashes. All 131 images are 256×256; the manifest reports 0 training-eligible examples. `npm run check` passed (typecheck, lint, formatting, production build); all eight Python tests passed, including a synthetic end-to-end dataset build and a tampered-crop rejection test; all six source scans passed SHA-256 verification. CI now installs the pinned dataset-rendering dependencies before running those tests.

Provenance: source-manifest SHA-256 `63c89aadb24eb21ae6b164764b2c5c0383b3ed0c615af888747b34994c8d9a3f`; model SHA-256 `5058259e0b7f8ce923f8c138135e15cb9ea09995a8a81fc853b3f74c1e0b12b2`. The builder and sampler source used for this export match commit `a9d45db` (committed after export); the dataset manifest also records hashes for each direct input and the builder implementation.

## 2026-10-24 — Complete provisional screen of remaining candidates

Operator: Codex AI visual screen, one pass. No independent human adjudication. The codes are provisional triage labels, not ground truth.

Inputs: six hash-verified GeoPDFs in `evidence/pilot_sheets.json`; 909-candidate output from the published U-Net; prior 35-item single-review decision overlay; exact pending-review queue and 57 contact sheets under ignored `data/usgs/candidate-review-all-v3/`. The contact sheets showed a 256×256 crop centered on each candidate and a red target cross. Per-sheet map context included explicit oil/gas well labels; Lodi also showed a “Storage Bins” lookalike context.

Screen: all 874 pending candidates screened. Recorded 573 provisional symbol candidates, 159 provisional lookalikes, and 142 uncertain cases. The 35 existing decisions were preserved unchanged. Queue row count, per-crop hashes, batch membership, contact-sheet hashes, codebook lengths, source/candidate/decision hashes, and contact-sheet coverage were validated before applying the overlay. The private AI overlay records reviewer/method, per-item contact sheet/cell, provisional confidence, and independent-review requirement.

Private output: `data/usgs/candidate_review_decisions_ai_v2.json` and `data/usgs/dataset-training-prep-v3/`, dataset ID `c353b1ae8a13c19b`. The export contains 909 reviewed candidate crops plus 96 prior spatial-review crops (1,005 total), and `provisional_training_candidates.csv` with 732 weak-label examples (573 symbol-like, 159 lookalike). The remaining 142 AI-uncertain crops are retained in `reviewed_examples.csv` but excluded from that provisional binary experiment table. All 1,005 crops remain training-ineligible pending independent adjudication; no split is assigned. This is a patch-classification exploration input, not a detector training set, performance estimate, map-wide well inventory, or field-confirmed location layer. The decision overlay hashes the review applier, codebook, all 57 contact sheets, review queue, and original decisions; the dataset manifest carries that review provenance forward.

Location-free snapshot: `evidence/candidate_review_summary.json`. Private crop/decision artifacts, precise pixel positions, and source scans remain ignored and are not in Git. Next action: obtain an independent human review of the AI statuses and spatial sample, resolve disagreements, then decide whether an exploratory training run is justified. Do not calculate validation metrics from these model-selected candidates.

## 2026-10-24 — Blind-review desk and final dataset pipeline

Added a local-only browser review desk that hides AI decisions, verifies the active crop hash, supports keyboard decisions and notes, saves progress in browser storage, and exports a full-queue review with queue/contact-sheet provenance and reviewer attestation. Added a Python importer that rejects mismatched queues, crops, contact sheets, provenance, and decision coverage while preserving the AI decision as history. The dataset builder now keeps AI weak labels separate from independently reviewed fit-only examples and only marks a complete two-class blind review as exploratory fit-ready; evaluation remains prohibited.

Rebuilt private dataset ID `712b67e8b9a3fee1` to `data/usgs/dataset-training-prep-v4/`: 909 candidate chips plus 96 spatial-sample chips; 732 AI weak labels; zero independently reviewed fit examples; zero training-eligible examples today. The state is intentionally **not training ready** until a separate human review is complete. No data or exact locations are committed.

## 2026-10-24 — Contact-sheet integrity and final verification

The first review-desk pass recorded hashes for contact sheets but did not verify them against the original AI screening at the decision point. Tightened the chain: the batch manifest carries each contact-sheet SHA-256; the browser verifies crop and context-sheet hashes before accepting decisions and again on export; both AI and independent-review importers compare them to the originating batch and AI provenance. Regenerated the private `candidate-review-all-v4/` batch from the exact same queue, verified all 874 status codes were preserved in `candidate_review_decisions_ai_v3.json`, and rebuilt the private dataset twice.

Final deterministic snapshot: dataset ID `712b67e8b9a3fee1`, with repeat output hashes matching. It contains 909 candidate crops and 96 spatial-sample crops (1,005 total); 732 provisional AI candidates, 0 independent human fit examples, 0 training-eligible examples, and no evaluation split. All six downloaded source scans match the evidence manifest. Final checks: 10 Python tests passed; `npm run check` passed typecheck, lint, formatting, and production build. The private crops, queues, codebook, and exact coordinates remain ignored and uncommitted.

## Entry template

## 2026-10-24 — Training and evaluation runners prepared

Owner reports completing the 874-candidate review and the full-map tile annotation in the browser. Neither export is present in the workspace, so no re-import, manifest rebuild, model fit, or detector metric was run; existing private dataset v4 remains unchanged and not training-ready. Added a fail-closed exploratory candidate-patch trainer that accepts only hash-verified independently reviewed training rows, trains on training counties only, and emits no evaluation/deployment claims. Added a held-out detector evaluator requiring complete reviewed-tile coverage, positive/negative inventory, uncertainty resolution, county-disjoint frozen split, matching source hashes, and truthful blind-inventory attestation. Evaluation reports one-to-one matches and FP/FN breakdowns at map-scale distance tolerances; these are not georeferenced ground-distance validation. App annotation export now records the blindness attestation. Tests cover split leakage, crop integrity, successful scoring, and incomplete-coverage rejection. Next: place the two browser exports in private `data/usgs/`, validate/import, rebuild the manifest, then run only gates supported by the actual labels and annotations.

Rebuilt private dataset v5 from the verified on-disk inputs to `data/usgs/dataset-training-prep-v5/`. The dataset ID remains `712b67e8b9a3fee1` because the input hashes are unchanged; manifest SHA-256 is `587026913c4da7d3c5a7dd058be45b820be0681c2895a976e045b3b731788338`. It contains 909 candidate crops and 96 spatial-sample crops, including 573 AI-screen symbol candidates, 159 AI-screen lookalikes, 142 AI-screen uncertain cases, 3 earlier confirmed symbols, 4 earlier rejected lookalikes, 5 collar/page-furniture rejects, 23 candidate uncertainties, 89 spatial chips reviewed as no symbol visible, and 7 spatial uncertainties. It has 0 independently reviewed fit examples and 0 training-eligible examples; `exploratory_fit_ready=false`, `training_ready=false`, `evaluation_ready=false`. Python 3.10 and TensorFlow are available locally. The trainer's readiness check was smoke-tested and correctly refuses this AI-only snapshot. The owner's newer browser reviews still need their JSON exports before the dataset can legitimately become fit-ready.

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
