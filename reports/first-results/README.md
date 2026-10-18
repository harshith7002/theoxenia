# Theoxenia research report 01: reproducibility package

Prepared for Zenodo. No deposit, DOI, external review or public deployment is
implied by these files. Read report.pdf (or report.md) for findings and limits.

## Contents and licenses

- report.pdf / report.md: narrative, results, limitations and references.
- theoxenia-evidence.zip: immutable compact outputs and original manifests.
- theoxenia-source.zip: exact committed source snapshot, including uv.lock,
  reproduction scripts, tests, report sources and all repository licenses.
- metadata.json: Zenodo deposition metadata; no invented DOI or affiliation.
- SHA256SUMS: hashes for all upload-package files except the checksum list itself.
- SOURCE_REVISION.txt: full source revision used to build the package.
- VALIDATION.md: recorded full reproduction and release-check results.
- SUBMISSION.md: API, website and software-release publication routes.

Code: Apache-2.0. Authored report, figures and derived diagnostic summaries:
CC BY 4.0. Source observations and third-party software keep their own terms.
No raw telescope data is included. Credit Breakthrough Listen / GBT and upstream
tools as described in the report. Hashes identify local slices, not whole remote
archive objects. A DOI is not peer review.

## Verify without fetching data

On macOS run `shasum -a 256 -c SHA256SUMS` in the upload package. On Linux use
`sha256sum -c SHA256SUMS`. Extract the evidence ZIP into an empty directory and
verify its internal SHA256SUMS the same way. Each run also has output hashes in
manifest.json. Source files live in the separately checksummed source ZIP.

## Reproduce the science

Extract the source ZIP into an empty directory, then enter that directory.
Install uv >=0.13 and its Python 3.15.0 runtime. On Linux, HDF5 development
headers and a compiler may be needed for h5py; see the repository CI workflow.

```bash
uv sync --locked --all-groups --extra radio --python 3.15.0
uv run --locked --extra radio python scripts/reproduce_report.py
```

The command performs the original and corrected checks, writes new manifests,
and checks the declared counts, controls, drift coverage and maximum-score
tolerance (0.005). It does not replace earlier runs or submit anything. Archive
access is required: approximately 518 MB of HTTPS transfers, capped at 256 MiB
per file, and approximately 1 GB of scratch space. The measured initial run took
about six minutes on the author's machine; time depends strongly on network and
hardware. No GPU or paid service is used. Scratch inputs and injected copies
stay under ignored data/detector-diagnosis/ and may be removed after inspection.
`--reuse-cache` is optional; it verifies all six historical input hashes first.

The independent reference includes zero drift; turboSETI excludes it. Its
nearest-channel tracks differ from the Taylor tree. Reproduction is an empirical
check on this dataset/configuration, not a proof of completeness or a flux limit.

## Regenerate figures and PDF from recorded evidence

```bash
uv run --locked --extra radio python scripts/plot_report.py
uv run --locked --extra reports python scripts/render_research_report.py
```

PDF rendering is pinned to ReportLab 4.4.9. The scientific evidence is already
recorded; figure/PDF rendering makes no archive requests and no new measurements.

## Rebuild the upload package

In a clean Git checkout of the source revision (the extracted ZIP is sufficient
for scientific reproduction, but packaging needs Git commit identity):

```bash
uv run --locked python scripts/package_report.py --output .preview/zenodo-report
```

The builder verifies every included manifest artifact, refuses modified tracked
files and an existing output directory, and produces deterministic evidence ZIP
entries. It neither reads credentials nor makes network calls. Report metadata
must be reviewed before submission; follow SUBMISSION.md. The website's original
273-row explorer remains explicitly historical, separate from this corrected run.
