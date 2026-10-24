# Stage 0 evidence: first Ohio map sample

Checked on 2026-10-23 against the [USGS TNM Access catalog](https://tnmaccess.nationalmap.gov/api/v1/docs) and the downloaded GeoPDFs. The six exact catalog IDs, download URLs, and SHA-256 hashes are in [evidence/pilot_sheets.json](evidence/pilot_sheets.json). Files are stored locally under ignored `data/usgs/` and can be downloaded again from their official URLs.

## Finding

The original question, “Does any named Ohio historical topo edition show individual well symbols?”, now has a **yes** answer. Five inspected editions visibly print labeled oil or gas well examples with open circles:

| Sheet                                                                                | Catalog year | Direct observation in the map interior                |
| ------------------------------------------------------------------------------------ | -----------: | ----------------------------------------------------- |
| [Lowell](https://www.sciencebase.gov/catalog/item/5a8a2576e4b00f54eb3c08b7)          |         1961 | “Oil Well” label beside an open circle                |
| [Findlay](https://www.sciencebase.gov/catalog/item/5a8a2476e4b00f54eb3bf1b5)         |         1960 | “Oil Well” label beside an open circle                |
| [North Baltimore](https://www.sciencebase.gov/catalog/item/5a8a2621e4b00f54eb3c192c) |         1960 | “Oil Well” and “Oil Wells” labels beside open circles |
| [Medina](https://www.sciencebase.gov/catalog/item/5a8a25afe4b00f54eb3c0e9d)          |         1953 | “Oil Wells” label beside open circles                 |
| [Lodi](https://www.sciencebase.gov/catalog/item/5a8a2561e4b00f54eb3c0722)            |         1961 | “Gas Well” label beside an open circle                |

The [Macksburg 1961](https://www.sciencebase.gov/catalog/item/5a8a257be4b00f54eb3c0935) map collar explicitly says that unlabeled wells are oil wells. A complete interior review is still needed before assigning it a symbol count. The catalog year is not necessarily the last photorevision year printed on the sheet; the map collars should be used when recording edition and revision history.

The Medina source is a 1953 1:24,000 edition. This conflicts with the source brief's blanket statement that every Ohio 7.5-minute quadrangle was first mapped between 1958 and 1964. Treat that statewide timing claim as needing correction before it appears in the demo or publication.

This is a targeted visual check, not a systematic count. No second reviewer has checked the sheets. It proves that the symbol source exists in several Ohio regions, but it does not measure detection performance, statewide coverage, unmatched leads, or hazard.

## Reproduce

1. Download the six official GeoPDF URLs in `evidence/pilot_sheets.json` into `data/usgs/` using the listed `local_file` names. The repository does not commit those large source scans.
2. Run `python -m ghostwells verify --manifest evidence/pilot_sheets.json --data-dir data/usgs` to check SHA-256 hashes.
3. Inspect the map interiors and collars at full resolution. The observation table above gives a fast starting point. Do not treat the listed labels as a complete inventory.
4. Install the research dependency and generate local review chips as described in `README.md`. The annotation desk records labels in rendered-page pixels and stores progress in the browser; its export is not a geospatial well layer.

## Tiling run — 2026-10-23

All six source PDFs passed the manifest hash check. The local tiler rendered 594 overlapping JPEG chips at 2.5 pixels per PDF point, 512-pixel chip size, and 64-pixel overlap (about 46.6 MB). The tile manifest is under ignored `data/usgs/tiles/`. One chip was visually inspected to confirm that the image and page-pixel origin align. The generated `review_queue.json` explicitly lists all 594 chips as pending. No symbol inventory or count has yet been completed; the chips still require human review and overlap deduplication. The annotation desk saves to browser-local storage and exports pixel positions, not geographic coordinates. Independent review remains outstanding.

## Published-model candidate pass — 2026-10-23

Downloaded the authors' U-Net from the [DOE/NETL EDX package](https://edx.netl.doe.gov/dataset/u-net-based-usgs-quadrangles-oil-and-gas-well-symbols-identification), DOI `10.18141/2452768`, into ignored `data/research_model/`. The catalog MD5 matched `44932be2a2fa9690bf3b5572747a158e`. The weights loaded in TensorFlow 2.15. The local runner follows the notebook's 256-pixel patches, 25-pixel overlap, ResNet preprocessing, 0.5 threshold, 4-connected components, and 45-pixel minimum area.

At the default 180-dpi-equivalent render, the model emitted 29 components across six maps. A crop review found many were contours, text, and collar artifacts; this scale was rejected. At 300-dpi-equivalent render, it emitted 909 raw components: Macksburg 150, Lowell 14, Findlay 52, North Baltimore 59, Medina 7, Lodi 627. Outputs are in ignored `data/usgs/review_candidates_300dpi.json`. Full-sheet overlays and the Findlay crop sheet are in ignored `data/usgs/full_pages/`.

These 909 are **unreviewed model candidates, not annotations or well counts**. The very high Lodi count and visible false positives show that the model cannot be assumed to transfer accurately to these Ohio sheets. No complete visual review, Ohio precision/recall estimate, collar mask, independent review, or geographic transform has been produced. Do not publish or treat these points as confirmed wells. Next: mask the map neatlines, review candidate crops and matched negatives, then quantify the model's Ohio error before deciding whether it can accelerate annotation.

### Conservative page-edge triage — 2026-10-23

A first broad page-edge screen was superseded on 2026-10-24 by manually traced per-sheet rectangular map frames in `evidence/map_frame_bounds.json`, with a 0.5%-of-page boundary buffer. All 15 edge/exterior crops were inspected: five clear collar/page-furniture false positives were rejected; ten boundary-near candidates remain uncertain. All 14 Lowell and 7 Medina candidates were also inspected once: three aligned open-circle symbols, four clear lookalikes, and 13 uncertain cases. This is a single-reviewer candidate-only sample—not a precision estimate or complete map inventory. The private decision sidecar and queue remain under ignored `data/usgs/`; the resulting 909 statuses are 3 confirmed symbols, 4 rejected lookalikes, 5 rejected collar/page-furniture, 23 uncertain, and 874 pending. The labeled Findlay crop verifies annotation context, not a candidate identity. See [RUN_LOG.md](RUN_LOG.md) for limitations and next steps.

The [USGS copyright guidance](https://www.usgs.gov/faqs/are-usgs-topographic-maps-copyrighted) says historical USGS topographic maps are public domain and asks for USGS credit. Public redistribution of source crops still needs the project's privacy review because a lead could reveal an exact location.

## Next measurement

Record all well symbols and lookalikes in each sampled sheet, with a reproducible collar mask and an independent review subset. Only then set these inventory rows to `reviewed` in the survey CSV, report density by sheet/region/era, and choose whether to continue to model inference.
