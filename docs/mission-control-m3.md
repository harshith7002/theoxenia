# Mission Control queue

`configs/live.yaml` follows spec section 8.5. Two fields are added: `transfer_cap_bytes` (268435456, applied per file) and `allow_plain_http` (false). Public HTTP filterbank reads stay refused.

`measured_file_bands` records the cadence `--63460` header read of 2026-10-12. Each of the six fine files transferred 1048584 bytes for that read. The band was 1023.9257840439677 MHz to 1926.26953125 MHz. A queue window is emitted only when one of these measured bands contains it. A catalog centre frequency is not treated as a band.

## Commands

```bash
make queue
make queue-synthetic
```

`make queue` reads `tests/fixtures/opendata_cadence_63460.json` and writes `configs/queue.jsonl`. The first line is a header with that fixture path and the SHA-256 of the bytes that were parsed. Later lines are pairs, breadth-first: window 1 of every queued cadence, then window 2. `priority` is the window index.

On 2026-10-12 a refetch of `http://seti.berkeley.edu/opendata/api/get-cadence/63460` returned HTTP 500 and 20299 bytes. The body was an HTML Werkzeug page whose title reports `IndexError: list index out of range`. That response was not parsed. The same night, `http://seti.berkeley.edu/opendata/api/query-files?target=HIP544&cadence=1&telescopes=GBT&file-types=HDF5&limit=20` returned HTTP 200 and 53394 bytes, `result` success, 84 rows, 11 cadence ids. Cadence `63460` in that body had 3 fine files, all target HIP544, so it is not an ABACAD set and it was not queued. The committed queue uses the saved 18-row body instead. That file is 10904 bytes, SHA-256 `6ced767dca047281471bbec1190791b08d4fa4279b6fd1075375655b023dc3b7`, and it matches the earlier catalog save byte for byte. It has no `cadence_url`, so the builder is given cadence id `63460`. The written header records `cadences_in_listing` 1, `cadences_queued` 1, and `windows_skipped_outside_measured_band` 0. Eight L-band pairs were written, priority 0 through 7, windows starting at 1380, 1420, 1500, 1600, 1700, 1100, 1200, and 1300 MHz.

`make queue-synthetic` writes `configs/queue.synthetic.jsonl`. Every line has `synthetic: true`. The window is the generated EXP-004 band, computed from the generator constants. That file is the local worker exercise. It is not a Breakthrough Listen listing.

Cadences present in a listing but absent from `measured_file_bands` are counted in the header and not queued.

## Worker

`make live-once` and `make live-forever` run `xenia live run` on `configs/queue.synthetic.jsonl` with `THEOXENIA_PUSH=0`. The loop writes `runs/worker-<host>/manifest.json` (`kind` `worker`, `demo` false) and deletes `data/tmp` after every pair. A pair that raises is tried twice more, then marked failed. The configured commit branch is `live`. If that branch does not exist, the loop records a warning and does not create it. It never commits to `main`. A push happens only when `THEOXENIA_PUSH` is `1`. Idle waits are split into heartbeat-sized sleeps so the heartbeat age stays under ten minutes.
