# PUB-002: empty-table investigation protocol

Recorded before interpreting the diagnostic results. Source: EXP-003 run
`20261012T203545022355Z-exp-003-cadence`, six HIP544 ABACAD scans at 1380-1381 MHz.
Diagnostic implementation checkpoint: `7241ef8`.

## Question

Why did scans 3-6 have no reported hits? Distinguish a broken input, a detector
failure, and signals below the chosen threshold. An empty table is not by itself
a null result about extraterrestrial transmitters.

## Checks

1. Re-fetch only the original window using bounded HTTPS reads (256 MiB/file).
   Require all six local-slice SHA-256 values to match the historical manifest.
2. Verify finite, positive native power. Record per-integration means/medians.
3. Rerun the original configuration: turboSETI 2.3.2, float32 CPU, max drift
   4 Hz/s, min drift 1e-5 Hz/s, threshold 10, one coarse channel, DC blanking.
   Record every searched trial's pre-threshold maximum and finite fraction,
   the actual normalization and all returned rows/warnings.
4. Independently sum straight, nearest-channel tracks in float64, covering
   integer endpoint offsets corresponding to +/-4 Hz/s. Include zero drift.
   Use 5th/95th percentile trimming and population standard deviation of
   the time-integrated spectrum; median is over all integrated channels.
   Exclude tracks leaving the data, never wrap frequency edges. These paths
   differ from the Taylor tree, so compare the threshold conclusion rather
   than demanding identical SNR values.
5. On separate copies, add three deterministic, one-channel-wide tracks at
   23%, 48%, 73% of the native channel range. Their slopes are -1, +1, +10
   native channels per integration. Add constant power giving a nominal
   integrated contribution of 40 times the original normalization standard
   deviation. Require matches within 3 native frequency channels and 0.03
   Hz/s. Record all failures; do not adjust the controls to obtain a pass.

## Interpretation criteria

- Hash mismatch or invalid power blocks interpreting the rerun as the same data.
- If a later scan contains above-threshold trials but produces no rows, inspect
  selection/writing before treating its empty table as valid.
- If both integrations remain below threshold and positive controls recover,
  conclude only that these scans have no reported lines under this tested setup.
- Failed controls trigger further diagnosis and remain in the research record.
- The logging-format exception is separate from a scientific failure. Confirm
  its traceback location; never suppress arbitrary search failures.

This is one dataset and selected deterministic controls. It is not a randomized
sensitivity/completeness study, an astrophysical flux calibration, independent
external review, or new telescope exposure. Any further adaptation must be
reported as a follow-up, with its reason and separate results.
