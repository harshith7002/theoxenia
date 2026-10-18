> **Historical deployment notes.** Superseded for the 2026-10-18 first release by the [main-only snapshot build](public-release.md). Do not execute the branch-creation or merge commands below. The live worker remains unaccepted.

# Mission Control deploy

`deploy/run.sh` is the process a supervisor keeps alive. The operator contract, environment variables, and the `/healthz` rule are in `deploy/README.md`.

The script fast-forwards an existing `app/` checkout from `origin/live`, or clones that branch when it already exists. When this checkout has no `live` branch, it stays in place and does not create one. `THEOXENIA_PUSH` defaults to `0`.

`/healthz` returns 200 only for a non-demo worker whose status is `running` and whose heartbeat is at most 600 seconds old. The worker rebuilds `site/state.json` on every heartbeat so an idle wait of fifteen minutes does not by itself turn the check to 503.

`scripts/recovery_check.py` compares two rendered `index.html` files. It normalises the heartbeat label, the ticker sentence, and the "State built" clock. `make recovery-check` runs its tests.

The command sequence for the host, the `live` branch, Pages, the recovery box, and the 24-hour soak is in `deploy/README.md` under "Tomorrow".

`.github/workflows/pages.yml` publishes MkDocs from `main` and, once `origin/live` exists, rebuilds the Mission Control page from that branch's manifests into `/live/` with `meta.is_mirror` set. It does not create `live`. The mirror URL recorded in the workflow is the default project Pages URL `https://mpetyx.github.io/theoxenia/`. Pages is not enabled in the repository settings yet, and that URL was not fetched.

`.github/workflows/live-pulse.yml` is the D-017 proposal. Its schedule is commented out. A run searches only when `THEOXENIA_PULSE` is `1`, `THEOXENIA_LIVE_URL` is set, that URL's `/healthz` is not 200, and `origin/live` already exists. The workflow token is `contents: read`, so the pass cannot push.
