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
