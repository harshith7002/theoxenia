# Architecture

The project uses a prosaic-first, evidence-backed pipeline. A plotted value is derived from validated experiment/run records; it is not hand-entered in the dashboard. The live [Mission Control MVP brief](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac) and the [live Architecture page](https://app.notion.com/p/3f6073dd-fc5c-818f-a25a-dc1e1dc330f7) are the mutable sources of truth.

## Current data flow

```text
synthetic demo fixtures ─┐
                         ├── Pydantic RunManifest ──► LiveState ──► static HTML/SVG
EXP-001 run artifacts ───┤
EXP-002 grid artifact ────┘
```

- `src/xenia/live/models.py` defines strict run, page-state, and experiment artifact contracts.
- `src/xenia/radio/remote.py`, `hdf5.py`, `detector.py`, and `voyager.py` implement bounded, provenance-recorded EXP-001 reads and the known-answer detector run.
- `src/xenia/radio/floor.py` and `floor_config.py` implement the deterministic EXP-002 setigen grid and turboSETI matching.
- `src/xenia/live/state.py` derives dashboard state from run manifests; `render.py` writes static HTML and SVGs from local assets.
- `src/xenia/provenance.py` creates compact run manifests; `src/xenia/schemas.py` exports schemas from the Pydantic source models.

Every result-producing command records exact parameters, code SHA, runtime versions, timestamps, outcomes, notes, and output references in `runs/<RUN_ID>/manifest.json`. Result runs are linked to their Notion Experiment records. Raw telescope data and temporary slices remain outside Git.

## Milestone boundary

| Scope | Status in this repository |
|---|---|
| M0, static fixture-backed page and schema | Implemented; see [M0 notes](mission-control-m0.md). |
| EXP-001, Voyager positive control | Implemented and run; the measured values and source caveats are in [data sources](data-sources.md). |
| EXP-002, synthetic injection/recovery | Runner, schema, tests, and PR/nightly CI path are implemented; completion requires the full grid run, committed manifest/artifact, and Notion Experiment linkage. See [method](mission-control-exp002.md). |
| M3, persistent worker, restart/egress and VM validation | Deferred until Michael attaches the VM and approves the exact setup. No host is selected or provisioned. |
| Static docs/catalogue publication | MkDocs is build-only in this repository. GitHub Pages publication is not enabled. |
| Disclosure, fusion, and exoplanet pipelines | Not part of the current EXP-030 vertical slice; implement only against an actionable Notion task and verified primary sources. |

## Deliberately deferred scaffold components

The supplied initial scaffold also contained candidate/incident models, a candidate catalogue, generic source probes, disclosure OCR, fusion scoring, an unbounded cadence prototype, and workflows that fetched external records or deployed documentation. Their presence in the archive is not evidence that their contracts or endpoints are accepted. See [the scaffold integration review](scaffold-integration.md) for why they are not copied into the current runtime.

## Static documentation and hosting

MkDocs Material builds to a temporary local directory for validation. This is separate from the generated Mission Control preview under `site/`. No documentation workflow calls `gh-deploy`, enables Pages, creates credentials, or publishes externally. Hosting decisions continue to follow the live Notion decisions and approval boundaries.
