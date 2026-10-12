# EXP-004 synthetic ABACAD cadence

This run is a known-answer fixture. It is not a telescope observation and it is not a sensitivity claim. `demo` stays false so the page does not show the placeholder badge; every hit explanation says the cadence is synthetic.

## What it checks

Six seeded setigen frames use the EXP-002 channel width and integration length. The scan order is A, B, A, C, A, D. A is on source. The line, when it continues across scans, is injected at the frequency reached by that scan's start.

| Injection | Where it is planted | Drift | Expected verdict |
|---|---|---:|---|
| `on_only` | the three A scans | +0.8 Hz/s | `ON_ONLY` |
| `in_off` | all six scans | 0 Hz/s | `IN_OFF` |
| `single_pointing` | the first A scan only | +0.3 Hz/s | `SINGLE_POINTING` |
| `known_source` | the three A scans, inside `configs/fixtures/exp004_known_sources.yaml` | +0.6 Hz/s | `KNOWN_SOURCE` |

The catalog range `synthetic known-answer band` is a fixture. It is not a catalogued transmitter. Real ranges are added only with a primary source.

## Search and labels

`xenia live cadence --synthetic` runs `FindDoppler` on each file (`max_drift` 4 Hz/s, SNR 10, one coarse channel), then turboSETI `find_event_pipeline` with filter threshold 3. Zero-drift hits are kept so a line in an OFF scan can still be labelled. The known final-logging `TypeError` is wrapped the same way as EXP-001 and EXP-002.

`xenia.live.verdict` applies spec section 4.5 in order: known source, then OFF, then fewer than three ON scans, then a ±1 kHz hit in another cadence of the same session, then `ON_ONLY`. The function cannot return `UNEXPLAINED`. The five section 8.6 checks are booleans with notes. Review is recorded as not done.

## How to run

```bash
make cadence-synthetic
```

The reduced frame (8192 channels, same integrations) is `make cadence-synthetic-reduced`. CI runs that reduced path from the test suite. Both modes use seed `20261012`.

Outputs under `runs/<RUN_ID>/`:

- `manifest.json` with `mission_control.kind` of `cadence` and outcome `searched_with_survivors` when an `ON_ONLY` hit is present
- `hits.parquet` (polars 1.44.2 native writer), one row per matched injection, including the five check booleans. PyArrow was not used: releases 23.0.1 through 26.0.0 have no CPython 3.15 wheel, and building 23.0.1 from source stopped because `cmake` is not installed.
- `truth.json` and `recovery.json`
- an SVG thumbnail per hit so the gallery can render

Inputs are `synthetic://exp-004/...` URIs with the SHA-256 of each temporary filterbank. The filterbanks are deleted after the search and are not committed.

`make live-evidence` renders the cadence as a pointing. The gallery tile explanation says the cadence is synthetic.

## Measured full run

`make cadence-synthetic` wrote run `20261012T194125275790Z-exp-004-cadence`. The manifest records git SHA `e9db4be`, which is the commit the run started from. Started `2026-10-12T19:41:25.275790Z`, finished `2026-10-12T19:41:32.741860Z` (7.466070 s inside the command). `/usr/bin/time -p` reported `real 8.52` for the make target.

Outcome `searched_with_survivors`. `recovery.json` has `all_matched` true. Manifest notes: `IN_OFF=1, KNOWN_SOURCE=1, ON_ONLY=1, SINGLE_POINTING=1`. Unassigned detections 0. Unassigned filter-3 events 0. Filter-3 events retained 2. One known-source range was loaded. The known turboSETI final-logging `TypeError` is recorded four times; the `.dat` rows were kept.

Highest-SNR detection per injection, from `hits.parquet`, and the association residual from `recovery.json`:

| Injection | Verdict | Frequency (MHz) | Drift (Hz/s) | SNR | Frequency error (Hz) | Drift error (Hz/s) |
|---|---|---:|---:|---:|---:|---:|
| `on_only` | `ON_ONLY` | 5999.998894 | 0.765319 | 22.151714 | 0.0 | 0.03468100000000007 |
| `in_off` | `IN_OFF` | 5999.994968 | 0.010204 | 43.487137 | 2.8580970764160156 | 0.010204 |
| `single_pointing` | `SINGLE_POINTING` | 5999.991059 | 0.306128 | 38.991108 | 0.30328369140625 | 0.006128000000000022 |
| `known_source` | `KNOWN_SOURCE` | 5999.987505 | 0.591847 | 27.371674 | 0.0 | 0.002051000000000025 |

Each row has `checks_done` 4 and `review` false. The injected zero-drift line was not labelled at exactly 0 Hz/s: its highest-SNR detection is `+0.010204` Hz/s, so the drift check note says the drift is not zero. The `IN_OFF` verdict comes from the line being present in 3 OFF scans. The `ON_ONLY` and `KNOWN_SOURCE` rows passed the filter. The single-pointing row did not.

The reduced CI test is `tests/test_cadence_reduced.py`. A pytest run of that file together with `tests/test_cadence_synth.py` reported `3 passed in 6.25s`.
