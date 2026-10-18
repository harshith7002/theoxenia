"""Build a verified, deterministic Zenodo upload package without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from xenia.live.models import RunManifest
from xenia.live.state import sha256_file


def write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, content)


def verified_evidence(root: Path, run_ids: list[str]) -> dict[str, bytes]:
    files = {}
    for run_id in run_ids:
        manifest_path = root / "runs" / run_id / "manifest.json"
        if not manifest_path.resolve().is_relative_to((root / "runs").resolve()):
            raise ValueError("run outside repository")
        manifest = RunManifest.model_validate_json(manifest_path.read_text())
        if manifest.run_id != run_id:
            raise ValueError("run identity mismatch")
        files[f"runs/{run_id}/manifest.json"] = manifest_path.read_bytes()
        for artifact in manifest.outputs:
            if artifact.path == f"runs/{run_id}/manifest.json":
                continue
            path = root / artifact.path
            if not path.resolve().is_relative_to(manifest_path.parent.resolve()):
                raise ValueError("artifact outside run")
            if not artifact.sha256 or sha256_file(path) != artifact.sha256:
                raise ValueError(f"evidence checksum mismatch: {artifact.path}")
            if path.stat().st_size != artifact.size_bytes:
                raise ValueError(f"evidence size mismatch: {artifact.path}")
            files[artifact.path] = path.read_bytes()
    return files


def build(root: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("use a new output directory")
    report = root / "reports" / "first-results"
    config = json.loads((report / "package.json").read_text())
    # Require the report and all reproduction code to be committed; an unrelated
    # untracked backup is deliberately neither read nor packaged.
    dirty = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=root, text=True)
    if dirty.strip():
        raise ValueError("commit tracked changes before packaging")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    evidence = verified_evidence(root, config["run_ids"])
    destination.mkdir(parents=True)
    code = subprocess.check_output(["git", "archive", "--format=zip", revision], cwd=root)
    (destination / "theoxenia-source.zip").write_bytes(code)
    for name in (
        "report.pdf",
        "report.md",
        "README.md",
        "SUBMISSION.md",
        "metadata.json",
        "diagnosis-overview.png",
        "diagnosis-overview.svg",
        "summary.json",
        "PROTOCOL.md",
        "VALIDATION.md",
    ):
        data = (report / name).read_bytes()
        committed = subprocess.check_output(
            ["git", "show", f"{revision}:reports/first-results/{name}"], cwd=root
        )
        if data != committed:
            raise ValueError(f"report differs from committed source: {name}")
        (destination / name).write_bytes(data)
    evidence["README.md"] = (report / "README.md").read_bytes()
    evidence["PROTOCOL.md"] = (report / "PROTOCOL.md").read_bytes()
    evidence["SOURCE_REVISION.txt"] = (revision + "\n").encode()
    evidence["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(evidence.items())
    ).encode()
    write_zip(destination / "theoxenia-evidence.zip", evidence)
    (destination / "SOURCE_REVISION.txt").write_text(revision + "\n")
    checks = "".join(f"{sha256_file(p)}  {p.name}\n" for p in sorted(destination.iterdir()))
    (destination / "SHA256SUMS").write_text(checks)
    print(f"Prepared {destination}; revision {revision}. No network requests or submission.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.output.resolve())
