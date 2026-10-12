# Theoxenia

**An evidence-first, reproducible Python lab for public radio technosignature data.**

The repository is named **Theoxenia**; the installable Python package and command-line tool use the short name `xenia`.

> **Current milestone: M0 demo page.** Mission Control is a local, static skeleton built from synthetic fixtures. It is not a live worker, contains no telescope observations, and its demo values must not be interpreted as findings.

The project starts with public scientific data, explicit provenance, known-answer tests, and mundane explanations. A hit is a measurement to check, not a conclusion. Raw telescope files are streamed or sliced when real searches begin; they do not belong in Git.

## Quick start

The project baseline is **CPython 3.15.0**. Use uv 0.13.0 or later so it can install that stable interpreter; see the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) and [Python 3.15.0 release page](https://www.python.org/downloads/release/python-3150/).

```bash
uv python install 3.15.0
uv sync --all-groups --python 3.15.0
make test
make live-dev
```

Open <http://127.0.0.1:8080>. The page is rendered from the demo manifests, works without JavaScript, and displays a persistent demo warning. Stop the server with `Ctrl-C`.

## Useful commands

| Command | Purpose |
|---|---|
| `make install` | Install the project and development tools from `uv.lock`. |
| `make test` | Run the focused pytest suite. |
| `make lint` | Run Ruff checks and formatting validation. |
| `make schemas` | Export Pydantic JSON Schemas. |
| `make schemas-check` | Fail if committed schemas are stale. |
| `make schemas-validate` | Build demo state and validate it against the committed `LiveState` schema. |
| `make files-check` | Reject raw science data and files larger than 2 MiB. |
| `make live-build` | Rebuild `runs/state.json` and `site/` from demo manifests. |
| `make live-dev` | Build the demo and serve it locally on port 8080. |

`xenia live build-state --help` and `xenia live render --help` show the underlying options. Result-producing commands write a small, provenance-rich `runs/<RUN_ID>/manifest.json`.

## M0 architecture

```text
tests/fixtures/live/*/manifest.json
              │
              ▼
     Pydantic manifest models
              │
              ▼
      runs/state.json
              │
              ├── Jinja2 template ──► site/index.html
              ├── server-rendered SVG ─► site/sky.svg and site/floor.svg
              └── manifest index ─────► site/runs/index.html
```

`LiveState` in `src/xenia/live/models.py` is the schema source of truth. Its checked-in JSON Schema is `schemas/live_state.schema.json`. Rendered page files under `site/` are generated and intentionally not committed; the fixtures and their manifests are committed so contributors can reproduce the page.

M0 deliberately stops at the demo skeleton. The Voyager known-answer run, injection/recovery grid, real-data crawler, Manus hosting, and GitHub Pages mirror are later milestones. Do not infer that a live URL or those results exist yet.

## Reproducibility and data handling

- Every rendered item links to a relative run manifest; the generated manifest records exact inputs, command parameters, outputs, code version, timestamps, outcome, and notes.
- Demo fixtures are synthetic and clearly labeled. No telescope or scan data is included.
- Schemas are generated from Pydantic models and checked in CI.
- Files above 2 MiB and raw telescope-data formats are rejected by the staged-file check.
- Secrets and credentials never belong in the repository.

## License

Code is licensed under Apache-2.0. The page and project-authored documentation are licensed under CC BY 4.0. Third-party data keeps its original terms; see [`LICENSE-DATA.md`](LICENSE-DATA.md).

## Project sources

The mutable project specification, decisions, and task state live in the [Alien Exploration Notion teamspace](https://app.notion.com/p/3ab073ddfc5c83b3ad6801b9c2608d6b). The Mission Control design and acceptance criteria are recorded in [EXP-030](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac). The M0 implementation boundary and copy decisions are in [`docs/mission-control-m0.md`](docs/mission-control-m0.md).
