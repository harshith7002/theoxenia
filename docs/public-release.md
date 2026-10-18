# First public release: recorded evidence

Prepared 2026-10-18. This release makes the existing research inspectable; it does not assert that the 24/7 crawler has passed its acceptance test. No new observation was run for this redesign.

## What a visitor can do

Explore the recorded Voyager waterfall; understand the six-scan ON/OFF method; inspect the real sky pointing; read the synthetic recovery grid cell by cell; follow the complete verdict counts to their manifests; open individual hit pages; and browse the lab notebook, including failed attempts. The interface works without JavaScript or remote fonts and images.

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

The Pages workflow is manual-only. It builds Mission Control at the site root and project documentation under `/docs/`, both from `main`. Pushing code cannot trigger the first public deployment. No Pages setting, host, domain, account or paid resource was changed during preparation. The Pages API returned 404 during inspection; there is no verified public URL yet.

The next deployment session should enable GitHub Pages with GitHub Actions as its source, run the Pages workflow on `main`, then verify the returned URL, images, manifest links, phone layout and snapshot status. The default base URL is `https://mpetyx.github.io/theoxenia/`; change the builder argument if the actual destination differs.

## What still needs scientific or operational work

- Investigate the empty later ON scans in EXP-003 before drawing broader null-result conclusions. The original warnings and outputs remain intact.
- Grow beyond the currently recorded cadence and complete measured queue coverage. The original MVP asks for at least 100 cadences.
- Validate a persistent host, recovery and a 24-hour unattended run with at least 50 pairs before presenting a live-service claim. The existing 60-minute synthetic run is not that proof.
- Design worker-result persistence for the single-branch policy. The legacy worker publisher intentionally refuses to commit to `main`; it remains off. The legacy pulse workflow is also inactive.
- Finish OCR corpus validation, historical satellite coverage and other environmental checks before expanding their public claims.
- Reconcile the older Notion task and pipeline pages: some still say merged work is unmerged, and older EXP-004/EXP-030 definitions conflict with later Mission Control assignments. This document records the implementation boundary; it does not silently mark those scientific tasks complete.

## Validation

The release checks cover aggregate counts against the committed archive record, synthetic/observed separation, repeat-window deduplication, invalid count rejection, HTML escaping, all local HTML asset and navigation targets, and two independent snapshot builds. Strict typing is blocking again after clearing the inherited 31 errors; YAML and pandas are explicitly listed with the other untyped external libraries. Desktop and a 360 px browser-frame layout were inspected; this is not a claim of physical iOS/Android testing.

The original branch history was preserved in a verified Git bundle outside the checkout before consolidation. Historical run artifacts were not rewritten.

Validation on 2026-10-18: 208 tests passed with 83.76% coverage; all optional disclosure dependencies installed. Strict typing: 42 source files clean. Lint, formatting, schema freshness, file policy, public copy scan, experiment index and strict documentation build passed. The archive Parquet verdict totals were independently read and match 149 IN_OFF + 124 SINGLE_POINTING.
