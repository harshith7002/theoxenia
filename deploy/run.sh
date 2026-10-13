#!/usr/bin/env bash
# Host-agnostic Mission Control process. Does not create the live branch.
set -euo pipefail

log() { printf 'deploy: %s\n' "$*" >&2; }

if [ -d app ]; then
  log "updating app from origin/live"
  git -C app pull --ff-only origin live
  cd app
elif git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  && ! git rev-parse --verify --quiet refs/heads/live >/dev/null \
  && ! git rev-parse --verify --quiet refs/remotes/origin/live >/dev/null; then
  log "branch live does not exist; staying in $(pwd) and not creating it"
else
  log "cloning origin/live into app"
  git clone --branch live https://github.com/mpetyx/theoxenia.git app
  cd app
fi

if [ "${THEOXENIA_DEPLOY_STOP:-}" = "before-sync" ]; then
  log "stopping before sync"
  exit 0
fi

export THEOXENIA_PUSH="${THEOXENIA_PUSH:-0}"
PORT="${THEOXENIA_PORT:-8080}"
BIND="${THEOXENIA_BIND:-0.0.0.0}"

uv sync --frozen --all-groups --extra radio --python 3.15.0
uv run --locked xenia live build-state \
  --runs runs \
  --output runs/state.json \
  --manifest-root runs \
  --experiment-id EXP-030
uv run --locked xenia live render \
  --state runs/state.json \
  --runs runs \
  --output site \
  --manifest-root runs \
  --experiment-id EXP-030

uv run --locked xenia live serve --directory site --host "$BIND" --port "$PORT" &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
sleep 1
if ! kill -0 "$server_pid" 2>/dev/null; then
  log "server exited during startup"
  exit 1
fi

uv run --locked xenia live run --forever
