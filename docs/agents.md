# Agent and contributor workflow

Notion is the source of truth for mutable tasks, decisions, experiment records, and source verification. These repository notes are an orientation, not a replacement for the live [Agent Playbook](https://app.notion.com/p/3f6073dd-fc5c-8106-a727-cdd9343ebd07), Charter, Architecture, Decisions Log, Roadmap/Pipelines, or database rows.

## Before taking work

1. Read the relevant current Notion pages and task/database records; do not rely on stale copied statuses.
2. Take only a task whose status is **Next** and whose Owner matches the executor. Follow any prerequisite or `Needs Michael` blocker as written.
3. Agree on acceptance criteria before a result-producing run. Prefer a narrow task and a small branch/PR.

## While working

- Use documented `make` targets and the installed `xenia` CLI for reproducible work.
- Verify source claims against primary sources and record exact URLs, queries/record IDs, and checksums where applicable. Treat scaffold values, copied notes, and model-generated values as unverified until checked.
- Keep mundane explanations and null results visible. Do not call a case anomalous or unexplained without the required checks and human review.
- Commit no secrets, raw telescope/scan data, or outputs above the repository’s size policy. Keep notebooks paired with script equivalents.
- Every result-producing run needs `runs/<RUN_ID>/manifest.json`, exact code/version/parameters/timestamps/outcome, small referenced outputs, and a matching Notion Experiment record.

## Finish and authority

Link the PR and run evidence to the actual Notion records, and update task status only to reflect completed work and the live workflow. Do not publish externally, provision hosts, create credentials/accounts, contact people, submit requests, or spend without Michael’s explicit approval. A GitHub branch or documentation build is not a public deployment.

For the project-specific operator checklist, see the repository’s [`agents/README.md`](https://github.com/mpetyx/theoxenia/blob/main/agents/README.md) and [`agents/manus.md`](https://github.com/mpetyx/theoxenia/blob/main/agents/manus.md).
