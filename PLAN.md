# Ghost Wells — project tracker

Updated: 2026-10-24. Owner: project team. Status key: `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED`.

## North star and release rule

Build a reproducible workflow that reads historical Ohio map evidence, compares it with ODNR records, and produces private, reviewable leads. A polished interface is useful only when its underlying evidence is traceable. Never call a candidate a confirmed well.

**Current gate:** Five named Ohio historical topo editions now show labeled individual well symbols in targeted inspection ([evidence log](EVIDENCE.md)). The remaining question is density, lookalikes, spatial coverage, and whether detection can generate useful reviewed leads. Complete and independently check the survey before claiming that the approach scales.

## Milestones

| ID  | Status      | Outcome                    | Exit evidence                                                                                                                                |
| --- | ----------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| M0  | IN PROGRESS | Survey Ohio sheet editions | Named USGS sheets, years, download links, reviewer notes, count of actual symbols and lookalikes; representative positive and negative crops |
| M1  | TODO        | Reproducible map ingest    | Raw scans and metadata manifest with hashes, CRS and license records, georeferencing QA                                                      |
| M2  | TODO        | Ohio detection baseline    | Licensed model, labeled chips, county held out precision/recall, era and region error analysis                                               |
| M3  | TODO        | ODNR cross check           | Dated ODNR snapshot, coordinate QA, 50/100/200 m sensitivity report, manually reviewed candidates                                            |
| M4  | TODO        | Private reviewer workflow  | Source crop and edition history, accept/reject/uncertain states, audit trail, private lead export                                            |
| M5  | TODO        | Public aggregate view      | Privacy review, suppress small cells, no candidate points or identifiable imagery                                                            |
| M6  | TODO        | Demo and release           | End to end replay from real Ohio sheet, verified claims, accessible responsive UI, security and release checks                               |

## Work queue

### 0. Evidence and feasibility

- [x] Download six named Ohio editions: Macksburg/Lowell, Findlay/North Baltimore, Medina/Lodi.
- [ ] Add negative-control sheets from lower drilling regions.
- [x] Save source URL, USGS identifier, catalog year, scale, download date, rights, and file hash for each pilot scan.
- [x] Inspect selected interior areas and collars; document labeled positive examples on five sheets and a collar note on Macksburg.
- [ ] Complete full-interior and collar inspection, count symbols and confusing lookalikes, and retain private review crops.
- [ ] Have a second reviewer check a sample. Log disagreements.
- [x] Seed the real pilot inventory with all six editions marked pending; the survey command reports zero completed counts.
- [x] Add local PDF tiling and a browser annotation desk for well symbols, common lookalikes, uncertainty, undo, and reviewed-tile tracking.
- [ ] Annotate every map tile; inspect and resolve duplicate marks at chip overlaps.
- [x] Integrate the published DOE/NETL U-Net as a reproducible, pixel-only candidate generator; keep all outputs unreviewed.
- [ ] Review the candidate layer and matched negative examples on Ohio sheets; measure precision/recall before promoting any model output to annotation.
- [ ] Run `ghostwells survey` on the fully reviewed inventory and publish aggregate counts only.
- [x] Decide to **continue Stage 0**: labeled symbols exist on five sampled sheets across multiple regions. This is a narrow feasibility result, not a decision to launch the full detection product.
- [ ] Make a documented **continue / pivot / stop** decision for model work after full counts and a second review. Continue if density and reproducibility justify a pilot. Pivot to another historical source if symbols are sparse. Stop map detection if neither source produces reliable, permitted evidence.

### 1. Data contracts and provenance

- [ ] Verify USGS download/API behavior and actual georeferencing for selected maps.
- [ ] Verify ODNR fields, coordinate reference, update date, download rights, and historical accuracy notes.
- [ ] Inventory all proposed context layers; add only those with accessible data and justified purpose.
- [ ] Create immutable input manifests and derived output version IDs.
- [ ] Define candidate status: raw detection → deduplicated symbol → unmatched lead → reviewed lead → agency submitted → agency disposition. Never equate these stages.

### 2. Detection and matching

- [ ] Confirm model weights, license, and reproducible inference path from Ciulla et al. before using published metrics as project metrics.
- [ ] Label Ohio symbols and hard negatives; split validation by county and sheet, not random chips.
- [x] Generate a reproducible private review queue; all 909 candidates now have a recorded status, including 874 provisional AI-screened cases. This is not independent adjudication or a complete map inventory.
- [x] Trace conservative rectangular map-frame bounds for all six pilot sheets, with an explicit boundary buffer; exact edge geometry remains a refinement.
- [x] Review all collar/exterior and frame-edge candidate crops once; reject only five clear page-furniture hits and leave boundary-near cases uncertain.
- [x] Build a provenance-checked private crop pilot with source/candidate/decision/frame hashes, one crop per reviewed hit, and an explicit no-training-ready gate.
- [x] Generate and visually screen a deterministic 4×4 spatial sample per sheet, 96 chips total; retain seven ambiguous crops as uncertain and do not mark any sample training-eligible.
- [x] Export a combined private pilot with 909 candidate audit rows/crops, 96 spatial-review crops, 732 provisional exploratory-training candidates, pinned renderer versions, and an explicit zero-training-eligible gate.
- [x] Screen all 874 previously pending candidate crops once in 57 map-specific contact sheets; record 573 provisional symbol candidates, 159 provisional lookalikes, and 142 uncertain cases with crop/batch provenance.
- [ ] Obtain independent human adjudication of the AI screen and spatial sample; resolve disagreements before any accuracy estimate or training promotion.
- [ ] Record pixel center, map transform, CRS, confidence, model version, crop, and source sheet for each detection.
- [ ] Assess map positioning error on known surveyed wells before choosing any public accuracy claim.
- [ ] Merge duplicate chips; then test edition fusion at 15 m and ODNR matching at 50, 100, and 200 m.
- [ ] Sample unmatched results for manual review and report false positives.

### 3. Product and privacy

- [x] Create initial responsive review interface with explicit sample state.
- [x] Add a local-only blind candidate adjudication desk with SHA-256 crop/contact-sheet checks, browser-local progress, keyboard labels, and private reviewer-attested export; this does not replace authentication or a shared review service.
- [ ] Connect interface to real, versioned aggregate survey output.
- [ ] Design private reviewer authentication and authorization before storing precise leads online.
- [ ] Implement decision history, source evidence viewer, and export only after data contract review.
- [ ] Define public aggregation/suppression rule and test re-identification risk.
- [ ] Keep risk/context scores described as review priority, never hazard prediction.

### 4. Engineering and release

- [x] Set TypeScript strictness, lint, format, and automated local checks.
- [x] Add a dependency free Stage 0 survey CLI with tests.
- [x] Add CI checks for the frontend and survey utility.
- [ ] Define a dependency update policy.
- [x] Add a source manifest and file-hash verification; keep raw scans and precise locations outside Git.
- [ ] Test keyboard and mobile workflows with real users.
- [ ] Threat model precise coordinate storage, exports, logs, and screenshots.
- [ ] Verify every number, citation, and deadline in the demo against current primary sources.
- [ ] Correct the source brief's statewide first-mapped date claim: the official catalog contains a Medina 1953 1:24,000 edition.
- [ ] Prepare a 3 minute demo using real Ohio evidence only; label any simulated data.

## Decision log

| Date       | Decision                                | Reason                                                                                        | Revisit                                                                            |
| ---------- | --------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 2026-10-23 | Start with files, not a database        | Survey and pilot are single team batch workflows; fewer moving parts                          | Add a database when concurrent review, access controls, or query volume require it |
| 2026-10-23 | Show sample data explicitly in UI       | No Ohio detection has been validated in this repository                                       | Replace with versioned, reviewed exports after M0–M3                               |
| 2026-10-23 | Gate full build on Ohio symbols         | A core source assumption is unresolved                                                        | After reviewed M0 evidence                                                         |
| 2026-10-23 | Continue the Stage 0 survey             | Five named Ohio sheets contain labeled well symbols; density and lead quality remain unknown  | After full counts and independent review                                           |
| 2026-10-23 | Use the published U-Net only for triage | 300-dpi run produced 909 components with a very high Lodi count; Ohio transfer is unvalidated | After visual candidate and negative review                                         |

## Run log template

For each real data run, append a dated record to `RUN_LOG.md` with: input manifest hash, code commit, model version, parameters, counts at each stage, review sample, errors, and output paths. Avoid writing precise leads into public Git history.

## Definition of done

The project can demonstrate one complete, reproducible Ohio workflow from source scan to private, reviewable lead with measured uncertainty. The public experience reveals no exact candidate locations. All data, models, scores, and impact claims are sourced and accurately labeled. `npm run check` and Python tests pass, the UI passes mobile and keyboard review, and the release is reproducible from a clean clone.
