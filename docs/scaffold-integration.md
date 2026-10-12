# Initial scaffold archive review

**Archive:** `theoxenia-scaffold.zip`, supplied by Michael on 2026-10-12. **SHA-256:** `8507fe0df16bb78f391fa77e4c3616765219ab5bbf5aeb7adf1f1cf6582d8740`. The archive contained 74 ZIP members (including directories) and 101,135 bytes of file content. It was extracted to a temporary review directory and was not copied into the repository as a ZIP.

## Adopted and reconciled

- The original evidence-first, multi-pillar project intent is retained in the current README and architecture, but mutable status and scope come from live Notion.
- The useful open-source collaboration pattern is adapted in `.github/PULL_REQUEST_TEMPLATE.md`, the two issue templates, `CODE_OF_CONDUCT.md`, `docs/agents.md`, and `agents/`.
- Static MkDocs Material documentation is configured for a build-only validation. The supplied deployment workflow is **not** used; no GitHub Pages publication is configured.
- The archive’s single Voyager and single-injection examples are superseded by the tested, bounded EXP-001 pipeline and schema-backed EXP-002 grid described in [data-source verification](data-sources.md) and the [EXP-002 method](mission-control-exp002.md).

## Deferred or not copied into the runtime

| Archive content | Decision and reason |
|---|---|
| `pyproject.toml`, README, `Makefile`, CI, and CLI | Conflicted with the live Python 3.15 baseline, current `uv` lock, tested command surface, schema checks, and run-manifest requirements. The repository’s current versions remain authoritative. |
| `src/xenia/radio/hello.py` | Its default source is HTTP and its download path streams the entire sample to persistent `data/samples`; this conflicts with current HTTPS range reads, transfer limits, and temporary-slice policy. EXP-001 already has a verified implementation. |
| `radio/inject.py` and `tests/test_inject_recover.py` | The example runs a single un-smoothed signal, monkey-patches turboSETI, keeps temporary filterbanks under the run directory, and does not implement the required full grid/typed artifact. EXP-002 is implemented separately; preliminary runs also led to a drift-integration regression test. |
| `radio/cadence.py` | Its S3 provider and records are not independently verified; its remote HDF5 handling can materialize selected arrays and lacks the current byte cap/provenance contract. Revisit only for an actionable cadence/worker task. |
| `configs/sources.yaml` and `src/xenia/sources.py` | Several entries are unverified, the Voyager URL is HTTP, and a reachability response alone would not verify the scientific endpoint or query. The live Notion Data Sources database and per-experiment source evidence take precedence. |
| `catalog/candidates.json`, root candidate/incident models, generated schemas, and `catalog.py` | Candidate facts and source names are not linked to exact records/URLs, and mutable candidate state belongs to Notion. These files are not suitable as a public catalogue until records are checked against the live database and primary sources. |
| `fusion/score.py` and `tests/test_score.py` | The score weights and probability composition are an unvalidated heuristic with only toy tests. Do not use or publish a confidence score until a live decision/task and calibration evidence exist. |
| `fusion/baseline.py`, disclosure OCR/extraction, and unrelated workflows | These belong to future pillars, include unverified query/access assumptions, and are outside the current actionable EXP-030 scope. They also need their own schemas, tests, exact source verification, and manifests. |
| `docs.yml` and `nightly.yml` | `docs.yml` ran `mkdocs gh-deploy` with write permission; `nightly.yml` fetched public data without the current manifest/source-verification contract. Neither is installed or enabled. |
| old agent role files for Claude/Grok | Their static permission and automatic Notion-write assumptions were not carried over. Live Notion permissions and the current owner/status workflow govern any executor. |

The archive is useful historical context, not an accepted source of truth for mutable data, current endpoints, runtime baseline, or task status. This review deliberately preserves compatible community practices while avoiding silent import of unverified records or unsafe download/deployment behavior.
