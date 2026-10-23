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

The [USGS copyright guidance](https://www.usgs.gov/faqs/are-usgs-topographic-maps-copyrighted) says historical USGS topographic maps are public domain and asks for USGS credit. Public redistribution of source crops still needs the project's privacy review because a lead could reveal an exact location.

## Next measurement

Record all well symbols and lookalikes in each sampled sheet, with a reproducible collar mask and an independent review subset. Only then set these inventory rows to `reviewed` in the survey CSV, report density by sheet/region/era, and choose whether to continue to model inference.
