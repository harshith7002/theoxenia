# Main-only observatory worker

Use the [operator guide](../docs/mission-control-deploy.md) and [operating model / hosting proposal](../docs/observatory.md).

- `run.sh`: one bounded real-data pass in a dedicated main checkout; push is opt-in with `THEOXENIA_PUSH=1`.
- `theoxenia.service`: non-root, restricted systemd oneshot with a 35-minute limit.
- `theoxenia.timer`: run 15 minutes after the prior pass finishes.

These host files are prepared but are not proof of a provisioned server or a passed 24-hour soak. The public site continues to use GitHub Pages. The old live-branch bootstrap and synthetic pulse are superseded; no root-domain change is required.
