# Mission Control M0 implementation notes

**Source of truth:** [EXP-030 Mission Control MVP](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac), checked 2026-10-12. M0 is a demo skeleton; this note does not replace the Notion specification.

## Scope and data flow

M0 reads only `tests/fixtures/live/*/manifest.json`, validates every record through Pydantic, aggregates `LiveState`, writes a checksummed result manifest, and renders a static page plus SVG panels. Each visible pointing, hit, and future hero/floor record links back to a run manifest. The page is readable with JavaScript disabled and makes no remote asset requests.

The fixtures and thumbnails are synthetic layout tests. They are not observations, real target names, or scientific results. No raw telescope file is downloaded or stored. The worker snapshot is explicitly paused, and the banner states that the page is M0-only.

## Copy and scientific wording

The proposed gallery heading in the Notion mockup contains a term that the same specification bans from the public page. M0 uses **“Latest hits, and the checks applied.”** instead. Verdict labels retain the specified exact taxonomy. No page copy describes the fixture records as findings.

## Deferred items

This implementation does not deploy to Manus, create a `live` branch, publish a public page, set up GitHub Pages, start a persistent worker, or use real radio data. Those require the remaining EXP-030 milestones, host/persistence/egress verification, and any explicit approval called for by the project decisions. M0 code and tests are prepared for a later setup on the VM Michael plans to add.

## Coordinate-map source

The sky-map band is drawn from the J2000 north Galactic pole used by [Astropy's Galactic frame](https://github.com/astropy/astropy/blob/main/astropy/coordinates/builtin_frames/galactic.py), which cites the IAU Galactic-coordinate definition. It is a projection guide only; M0 pointings are synthetic.

## Validation snapshot

Validated on 2026-10-12 with CPython 3.15.0 and uv 0.13.0. The locked dependency sync succeeded, including Pydantic 2.14.1 and JSON Schema validation. Ruff lint and formatting checks passed; the suite passed **45 tests** with **83.63% coverage**. The generated `LiveState` schema was fresh, and the demo `runs/state.json` validated against it. `make live-build` rendered the static page and its local assets from the synthetic fixtures.
