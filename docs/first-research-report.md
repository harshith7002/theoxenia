# First reproducible research report

**Empty tables, tested boundaries** is report 01, prepared for Zenodo on 18 October 2026. It is unpublished, has no DOI and has not received external peer review. The public research page offers the PDF, figure, results table and verified evidence bundle. Sources are in `reports/first-results/`.

## What the work establishes

All six bounded 1380–1381 MHz HIP544 cadence slices match their original SHA-256 hashes. Replaying the original detector reproduces 186, 149, 0, 0, 0 and 0 per-scan hits. An independently implemented straight-track sum also stays below the threshold of 10 in the four empty scans. These are valid below-threshold results at this configuration, not evidence of a generally empty sky.

Instrumentation revealed that the original requested ±4 Hz/s search covered only ±3.826596 Hz/s. A scoped, hash-verified correction for the pinned turboSETI 2.3.2 CPU search extends coverage to the last grid point inside the request, ±3.989864 Hz/s. It also fixes a final count-formatting error. The corrected search adds one OFF-scan hit, producing 186, 150, 0, 0, 0 and 0 hits. The historical 273-row clustered table is unchanged; no new complete cadence clustering is claimed.

On identical five-track injected copies, recovery changes from 15/30 to 24/30, including all 20 controls in the four empty scans. Near-boundary recovery changes from 0/12 to 9/12. A passive observer shows all six remaining misses cross the internal threshold but lose the stronger-neighbor selection. The observer must return exactly the same top-hit rows as the original call.

## Reproduce and inspect

From the locked repository environment:

```bash
uv sync --locked --all-groups --extra radio --python 3.15.0
uv run --locked --extra radio python scripts/reproduce_report.py
```

The command downloads bounded slices, writes new manifests, compares the original diagnosis, audits selection, and repeats the corrected checks. It makes no external submission. Approximately 518 MB of transfer and 1 GB of scratch space are needed; optional `--reuse-cache` verifies the six original hashes before reuse.

The corrected diagnosis is `20261018T183744725763Z-detector-corrected`; the selection audit is `20261018T183947862671Z-control-selection`. Original diagnosis and independent reproduction records are pinned in `reports/first-results/package.json`. Exact commands, parameters, versions, processor snapshots, times and output hashes are preserved. Raw observations are not committed.

## Remaining work

This is one cadence and one 1 MHz window. Control tracks are idealized and do not estimate detection probability or calibrated flux limits. Crowded-field selection, interference, drift mismatch, bandpass structure and time variability need broader validation. Rerun the historical recovery grid before using it to calibrate the corrected detector. The session census, physical-origin classification and independent external review remain unfinished. GPU execution and other upstream source versions are not validated.

## Publication

The offline package builder verifies pinned artifacts, includes the exact committed source and creates checksums. Run it from a clean tracked checkout:

```bash
uv run --locked python scripts/package_report.py --output .preview/zenodo-report
```

Zenodo supports a [REST API](https://developers.zenodo.org/) for creating drafts, uploading files and explicitly publishing. Draft preparation uses `deposit:write`; publication requires `deposit:actions`. Tokens should remain local and must not enter the package. The website is an alternative. A [reserved DOI](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/) can be inserted before final upload; registration occurs on publication. A DOI provides attribution and preservation, not scientific endorsement. Owner review of authorship, metadata and final files remains before publication.
