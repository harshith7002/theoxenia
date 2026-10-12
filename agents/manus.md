# Operator checklist

## Start

1. Read the current Notion Charter, Architecture, Agent Playbook, Decisions Log, Roadmap/Pipelines, and relevant database rows.
2. Take only a task in **Next** with Owner **Manus**; check blockers and acceptance criteria before implementation. The live board determines task status.
3. Inspect the repository branch and working tree. Keep the branch and PR concern-scoped.

## Implement and run

- Use the current `uv`/Ruff/pytest conventions and typed Pydantic models.
- Prefer a documented `make` target or `xenia` CLI command over ad-hoc result scripts.
- Verify source URLs, exact records/queries, license/access constraints, and claims against primary sources. Scaffold material is not verified evidence.
- Before a result run, define acceptance criteria. Run from a clean code commit so the manifest’s Git SHA identifies the executed code; store only small checksummed summaries/plots, never raw observations or temporary slices.
- Record failures and nulls honestly. Preserve the manifest and reference the matching Notion Experiment row.

## Finish

1. Run the documented tests, lint, schema, and file-policy gates.
2. Open a focused PR and populate its experiment section from the actual manifest.
3. Link the PR and run IDs to the correct Notion records; update the task record only to reflect work actually completed.
4. Stop at any live `Needs Michael` blocker or need for new authority. Do not publish, provision, create credentials/accounts, contact people, submit requests, or spend without Michael’s explicit approval.

See [`../docs/agents.md`](../docs/agents.md) for the shared workflow and authority boundaries.
