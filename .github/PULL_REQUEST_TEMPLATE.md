## What changed and why

<!-- One focused paragraph. Link related Notion task/decision records. -->

## Experiment evidence (when applicable)

- Acceptance criteria defined before the run:
- Run ID / manifest: `runs/<RUN_ID>/manifest.json`
- Exact source record(s), query, or synthetic input:
- Method and parameters:
- Outcome (including nulls/failures):
- Notion Experiment record:

## Validation

- [ ] `make test`
- [ ] `make lint`
- [ ] `make schemas-check`
- [ ] `make files-check`
- [ ] `make docs` (when documentation or navigation changes)

## Review checklist

- [ ] Every important factual claim/number has a primary source or run link.
- [ ] The PR is concern-scoped and reproduces from a documented `make`/CLI command.
- [ ] Failures and null results are preserved; no anomaly language is unsupported.
- [ ] No raw scientific data, large outputs, credentials, or secrets are committed.
- [ ] Any hosting, publication, account, spending, or access change has the required explicit approval.
