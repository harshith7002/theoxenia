# Theoxenia

Theoxenia is an evidence-first, reproducible Python lab for public radio technosignature data. The current implementation is the Mission Control MVP’s Sensor vertical slice: a static, manifest-derived dashboard, a Voyager known-answer pipeline, and a setigen injection/recovery calibration.

## Start here

- [Repository README](https://github.com/mpetyx/theoxenia) — setup and supported commands
- [Automated observatory](observatory.md) — scheduled real-data processing, recovery and hosting
- [Architecture](architecture.md) — implemented boundaries and deferred work
- [EXP-001 data-source verification](data-sources.md) — Voyager source, mirror, and run evidence
- [EXP-002 method](mission-control-exp002.md) — synthetic calibration grid and limitations
- [Dependency compatibility](DEPENDENCIES.md) — tested CPython 3.15 stack
- [Mission Control M0 history](mission-control-m0.md)
- [Scaffold archive review](scaffold-integration.md)

The mutable task state, decisions, and experiment records live in the [Alien Exploration Notion teamspace](https://app.notion.com/p/3ab073ddfc5c83b3ad6801b9c2608d6b), not in a copied static status table. See the [Mission Control MVP brief](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac) for current acceptance criteria.

## Current boundary

The site and report are public. A bounded real-data worker now supports scheduled archive processing and automatic publication from `main`, with original observations separated from synthetic controls. The dedicated host and original 24-hour/50-pair acceptance remain open. See [the observatory](observatory.md) for current operation and [first public release](public-release.md) for its historical launch record.

The Pages workflow builds Mission Control at the site root and these docs under `/docs/`. It accepts manual dispatch, calls from the Observatory workflow, and main-branch evidence pushes.
