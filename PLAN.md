# Ghost Wells — project tracker

Updated: 2026-10-23. Owner: project team. Status key: `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED`.

## North star and release rule

Build a reproducible workflow that reads historical Ohio map evidence, compares it with ODNR records, and produces private, reviewable leads. A polished interface is useful only when its underlying evidence is traceable. Never call a candidate a confirmed well.

**Current gate:** Determine whether specific Ohio historical topo editions print enough individual well symbols for this approach. The source brief does not yet identify a confirmed Ohio sheet. Record a scan, edition, URL, and reviewed crop before claiming success.

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

- [ ] Download a small stratified sample of named Ohio editions: Macksburg/Lowell, Findlay/North Baltimore, Medina/Lodi, plus negative controls.
- [ ] Save source URL, USGS identifier, edition year, scale, download date, rights, and file hash for every scan.
- [ ] Inspect interior map areas and collars separately. Record actual symbol crops and confusing lookalikes.
- [ ] Have a second reviewer check a sample. Log disagreements.
- [ ] Run `ghostwells survey` on the reviewed inventory and publish aggregate counts only.
- [ ] Make a documented **continue / pivot / stop** decision. Continue if multiple Ohio sheets across more than one region have unambiguous individual symbols and enough density for a useful pilot. Pivot to another historical source if symbols are sparse. Stop map detection if neither source produces reliable, permitted evidence.

### 1. Data contracts and provenance

- [ ] Verify USGS download/API behavior and actual georeferencing for selected maps.
- [ ] Verify ODNR fields, coordinate reference, update date, download rights, and historical accuracy notes.
- [ ] Inventory all proposed context layers; add only those with accessible data and justified purpose.
- [ ] Create immutable input manifests and derived output version IDs.
- [ ] Define candidate status: raw detection → deduplicated symbol → unmatched lead → reviewed lead → agency submitted → agency disposition. Never equate these stages.

### 2. Detection and matching

- [ ] Confirm model weights, license, and reproducible inference path from Ciulla et al. before using published metrics as project metrics.
- [ ] Label Ohio symbols and hard negatives; split validation by county and sheet, not random chips.
- [ ] Record pixel center, map transform, CRS, confidence, model version, crop, and source sheet for each detection.
- [ ] Assess map positioning error on known surveyed wells before choosing any public accuracy claim.
- [ ] Merge duplicate chips; then test edition fusion at 15 m and ODNR matching at 50, 100, and 200 m.
- [ ] Sample unmatched results for manual review and report false positives.

### 3. Product and privacy

- [x] Create initial responsive review interface with explicit sample state.
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
- [ ] Add real data fixtures under a rights-aware storage policy; keep raw scans and precise locations outside Git.
- [ ] Test keyboard and mobile workflows with real users.
- [ ] Threat model precise coordinate storage, exports, logs, and screenshots.
- [ ] Verify every number, citation, and deadline in the demo against current primary sources.
- [ ] Prepare a 3 minute demo using real Ohio evidence only; label any simulated data.

## Decision log

| Date       | Decision                          | Reason                                                               | Revisit                                                                            |
| ---------- | --------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 2026-10-23 | Start with files, not a database  | Survey and pilot are single team batch workflows; fewer moving parts | Add a database when concurrent review, access controls, or query volume require it |
| 2026-10-23 | Show sample data explicitly in UI | No Ohio detection has been validated in this repository              | Replace with versioned, reviewed exports after M0–M3                               |
| 2026-10-23 | Gate full build on Ohio symbols   | A core source assumption is unresolved                               | After reviewed M0 evidence                                                         |

## Run log template

For each real data run, append a dated record to `RUN_LOG.md` with: input manifest hash, code commit, model version, parameters, counts at each stage, review sample, errors, and output paths. Avoid writing precise leads into public Git history.

## Definition of done

The project can demonstrate one complete, reproducible Ohio workflow from source scan to private, reviewable lead with measured uncertainty. The public experience reveals no exact candidate locations. All data, models, scores, and impact claims are sourced and accurately labeled. `npm run check` and Python tests pass, the UI passes mobile and keyboard review, and the release is reproducible from a clean clone.
