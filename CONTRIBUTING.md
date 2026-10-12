# Contributing

Theoxenia is a hobby-scale, evidence-first research lab. Small, reviewable changes are preferred. The live Notion Charter, Architecture, Decisions Log, and EXP-030 page remain the source of truth for current scope and decisions.

## Development setup

Use CPython 3.15.0 and uv 0.13.0 or later, then run:

```bash
uv python install 3.15.0
uv sync --locked --all-groups --extra radio --extra disclosure --python 3.15.0
make test
make lint
make types
make schemas-check
make files-check
make docs
```

`make types` is `mypy --strict` on `src/xenia`. The disclosure extra installs the OCR dependencies. Raw scans stay in the ignored `data/` directory.

For Mission Control changes, `make live-dev` builds from synthetic fixtures and serves the result locally. The M0 page is not a live worker and does not use telescope observations. A pre-commit hook scans `site/templates/` for the public-page word list. See `docs/hardening.md`.

## Pull requests

Keep PRs concern-scoped. Include focused tests and update generated JSON Schemas whenever a Pydantic model changes. Do not hand-edit the generated schemas; run `make schemas` and include the result.

Any result-producing command must record exact inputs, parameters, outputs, code/version, timestamps, outcome, and notes in `runs/<RUN_ID>/manifest.json`. Link the run ID to its Notion Experiment record. A code-only change that does not produce a research result does not need an artificial experiment run.

Before opening a PR, run `make test`, `make lint`, `make types`, `make schemas-check`, `make files-check`, and `make docs`. Run `make files-check` after `git add`, because it reads the index. A PR that changes experiments should state its acceptance criteria and show the manifest(s) that support the result.

Issues labelled `good first issue` are reproductions of a committed run or a small addition to an existing data source. A new pipeline is out of scope for that label. Use the cadence-claim template when the issue records one search.

## Data and security

Do not commit raw telescope files, scan files, credentials, or files larger than 2 MiB. Put local raw data under the ignored `data/` directory. Demo fixtures must be explicitly synthetic and must not be presented as observations.

Document mundane explanations and verification steps before describing any record as unusual. The worker must not assign `UNEXPLAINED`; that verdict requires all checks and explicit review sign-offs.

## Code style

Use typed, modular Python with focused errors. Pydantic models are the schema source of truth. Ruff, pytest, `uv`, and the checked-in lockfile are the project standards. Stream or slice raw data; do not load full telescope files when a windowed read is possible.
