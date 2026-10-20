"""Build an offline, manifest-backed public snapshot without running experiments."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from xenia.live.models import LiveState
from xenia.live.render import render_site
from xenia.live.state import build_state, load_manifests


def build_public_site(output: Path, *, base_url: str, now: datetime | None = None) -> LiveState:
    root = Path(__file__).resolve().parents[1]
    if output.exists() and any(output.iterdir()):
        raise ValueError("output must be a new or empty directory; preserve existing builds")
    output.mkdir(parents=True, exist_ok=True)
    state = build_state(
        load_manifests(root / "runs"),
        generated_at=now or datetime.now(UTC),
        mirror_url=base_url.rstrip("/") + "/",
    )
    state_path = output / "state.json"
    state_path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    render_site(
        state_path=state_path, runs_dir=root / "runs", output_dir=output, repository_root=root
    )
    (output / "build.json").write_text(
        json.dumps(
            {
                "git_sha": state.git_sha,
                "generated_at": state.generated_at.isoformat(),
                "mode": (
                    "automated-archive-observatory"
                    if (output / "observatory.json").exists()
                    else "recorded-evidence-snapshot"
                ),
                "source_branch": "main",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="https://mpetyx.com/theoxenia/")
    args = parser.parse_args()
    state = build_public_site(args.output, base_url=args.base_url)
    print(
        f"Built {args.output}: {state.totals.cadences_searched} observed cadence(s), "
        f"{state.totals.hits} recorded hits, {state.totals.survivors} survivors. No deployment."
    )


if __name__ == "__main__":
    main()
