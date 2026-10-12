# Theoxenia

Theoxenia is an evidence-first, reproducible Python lab for public radio technosignature data. The current implementation is the Mission Control MVP’s Sensor vertical slice: a static, manifest-derived dashboard, a Voyager known-answer pipeline, and a setigen injection/recovery calibration.

## Start here

- [Repository README](https://github.com/mpetyx/theoxenia) — setup and supported commands
- [Architecture](architecture.md) — implemented boundaries and deferred work
- [EXP-001 data-source verification](data-sources.md) — Voyager source, mirror, and run evidence
- [EXP-002 method](mission-control-exp002.md) — synthetic calibration grid and limitations
- [Dependency compatibility](DEPENDENCIES.md) — tested CPython 3.15 stack
- [Mission Control M0 history](mission-control-m0.md)
- [Scaffold archive review](scaffold-integration.md)

The mutable task state, decisions, and experiment records live in the [Alien Exploration Notion teamspace](https://app.notion.com/p/3ab073ddfc5c83b3ad6801b9c2608d6b), not in a copied static status table. See the [Mission Control MVP brief](https://app.notion.com/p/Mission-Control-MVP-EXP-030-3f7073ddfc5c811ca260d7b2a306eaac) for current acceptance criteria.

## Current boundary

The public repository contains no deployed worker or live dashboard. The `site/` Mission Control preview is static and built locally or in CI. M3 worker, VM setup, public Pages publication, cadence crawling, and other pillars remain deferred until their Notion tasks, required access, and approvals permit them.

This documentation is built statically with MkDocs Material. Its build workflow validates content only; it does not deploy or publish GitHub Pages.
