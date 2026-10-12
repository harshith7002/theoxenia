# Mission Control EXP-002: synthetic injection/recovery floor

**Source of truth:** the [Mission Control MVP brief](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac). This experiment is a controlled detector calibration using synthetic data; it is **not** an observation and does not establish a telescope sensitivity limit.

## Acceptance scope

The dashboard’s recovery-floor panel is derived from a typed `EXP-002` artifact, not hand-entered percentages. The full run covers the brief’s 8 SNR values × 9 drift values × 5 independent trial seeds; every cell must have exactly five recorded decisions. The pull-request smoke mode covers the reduced 3 × 3 subset with one seed. The exact axes and repeat counts are centralized in `src/xenia/radio/floor_config.py` and enforced by `RecoveryGridArtifact` validation.

| Mode | Injected SNR | Drift rate (Hz/s) | Trials per cell | Injections | Detector searches |
|---|---|---|---:|---:|---:|
| Reduced (PR) | 5, 15, 40 | −4, 0, +4 | 1 | 9 | 1 |
| Full (nightly/on demand) | 5, 8, 10, 12, 15, 20, 30, 40 | −4 through +4 in 1 Hz/s steps | 5 | 360 | 5 |

## Generation and detector method

Each independently seeded trial creates one setigen frame with 16 time integrations and 131,072 frequency channels. The frame uses 2.7939677238464355 Hz channel spacing, 18.253611008 s integrations, chi-squared noise with mean 1, and a fixed center frequency near 6 GHz. One signal is injected for every SNR/drift cell into a frequency slot separated by 1,600 channels. All injected signals in a given trial therefore share that trial’s seeded noise realization; the five full-mode trials use different consecutive seeds.

Signals use setigen’s constant time profile, Gaussian frequency profile, linear constant-drift path, and its documented radiometer-noise SNR intensity calibration. Doppler smearing uses 64 sub-samples per integration; at the grid’s maximum 4 Hz/s drift, the line moves about 26 fine channels in one 18.25 s integration, so eight sub-samples would under-resolve the path. The experiment records the frame dimensions and units, center and starting frequencies, signal width, subsampling, noise settings, seeds, frequency-slot spacing, detector options, and package versions. The `setigen` package’s public repository and `Frame` implementation are the primary API references: [setigen source](https://github.com/bbrzycki/setigen) and [Frame source](https://github.com/bbrzycki/setigen/blob/main/setigen/frame.py).

Each trial is written to a temporary SIGPROC filterbank with neutral synthetic metadata (`XENIA-SYNTHETIC`, zero telescope/machine IDs, and zero coordinates). The file is passed to [turboSETI](https://github.com/UCBerkeleySETI/turbo_seti) with SNR threshold 5, maximum absolute drift 4 Hz/s, one coarse channel, and one search partition. A hit recovers an injection only when its uncorrected frequency is within three frequency channels of the signal’s midpoint frequency, its drift is within two drift-resolution bins, and its SNR meets the configured threshold. Matching is one-to-one: a detector hit cannot recover two injected signals. Hits, trial seeds, error offsets, detector warnings, and temporary `.dat` output checksums/sizes are retained in the grid artifact.

The temporary filterbanks and detector tables are removed after each trial. They are not committed or copied into the artifact directory. The run writes `recovery_grid.json` and `manifest.json`; failed runs write `failure.json` and a failed manifest, preserving completed partial searches/measurements instead of manufacturing a floor.

## Reproduce

```bash
uv python install 3.15.0
uv sync --locked --all-groups --extra radio --python 3.15.0
make floor-smoke       # Reduced 3 × 3 grid (9 synthetic injections, 1 search)
make floor             # Full 8 × 9 × 5 grid (360 injections, 5 searches)
make floor-evidence    # Full run, state rebuild/schema validation, and static render
```

To validate a specific artifact independently:

```bash
xenia schemas validate-floor --grid runs/<RUN_ID>/recovery_grid.json
```

`runs/<RUN_ID>/manifest.json` contains the exact command and parameters, `EXP-002` linkage, code SHA, package versions, UTC timestamps, outcome, artifact hash/size, and notes. The grid JSON is itself schema-validated and records every injection decision and detector hit. The Mission Control state builder computes the plotted fraction from those validated records and links the panel to the experiment manifest.

## Continuous integration

`.github/workflows/exp-002-floor.yml` runs the reduced deterministic grid on pull requests, the full grid nightly, and either mode on manual dispatch. It then validates the generated recovery-grid and `LiveState` schemas, rebuilds/renders Mission Control, and uploads the run directory, state, and static page as a 30-day Actions artifact. The current Actions URL is carried through the typed payload and rendered as an optional dashboard link. The workflow needs no repository secrets and grants read-only repository permissions.

## Interpretation limits

This is a reproducible **synthetic detector regression test**, not a statement about a telescope’s limiting flux or completeness. The grid does not model an instrument bandpass, a calibrated receiver system temperature, real RFI, quantization/ADC effects, observation-specific masks, or signal populations. A zero-recovery cell is retained as a null result, not reworded as a scientific discovery or proof of absence. Do not compare its SNR values directly with a real observation’s SNR without a separately validated instrument/noise calibration.

## Sources

- [Mission Control MVP and EXP-002 acceptance brief (Notion)](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac)
- [setigen project and source](https://github.com/bbrzycki/setigen)
- [turboSETI project and source](https://github.com/UCBerkeleySETI/turbo_seti)
- [CPython 3.15.0 release](https://www.python.org/downloads/release/python-3150/)
- [Locked dependency and compatibility evidence](DEPENDENCIES.md)
- [EXP-001 Voyager source verification](data-sources.md)

## Current status note

This document describes the implementation and acceptance method. A real experiment result is only complete when its `runs/<RUN_ID>/manifest.json` and `recovery_grid.json` are present, the `make` gates pass, and that run ID is linked from the live Notion Experiment record. The CI artifact is separately identified by its GitHub Actions URL. A locally rendered preview is not a deployment.
