# Validation record — report 01

## Complete reproduction

Executed on 18 October 2026 from committed main revision `3b971bc`:

```bash
uv run --locked --extra radio python scripts/reproduce_report.py --reuse-cache
```

Result: **REPRODUCTION PASSED**. All six cached slices were checked against their
original SHA-256 hashes. Original and corrected counts and control recoveries
matched exactly. Both independent and upstream maxima matched the corresponding
recorded values within 0.005 normalized-score units. Corrected drift coverage and
selection-audit conditions passed. Passive selection instrumentation returned
exactly the recorded top-hit rows.

New immutable records, all included in package.json:

- Original diagnosis: `20261018T184921525048Z-detector-diagnosis`
- Original selection audit: `20261018T185007664549Z-control-selection`
- Corrected diagnosis: `20261018T185013498663Z-detector-corrected`
- Corrected selection audit: `20261018T185111223714Z-control-selection`

This is a repeat on the author's machine using verified cached inputs. It is not
independent external reproduction or a second telescope observation. The earlier
fresh-download run recorded approximately 518 MB of transfers and exact agreement
with all six historical local-slice hashes.

## Software and presentation checks

The complete local suite passed 231 tests with 84.29% coverage. Strict typing is
clean across 44 source files. Lint, formatting, schema freshness and validation,
file policy, experiment index and strict documentation build passed. The tests
cover missing/stale output, exception handling, both drift-boundary directions,
compatibility restoration, independent track geometry, changed-evidence rejection,
source/summary parity, deterministic ZIP entries and static navigation/downloads.

All five PDF pages were visually inspected. Regenerating the PDF produced identical
bytes. The research page, figure, table, publication status and evidence-download
link were inspected in the browser; the layout was also checked in a 360 px frame.
This is not physical-device testing. A follow-up test checks every checksum in the
website evidence bundle's SHA256SUMS after that list was added.

The final upload folder records its exact source revision in SOURCE_REVISION.txt;
its checksums cover the report, metadata, source ZIP and evidence ZIP. Publication,
a DOI, upstream acceptance and public deployment are separate future actions.
