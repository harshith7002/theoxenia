#!/usr/bin/env bash
# One supervised cycle in a dedicated main checkout. No branch creation or server.
set -euo pipefail
if [ "$(git branch --show-current)" != main ]; then
  echo 'deploy: requires a dedicated main checkout' >&2
  exit 1
fi
if [ "${THEOXENIA_DEPLOY_STOP:-}" = before-sync ]; then
  echo 'deploy: main only; not creating any branch; stopping before sync' >&2
  exit 0
fi
# A rejected previous push leaves a recoverable commit; never reset it away.
git pull --ff-only origin main
uv sync --locked --all-groups --extra radio --python 3.15.0
args=(--hosted --max-pairs 1)
if [ "${THEOXENIA_PUSH:-0}" = 1 ]; then args+=(--publish); fi
uv run --locked python scripts/observatory.py "${args[@]}"
