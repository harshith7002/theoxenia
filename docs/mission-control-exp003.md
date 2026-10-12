# EXP-003 archive cadence

One Breakthrough Listen ABACAD cadence, sliced to 1 MHz and searched with the same ON/OFF filter as EXP-004. `demo` is false. A passing filter is `ON_ONLY` until a reviewer signs it. This page does not claim a detection.

## Where the files are

The open-data catalog at `http://seti.berkeley.edu/opendata/api/` lists cadence `--63460` as 18 rows: six scans times three products. The fine-resolution product is `*.gpuspec.0000.h5`. In time order the on/off pattern is A, B, A, C, A, D. The on-source target is HIP544. The six HTTPS URLs are under `https://bldata.berkeley.edu/pipeline/AGBT16B_999_13/holding/`.

On 2026-10-12 a `Range: bytes=0-1023` request to the first HIP544 file returned `206 Partial Content`. `Content-Range` was `bytes 0-1023/15489328869`. The server was nginx/1.21.0. `Last-Modified` was Sat, 24 Mar 2018 01:28:35 GMT. The response `Date` was Mon, 12 Oct 2026 20:17:41 GMT. TLS verification was left on.

The same night, a bounded header read of each of the six files transferred 1,048,584 bytes in one range. Each `Content-Length` matched the catalog `size`. Public HTTP remains refused. Decision D-018 was not opened: the science host answered on HTTPS.

## Header, measured

All six headers agreed on these values:

| Field | Value |
|---|---|
| Shape | 16 integrations, 1 IF, 322,961,408 channels |
| Chunks | (1, 1, 1,048,576) |
| `fch1` | 1926.26953125 MHz |
| `foff` | −2.7939677238464355e-6 MHz (−2.7939677238464355 Hz) |
| `tsamp` | 18.253611008 s |
| `nbits` | 32, float32 |
| Band | 1023.9257840439677 MHz to 1926.26953125 MHz |

1380–1381 MHz is inside that band on every file. One chunk is 1,048,576 channels, which is 2.9296875 MHz. Sixteen integrations of one chunk are 67,108,864 uncompressed bytes. A 1 MHz window is 357,913.9413333333 channels and 22,906,492.245333333 uncompressed bytes at 16 integrations. The window fits in one chunk when it does not cross a chunk boundary, and it takes two chunks when it does. The run records the ranges actually transferred. The transfer cap is 268,435,456 bytes per file.

`src_raj` and `src_dej` are dataset attributes. `src_raj` is in hours. Multiplying by 15 matched the catalog `ra` in degrees at the catalog's printed precision, and `src_dej` matched catalog `decl`, for all six files. The pointing uses the first HIP544 catalog position: ra 1.6549208333 deg, decl 29.0205625 deg. That file's `src_raj` was 0.11032805555555557 hours (1.6549208333333336 deg) and `src_dej` was 29.020562500000008 deg.

Header `tstart` values were 57622.38260416667, 57622.38652777778, 57622.390439814815, 57622.39439814815, 57622.39834490741, and 57622.40230324074. Scans 1, 4, and 6 differ from the catalog `mjd` in the last digits. The search uses the header `tstart`.

## What the command does

`make cadence` runs `xenia live cadence` on those six URLs with `--window 1380.0 1381.0` and `--experiment-id EXP-003`. The slicer calls `open_counted_http_file` and `slice_hdf5_filterbank`. Each input SHA-256 is the local slice. `catalog_md5` is stored as the API field. This run does not hash the remote 15 GB objects.

`FindDoppler` uses max drift 4 Hz/s, SNR 10, and one coarse channel. `find_event_pipeline` uses filter threshold 3 and keeps zero-drift hits. Detections are grouped after projecting each scan-start frequency back to the first scan's `tstart`, inside 500 Hz and 0.15 Hz/s. The verdict uses the measured on-scan and off-scan counts. A filter-3 flag does not force `ON_ONLY`.

Outputs under `runs/<RUN_ID>/`:

- `manifest.json` with `mission_control.kind` of `cadence` and `demo` false
- `hits.parquet`, one row per labelled hit, including the five check booleans
- `slice_summary.json`, with the byte ranges and the per-file headers
- an SVG thumbnail for each hit shown on the page
- a six-panel PNG for an `ON_ONLY` hit when the plot call succeeds and the file is under 2 MiB

The page payload is the top three hits by SNR plus any plotted `ON_ONLY` hits. `hits.parquet` holds every labelled row. Verdict counts in the manifest are the parquet sums. Temporary filterbanks under `data/tmp` are deleted after the slice hashes and plots are done. Nothing under `data/` is committed.

## Measured search

The search results are whatever `make cadence` writes. Numbers from that run belong in this section only after the manifest exists. Until then this page does not quote a hit count.
