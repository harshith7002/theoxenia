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

Each trial is written to a temporary SIGPROC filterbank with neutral synthetic metadata (`XENIA-SYNTHETIC`, zero telescope/machine IDs, and zero coordinates). The file is passed to [turboSETI](https://github.com/UCBerkeleySETI/turbo_seti) with SNR threshold 5, maximum absolute drift 4 Hz/s, one coarse channel, and one search partition. Matching version 2 recovers an injection only when all of the following hold:

- The hit’s uncorrected frequency lies within three fine channels of the injected path. The path runs from `start_frequency_mhz` across the 16 integrations. turboSETI 2.3.2 writes the same channel into the corrected and uncorrected columns (`chan_freq` ignores the reference frame), so the reported channel is not pinned to the start of the observation.
- The hit’s drift is within three of turboSETI’s own drift-resolution bins of the injected physical drift. That bin is `|foff| / ((n_integrations − 1) · tsamp)` = 0.010204 Hz/s here. A seed-20261012 full-width probe at SNR 40 put real `|drift| ≤ 3` Hz/s hits 0, 1, 2, and 3 bins off, so the previous two-bin window dropped them. The tolerance was not opened past three bins.
- The hit’s SNR meets the configured threshold.

The frame is built with `ascending=False`. turboSETI flips the drift label when `DELTAF < 0` (`find_doppler.py`). Recovered hits in the v2 grid keep the injected sign, so the setigen and turboSETI signs agree for these descending files. Matching is one-to-one: a detector hit cannot recover two injected signals. The grid artifact records `matching_version: 2` and the `matching_rule` string. Hits, trial seeds, error offsets, detector warnings, and temporary `.dat` output checksums/sizes are retained. Version 1 artifacts omit `matching_version`; the field defaults to 1.

The temporary filterbanks and detector tables are removed after each trial. They are not committed or copied into the artifact directory. The run writes `recovery_grid.json`, a row-major `sweep.csv` summary, and `manifest.json`; failed runs write `failure.json` and a failed manifest, preserving completed partial searches/measurements instead of manufacturing a floor.

The CSV has one row per SNR/drift cell in the artifact's defined axis order. Its columns are `snr`, `drift_hz_s`, `trials`, `recovered_count`, `recovered_fraction`, and `recovered_seeds`; the last field is a compact JSON array of the seeds that recovered that cell (`[]` when none did). Both the JSON grid and CSV have checksums and sizes in the run manifest.

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

`runs/<RUN_ID>/manifest.json` contains the exact command and parameters, `EXP-002` linkage, code SHA, package versions, UTC timestamps, outcome, artifact hashes/sizes, and notes. The grid JSON is itself schema-validated and records every injection decision and detector hit; the CSV is a deterministic per-cell summary derived from that validated grid. The Mission Control state builder computes the plotted fraction from those validated records and links the panel to the experiment manifest.

## First full-grid result

Run `20261012T140202855194Z-exp-002-floor` completed on 2026-10-12 from code commit `f2030e7` with seed `20261012`. It contains all 360 injection decisions across five independently seeded detector searches. The 258,181-byte `recovery_grid.json` validates against the committed Pydantic schema; its SHA-256 is `b22f2bf0d2e438dda20897dba5a21cd623dd5c2a929091ba1b429fbbcb40da45`.

At 0 Hz/s, the detector recovered 2/5 injections at SNR 5 and 5/5 at every tested SNR from 8 through 40. At every nonzero drift from −4 through +4 Hz/s, it recovered 0/5. Therefore the grid establishes a zero-drift result only; no tested SNR reached full recovery across the dashboard’s ±3 Hz/s summary range. The corresponding static state/render runs are `20261012T140257833721Z-build-state` and `20261012T140258815795Z-render`. These values describe the synthetic generator and tested detector configuration only; they are not a calibrated telescope sensitivity curve.

All five turboSETI searches also emitted the recorded final candidate-count logging `TypeError` after writing parseable `.dat` rows. The adapter retained results only when the output parsed and passed its structural checks; the warning remains in the manifest and artifact. It did not treat an incomplete output as a successful null result.

That grid is retained as a bug. Version 1 compared turboSETI’s uncorrected frequency with the mid-observation centre. A 1 Hz/s line starts about 146 Hz away from that centre, and the three-channel tolerance is 8.4 Hz, so every nonzero drift missed. The Experiment row for this run is `Bug · invalid`.

## Second full-grid result (matching version 2)

Run `20261012T190848550861Z-exp-002-floor` completed on 2026-10-12 from code commit `e9db4be` with the same seed `20261012`. It contains all 360 injection decisions. `recovery_grid.json` is 273,572 bytes, SHA-256 `77f84624867ed5e1a2bf9e1e2409270284254f090162ee9b25474a8e4804a234`. `sweep.csv` is 2,352 bytes, SHA-256 `54a99746a0e208541ccf6ec8dd72c8fd4e5e4fab9f90504fd62b984a2a8ab343`. `matching_version` is 2. Started `2026-10-12T19:08:48.550861Z`, finished `2026-10-12T19:08:56.993088Z`.

Recovered counts out of 5, rows SNR 5, 8, 10, 12, 15, 20, 30, 40 and columns drift −4, −3, −2, −1, 0, +1, +2, +3, +4 Hz/s:

| SNR | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 | +4 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| 8 | 0 | 0 | 0 | 1 | 5 | 0 | 0 | 0 | 0 |
| 10 | 0 | 0 | 0 | 1 | 5 | 3 | 0 | 0 | 0 |
| 12 | 0 | 0 | 0 | 3 | 5 | 4 | 0 | 0 | 0 |
| 15 | 0 | 0 | 0 | 3 | 5 | 4 | 0 | 0 | 0 |
| 20 | 0 | 0 | 4 | 4 | 5 | 5 | 1 | 0 | 0 |
| 30 | 0 | 0 | 3 | 4 | 5 | 3 | 1 | 1 | 0 |
| 40 | 0 | 0 | 1 | 2 | 5 | 2 | 2 | 1 | 0 |

Nonzero-drift cells recover. The strongest of those is 5/5 at +1 Hz/s for SNR 20. No SNR row is 5/5 across every column inside ±3 Hz/s, so `floor_summary` does not emit “Recovers SNR ≥ N at drift within ±3 Hz/s.” The computed sentence is: “At 0 Hz/s, full recovery begins at SNR ≥ 8; best nonzero-drift recovery was 100%. No tested SNR reached full recovery across ±3 Hz/s.” The ±4 Hz/s columns stayed at 0/5. On a separate SNR-40 probe, those lines did not rise cleanly out of the noise: a 4 Hz/s line moves about 26 fine channels inside one 18.25 s integration, and the detected SNR of |drift| = 3 Hz/s lines was about 9–10 against an injected SNR of 40. Drift errors on the missed high-SNR hits were often 4 or more detector bins, past the three-bin cap. That is a measured limit of this generator-plus-detector pair, not a hand-entered floor.

The unit test `test_floor_summary_is_computed_from_the_recovery_grid` still locks the “Recovers SNR ≥ N” branch on a complete synthetic grid. `test_committed_v2_floor_summary_reports_partial_nonzero_recovery` locks the sentence computed from this run.

## Continuous integration

`.github/workflows/exp-002-floor.yml` runs the reduced deterministic grid on pull requests, the full grid nightly, and either mode on manual dispatch. It then validates the generated recovery-grid and `LiveState` schemas, rebuilds/renders Mission Control, and uploads the run directory, state, and static page as a 30-day Actions artifact. The current Actions URL is carried through the typed payload and rendered as an optional dashboard link. The workflow needs no repository secrets and grants read-only repository permissions. GitHub starts scheduled runs only after this workflow is present on the default branch; this feature branch has not had a nightly Actions run.

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

The full local run and schema validation are complete. The EXP-002 task and Experiment records still need the run ID, result summary, and code/artifact links recorded in live Notion before this run is fully linked. PR checks and the reduced-grid workflow are pending push; the scheduled full-grid workflow will become active after merge to the default branch. A locally rendered preview is not a deployment.
