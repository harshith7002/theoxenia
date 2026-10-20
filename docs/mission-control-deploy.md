# Observatory operator guide

The [automated archive observatory](observatory.md) runs on main. Historical live-branch and synthetic-pulse deployment instructions are superseded. Do not create `live` or use the legacy `GitPublisher` / `xenia live run` path for production.

## Current hosted service preparation

Use a dedicated checkout at `/opt/theoxenia`, owned by a non-root `theoxenia` user. Install Git, build-essential, libhdf5-dev and pkg-config, plus the pinned uv version in `/usr/local/bin`. Install CPython 3.15.0 with uv and the committed lockfile. Allow at least 8 GB RAM and 80 GB disk until measurements support reducing them. No inbound web port is required; SSH access can be restricted to the operator.

Install the supplied service and timer into `/etc/systemd/system/`. Create the service account with `/var/lib/theoxenia` as its home directory, owned by that user. Configure the Git identity and repository-only authentication through the service user's credential store (outside the checkout). `ProtectHome=true` means this store must be accessible under `/var/lib/theoxenia`, not a home directory. An SSH deployment needs its key and known-host file there too; verify GitHub's host key rather than disabling checks.

The owner-readable `/etc/theoxenia/worker.env` contains only operational settings:

```ini
THEOXENIA_PUSH=1
```

The unit routes uv/Python caches and Matplotlib configuration to `/var/lib/theoxenia`. Its `Type=oneshot` runs one real window per invocation and has a 35-minute timeout. The timer starts two minutes after boot, then 15 minutes after each completed invocation. systemd prevents overlapping invocations of the same unit; the worker also holds an OS-level file lock. Git pull is fast-forward only. All source must be committed before processing.

## Handover from GitHub processing

Do not run two independent schedulers against the same main branch. First set repository variable `THEOXENIA_WORKER_MODE=hosted`, wait for any active Observatory job to finish, and pull main onto the server. Then start one supervised host cycle and verify its evidence push and automatic Pages deployment before enabling the timer. Switching back means stopping the timer first and restoring the variable to `scheduled`.

The Pages `push` trigger publishes host-generated evidence. The Actions worker instead calls Pages directly because its built-in token cannot trigger a second push workflow. Never grant the worker access to the root `mpetyx.github.io` repository.

## Recovery and acceptance

A timeout or crash leaves completed manifests intact; restart reconstructs completed windows from their checked artifacts. A rejected push leaves a local commit. Stop the timer, inspect divergence and recover the evidence onto current main without rewriting the science revision. Never reset away an unpublished evidence commit.

Inspect `systemctl status theoxenia.service`, `journalctl -u theoxenia.service`, the newest cycle receipt and public processing history. The site is a static publication, so HTTP 200 is not worker liveness. An old receipt is visible as stale. An alerting service and a measured 24-hour soak remain follow-up work until the host exists.

Before calling the service accepted, measure peak memory, runtime, bytes and disk growth; test process termination and restart; reproduce one result from a second checkout; and record the 24-hour run with at least 50 genuinely processed pairs. More measured queue inputs are required before that acceptance is possible. Seven remaining windows in the initial cadence are not 50 pairs.
