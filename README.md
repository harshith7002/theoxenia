# Theoxenia

**An evidence-first, reproducible Python lab for public radio technosignature data.**

The repository is named **Theoxenia**; the installable package and CLI use the short name `xenia`.

> **Current status:** Mission Control’s static M0 prototype and the EXP-001 Voyager HDF5 pipeline are implemented. No result is called a detection unless the run manifest records a hit that passes the predeclared known-answer checks. There is no live worker or public deployment yet; the VM-dependent M3 work remains separate.

A hit is a measurement to investigate, not a conclusion. Each result links to its inputs, exact parameters, code revision, outputs, and manifest. Failures and null results are retained as evidence. Raw telescope files and temporary slices do not belong in Git.

## Quick start

The project baseline is **CPython 3.15.0**. Use uv 0.13.0 or later to install that stable interpreter. See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) and [Python 3.15.0 release page](https://www.python.org/downloads/release/python-3150/).

```bash
uv python install 3.15.0
uv sync --all-groups --extra radio --python 3.15.0
make test
make live-dev
```

Open <http://127.0.0.1:8080>. The local M0 page is rendered from synthetic fixtures, works without JavaScript, and displays a persistent demo warning. Stop the server with `Ctrl-C`.

To run the real Voyager positive control, execute:

```bash
make voyager
```

This reads the immutable HTTPS mirror in bounded 64 KiB ranges, slices only the predeclared 8419.24–8419.35 MHz band, and refuses to transfer more than 24 MiB. The detector input and scratch outputs live only in a temporary directory. The run writes a compact manifest, hit summary, slice summary, and waterfall PNG under `runs/<RUN_ID>/`. Review [`docs/data-sources.md`](docs/data-sources.md) before interpreting the upstream sample or its published reference values.

## Useful commands

| Command | Purpose |
|---|---|
| `make install` | Install the project and development tools from `uv.lock`. |
| `make test` | Run pytest with the project coverage gate. |
| `make lint` | Run Ruff checks and formatting validation. |
| `make schemas` | Export Pydantic JSON Schemas. |
| `make schemas-check` | Fail if committed schemas are stale. |
| `make schemas-validate` | Build demo state and validate it against the committed `LiveState` schema. |
| `make files-check` | Reject raw science data and files larger than 2 MiB. |
| `make live-build` | Rebuild `runs/state.json` and `site/` from the synthetic demo manifests. |
| `make live-dev` | Build the demo and serve it locally on port 8080. |
| `make voyager` | Run EXP-001 against the pinned, range-read HDF5 Voyager sample. |
| `make live-evidence` | Build/render Mission Control from the manifests currently under `runs/`. |

`xenia live hero --voyager --help` shows the EXP-001 options. Result-producing commands write a small `runs/<RUN_ID>/manifest.json` with exact inputs, command, parameters, outputs, code SHA, timestamps, outcome, and notes.

## Project data flow

### M0 demo page

```text
tests/fixtures/live/*/manifest.json
              │
              ▼
     Pydantic manifest models
              │
              ▼
      runs/state.json
              │
              ├── Jinja2 template ─────► site/index.html
              ├── server-rendered SVG ──► site/sky.svg and site/floor.svg
              └── manifest index ──────► site/runs/index.html
```

### EXP-001 Voyager positive control

```text
Pinned HTTPS HDF5 mirror
  → fsspec byte-range reader (64 KiB blocks; 24 MiB hard cap)
  → HDF5 metadata validation and whole-channel cutout
  → temporary FILTERBANK file validated by blimpy H5Reader
  → turboSETI known-answer window and SNR/drift checks
  → hit summary + waterfall PNG + complete run manifest
```

The original Breakthrough Listen tutorial `.fil` sample has only two integrations, while turboSETI requires at least four. The project records the failed attempts and uses the separately published, 16-integration HDF5 positive-control sample instead; it does not fabricate integrations or patch upstream validation. The actual HTTPS transport is a third-party mirror pinned to an immutable Git commit, with the official publisher URL recorded separately. See the [source and verification notes](docs/data-sources.md).

`LiveState` in `src/xenia/live/models.py` is the schema source of truth. Its checked-in JSON Schema is `schemas/live_state.schema.json`. Generated page files under `site/` are reproducible outputs, not the source of truth.

## Current boundaries

- M0 fixtures are synthetic and are never represented as telescope observations.
- EXP-001 is a known-transmitter positive control. It is not an unknown candidate or an anomaly claim.
- EXP-002 injection/recovery, the 100-cadence crawler, unattended worker, live hosting, Pages mirror, and M4 sharing polish are later MVP acceptance items.
- The live worker must not be configured or hosted until the approved VM and required access are available. No host, account, or paid service has been provisioned.

## Reproducibility and data handling

- Every result command records checksummed inputs/outputs, exact parameters, code version, timestamps, outcome, and notes in its run manifest.
- HDF5 is read through measured HTTP ranges; there is no fallback to a whole-file download.
- Source and temporary HDF5 slices stay out of the repository. Compact summaries, manifests, and generated plots may be committed as experiment artifacts.
- Pydantic models generate the checked-in schemas; CI rejects stale schema exports.
- Files over 2 MiB and raw telescope-data formats are rejected by the repository file-policy check.
- Secrets and credentials never belong in the repository or Notion.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for Python style, tests, provenance requirements, and data-handling policy. Scientific dependency compatibility and the CPython 3.15 radio extra are documented in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

## License

Code is licensed under Apache-2.0. Project-authored documentation is licensed under CC BY 4.0. Third-party data keeps its original terms; see [`LICENSE-DATA.md`](LICENSE-DATA.md).

## Project sources

The mutable specification, decisions, and task state live in the [Alien Exploration Notion teamspace](https://app.notion.com/p/3ab073ddfc5c83b3ad6801b9c2608d6b). The [Mission Control MVP brief](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac) is the source of truth for milestones and acceptance criteria. M0-specific history is in [`docs/mission-control-m0.md`](docs/mission-control-m0.md).
