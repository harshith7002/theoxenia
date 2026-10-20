# First public release: recorded evidence

Public evidence edition, 2026-10-20; prepared 2026-10-18. This release makes the existing research inspectable; it does not assert that the 24/7 crawler has passed its acceptance test. No new telescope observation was made. PUB-002 reruns and audits the detector on the existing six archive slices; see [the first research report](first-research-report.md). PUB-001 fetched and processed six bounded archive slices for the interactive previews; all six match the original experiment's local-slice checksums.

## What a visitor can do

Follow three guided investigations (Voyager, HIP544 archive search, synthetic recovery); filter and inspect all 273 measured archive rows; zoom and pan six measured waterfall previews; select recovery-grid cells; download checksummed evidence dossiers; and browse the lab notebook, including failed attempts. Core stories, complete tables, dossiers and downloads work without JavaScript. Linked selection and canvas previews use small local scripts. No remote fonts, images, analytics or runtime data services are required. See [the investigation implementation and scientific boundaries](investigations.md).

The archive search is run `20261012T203545022355Z-exp-003-cadence`: one observed cadence, one completed window, 273 labelled rows, 149 in the OFF scans, 124 single-pointing hits, zero survivors. The gallery shows only three selected rows. Synthetic practice cadences are excluded from those observational totals. Repeated attempts at the same cadence/window use the latest finished record rather than accumulating duplicate exposure. Distinct windows remain distinct search work; hits are counted per window, not as globally unique transmitters.

The latest committed full calibration is matching version 2, run `20261012T190848550861Z-exp-002-floor`. Some nonzero-drift cells recover; no tested SNR row recovered every trial across ±3 Hz/s. Earlier version-1 results remain in the notebook as history. This is detector regression evidence, not telescope completeness.

## Build and preview

From the repository root, after installing the locked development environment:

```bash
uv run --locked python scripts/build_public_site.py --output .preview/release-v1
uv run --locked mkdocs build --strict --site-dir .preview/release-v1/docs
uv run --locked python -m http.server 8769 --bind 127.0.0.1 --directory .preview/release-v1
```

Use a new or empty output directory. The builder refuses to overwrite an existing build. It reads committed run evidence, writes a static snapshot and build metadata, and neither starts the worker nor creates new experiment manifests. Identical input records, commit and build clock produce identical rendered content. The manifest and asset links are tested locally.

## Branch and deployment policy

Michael requested consolidation onto `main` on 2026-10-18. All existing feature work and the five remaining PRs (#24–#28) were integrated. Source, templates, schemas and recorded evidence now travel together on `main`. The old `live`-branch deployment instructions are superseded for this release. Do not create `live` or run the old handover's `git push origin main:live` command.

The Pages workflow is manual-only. It builds Mission Control at the site root and project documentation under `/docs/`, both from `main`. Pushing code does not deploy it automatically. The release destination is [Mission Control](https://mpetyx.com/theoxenia/) with [documentation](https://mpetyx.com/theoxenia/docs/). Michael authorized publication and Pages launch on 2026-10-20. The original preparation changed no hosting settings.

Deployments use GitHub Pages with GitHub Actions as its source and the manual Pages workflow on `main`. Verify the returned URL, images, manifest links, phone layout and snapshot status after each deployment. The default base URL is `https://mpetyx.com/theoxenia/`; change the builder argument if the actual destination differs.

## What still needs scientific or operational work

- The empty-table diagnosis is resolved for this configuration in PUB-002. Rerun the historical recovery grid under the corrected detector and test broader inputs before generalizing sensitivity. Crowded-data selection losses remain measured limitations; the original warnings and outputs stay intact.
- Grow beyond the currently recorded cadence and complete measured queue coverage. The original MVP asks for at least 100 cadences.
- Validate a persistent host, recovery and a 24-hour unattended run with at least 50 pairs before presenting a live-service claim. The existing 60-minute synthetic run is not that proof.
- Design worker-result persistence for the single-branch policy. The legacy worker publisher intentionally refuses to commit to `main`; it remains off. The legacy pulse workflow is also inactive.
- Finish OCR corpus validation, historical satellite coverage and other environmental checks before expanding their public claims.

## Public release receipt

On 2026-10-20, Zenodo confirmed report record `23489303` as published (`submitted=true`, `state=done`). Its public record exposes all 14 verified files, totaling 5,969,135 bytes. The approved report date remains 2026-10-18; the publication action occurred on October 20. Authorship and licenses remain as approved: Michael Petychakis, sole author without affiliation or ORCID; report CC BY 4.0, code Apache-2.0, original upstream terms preserved.

The [first Pages deployment](https://github.com/mpetyx/theoxenia/actions/runs/39372152239) succeeded from `9cdd87b9294dedbc7e6b447574ea590de1d90b4e`. Pages uses the owner's existing `mpetyx.com` domain and enforces HTTPS. [Release CI](https://github.com/mpetyx/theoxenia/actions/runs/39372152334) passed 231 tests with 84.29% coverage, strict typing across 44 files and all configured quality gates.

Public HTTP checks passed for the main entry points, documentation, report PDF and evidence download. The public PDF is byte-identical to the frozen Zenodo package. Browser interaction verified that the explorer filters 273 rows to 149 `IN_OFF` rows and resets correctly.

The [Notion release handoff](https://app.notion.com/p/3fd073ddfc5c8179b136cd7fda8be037) and project navigation now reflect the release. All 41 task rows, 10 experiment rows, 19 source rows and five case records were reviewed; 22 task rows and eight experiment rows were reconciled. Historical instructions remain identified as history, including superseded branch and experiment-number aliases. OCR corpus acceptance was corrected to incomplete, and the 24-hour worker acceptance remains open. The launch did not change existing case classifications or turn a DOI into external scientific review.

## Validation

The release checks cover aggregate counts against the committed archive record, synthetic/observed separation, repeat-window deduplication, invalid count rejection, HTML escaping, all local HTML asset and navigation targets, and two independent snapshot builds. Strict typing is blocking again after clearing the inherited 31 errors; YAML and pandas are explicitly listed with the other untyped external libraries. Desktop and a 360 px browser-frame layout were inspected; this is not a claim of physical iOS/Android testing.

The original branch history was preserved in a verified Git bundle outside the checkout before consolidation. Historical run artifacts were not rewritten.

Validation on 2026-10-18: 208 tests passed with 83.76% coverage; all optional disclosure dependencies installed. Strict typing: 42 source files clean. Lint, formatting, schema freshness, file policy, public copy scan, experiment index and strict documentation build passed. The archive Parquet verdict totals were independently read and match 149 IN_OFF + 124 SINGLE_POINTING.

The investigation expansion adds parity checks between every exported row and the source Parquet, rejection of changed checksums and wrong provenance, deterministic downloads, complete no-script tables, and dossier bundle integrity. The expanded suite passed 212 tests with 84.04% coverage; strict typing is clean across 43 source files. Browser checks cover selection, filtering, reset, empty results, frequency zoom, contrast, recovery cells and missing-check labels. Stories, explorer, recovery and dossier layouts were checked in a 360 px browser frame, not on a physical phone. The recorded real-data preparation is `20261018T175821546488Z-public-evidence`.

PUB-002 report validation: 231 tests passed with 84.29% coverage; strict typing is clean across 44 source files. The full one-command original/corrected reproduction passed at source revision `3b971bc`, including exact counts, recoveries, drift coverage and 0.005-score maximum tolerances. The report page and evidence download were checked in the browser, including a 360 px frame. See `reports/first-results/VALIDATION.md` for the four new immutable run IDs. Report version 1.0 was published on 2026-10-20: [DOI 10.5281/zenodo.23489303](https://doi.org/10.5281/zenodo.23489303). Its 14 files preserve the verified source snapshot at `4b1203d`. The site links to that fixed research record; later presentation changes do not rewrite the report evidence.
