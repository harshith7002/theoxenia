# Deploy

`deploy/run.sh` serves the page and runs the worker. It does not create the `live` branch, and it does not push unless `THEOXENIA_PUSH` is `1`.

## Environment

| Name | Meaning |
| --- | --- |
| `THEOXENIA_PUSH` | `1` pushes. The script sets this to `0` when it is unset. |
| `THEOXENIA_HOST` | Host string stored on the worker heartbeat. |
| `THEOXENIA_PORT` | Page and `/healthz` port. Default `8080`. |
| `THEOXENIA_BIND` | Bind address. Default `0.0.0.0`. |
| `THEOXENIA_DEPLOY_STOP` | Test hook. `before-sync` exits after the branch check. Leave it unset on a host. |

## `/healthz`

`GET /healthz` returns 200 when the state is not a demo, the worker status is `running`, and the heartbeat age is from 0 through 600 seconds. Any other state returns 503. The HTML page stays available in both cases.

The worker rewrites `site/state.json` on every heartbeat, including while it is idle.

## Branch check

1. If `app/` exists, fast-forward it from `origin/live`.
2. If this directory is a checkout and neither `live` nor `origin/live` exists, stay here and log that the branch is not being created.
3. Otherwise clone `https://github.com/mpetyx/theoxenia.git` at branch `live` into `app/`.

The one-time `git push origin main:live` is not this script. It happens after the stacked pull requests are merged.

## Supervisor

Restart the script when the process exits, or when `/healthz` is 503.

```
[Service]
WorkingDirectory=/opt/theoxenia
ExecStart=/bin/bash /opt/theoxenia/deploy/run.sh
Restart=on-failure
Environment=THEOXENIA_PUSH=0
Environment=THEOXENIA_HOST=manus-1
Environment=THEOXENIA_PORT=8080
```

A Manus persistent task uses that same command and the same restart rule.

With no host attached, leave the schedule in `.github/workflows/live-pulse.yml` commented out. That workflow is decision D-017, status Proposed. A manual run does not search when `THEOXENIA_LIVE_URL` is unset, when that URL's `/healthz` returns 200, when `THEOXENIA_PULSE` is not `1`, or when `origin/live` is missing. When all of those pass, it runs one synthetic `--once` pass and does not push. The token is `contents: read`.

## Recovery

```bash
python scripts/recovery_check.py /path/a/index.html /path/b/index.html
```

Exit 0 prints `recovery-check: match`. The comparison ignores the heartbeat label, the ticker sentence, and the "State built" clock. Verdicts and manifest links still have to match.

`make recovery-check` runs the tests for this script.

## Tomorrow

Run this from the GitHub account that can merge. Do not push `main` before these merges. Do not create `live` before the `git push` line below. If a merge stops on `Makefile`, `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock`, `mkdocs.yml`, `src/xenia/cli.py`, or `src/xenia/schemas.py`, keep both sides' additions. Pull requests 16 and 17 both add Hypothesis; keep one dev pin, and keep the `mypy` configuration from pull request 16.

```
gh pr merge 4 --repo mpetyx/theoxenia --merge
gh pr merge 5 --repo mpetyx/theoxenia --merge
gh pr merge 6 --repo mpetyx/theoxenia --merge
gh pr edit 7 --repo mpetyx/theoxenia --base main
gh pr merge 7 --repo mpetyx/theoxenia --merge
gh pr edit 8 --repo mpetyx/theoxenia --base main
gh pr merge 8 --repo mpetyx/theoxenia --merge
gh pr edit 9 --repo mpetyx/theoxenia --base main
gh pr merge 9 --repo mpetyx/theoxenia --merge
gh pr edit 10 --repo mpetyx/theoxenia --base main
gh pr merge 10 --repo mpetyx/theoxenia --merge
gh pr edit 11 --repo mpetyx/theoxenia --base main
gh pr merge 11 --repo mpetyx/theoxenia --merge
gh pr edit 12 --repo mpetyx/theoxenia --base main
gh pr merge 12 --repo mpetyx/theoxenia --merge
gh pr edit 17 --repo mpetyx/theoxenia --base main
gh pr merge 17 --repo mpetyx/theoxenia --merge
gh pr merge 13 --repo mpetyx/theoxenia --merge
gh pr merge 14 --repo mpetyx/theoxenia --merge
gh pr merge 15 --repo mpetyx/theoxenia --merge
gh pr edit 16 --repo mpetyx/theoxenia --base main
gh pr merge 16 --repo mpetyx/theoxenia --merge
gh pr edit 23 --repo mpetyx/theoxenia --base main
gh pr merge 23 --repo mpetyx/theoxenia --merge
```

```
git push origin main:live
```

Michael enables GitHub Pages with source GitHub Actions. Then:

```
gh workflow run pages.yml --repo mpetyx/theoxenia --ref main
```

On the host secret store, set `GITHUB_TOKEN` and `THEOXENIA_HOST`. Do not commit either value. Then start the worker and leave `/usr/bin/time` outside any process group you kill:

```
cd /opt/theoxenia
THEOXENIA_PUSH=0 THEOXENIA_PORT=8080 THEOXENIA_BIND=0.0.0.0 /usr/bin/time -l -o soak-time.txt bash deploy/run.sh
```

On the host, while that process is up, save the page and sample health:

```
curl -fsS http://127.0.0.1:8080/index.html -o /tmp/host-index.html
curl -sS -D - http://127.0.0.1:8080/healthz >> /opt/theoxenia/soak-healthz.log
```

Repeat the health line through the soak. The log is the record.

On a second fresh box, after `/tmp/host-index.html` has been copied there and `origin/live` exists:

```
git clone --branch live --single-branch https://github.com/mpetyx/theoxenia.git /tmp/theoxenia-recovery
cd /tmp/theoxenia-recovery
uv python install 3.15.0
uv sync --locked --all-groups --extra radio --extra disclosure --python 3.15.0
uv run --locked xenia live build-state --runs runs --output runs/state.json --manifest-root runs --experiment-id EXP-030
uv run --locked xenia live render --state runs/state.json --runs runs --output site --manifest-root runs --experiment-id EXP-030
uv run --locked python scripts/recovery_check.py site/index.html /tmp/host-index.html
```

At 24 hours, record only what these print. Do not convert bytes into a cost.

```
date -u
du -sk runs data site
cat soak-time.txt
```

Write spec section 16 with the live page URL that served `/healthz`, the mirror URL printed by the Pages run, `https://github.com/mpetyx/theoxenia/tree/live`, and the Experiment row links for EXP-001, EXP-002, EXP-003, and EXP-030. URL stability, persistence, restart behaviour, and egress stay empty until a command has measured them. Egress is the sum of input `size_bytes` on cadence manifests written during the soak.
