"""Render publication figures solely from the pinned PUB-002 recorded results."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUN = "20261018T183744725763Z-detector-corrected"


def main():
    records = [json.loads((ROOT / "runs" / RUN / f"scan-{i}.json").read_text()) for i in range(6)]
    out = ROOT / "reports" / "first-results"
    x = np.arange(1, 7)
    observed = [max(t["max_snr"] for t in d["original"]["trials"]) for d in records]
    reference = [max(t["max_snr"] for t in d["independent"]["trials"]) for d in records]
    recovered = [sum(t["recovered"] for t in d["injected_truth"]) for d in records]
    legacy = [
        sum(
            any(
                abs(h["uncorrected_frequency_mhz"] - t["frequency_mhz"]) * 1e6
                <= 3 * 2.7939677238464355
                and abs(h["drift_hz_s"] - t["drift_hz_s"]) <= 0.03
                for h in d["legacy_injected_search"]["hits"]
            )
            for t in d["injected_truth"]
        )
        for d in records
    ]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, axes = plt.subplots(
        1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1.4, 1]}, layout="constrained"
    )
    ax = axes[0]
    ax.plot(x, observed, "o-", color="#176b79", label="turboSETI trials", lw=1.4)
    ax.plot(x, reference, "x--", color="#a35b20", label="Independent straight tracks", lw=1.1)
    ax.axhline(10, color="#b33c38", ls=":", lw=1.5, label="Search threshold = 10")
    ax.set_yscale("log")
    ax.set_ylim(5, 1000)
    ax.set_ylabel("Maximum normalized score (log scale)")
    ax.set_xticks(x, ["1 ON", "2 OFF", "3 ON", "4 OFF", "5 ON", "6 OFF"], rotation=30)
    ax.set_title("A / Why four tables were empty", loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.16)
    ax.legend(fontsize=7.6, loc="upper right")
    ax = axes[1]
    ax.bar(x - 0.18, legacy, color="#9ba8b3", width=0.34, label="Original")
    ax.bar(x + 0.18, recovered, color="#217d85", width=0.34, label="Corrected")
    ax.set_ylim(0, 6.3)
    ax.set_yticks([0, 1, 2, 3, 4, 5])
    ax.legend(fontsize=8, loc="upper left", ncols=2)
    ax.set_xticks(x, ["1", "2", "3", "4", "5", "6"])
    ax.set_xlabel("Scan number")
    ax.set_ylabel("Controls retained as matching top hits")
    ax.set_title("B / Five added tracks per scan", loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.16)
    for ext in ("png", "svg"):
        fig.savefig(out / f"diagnosis-overview.{ext}", dpi=180, metadata={"Creator": "Theoxenia"})
    plt.close(fig)
    rows = []
    for i, d in enumerate(records):
        rows.append(
            {
                "scan": i + 1,
                "role": "ON" if d["role"] == "A" else "OFF",
                "source": d["source"],
                "hits": len(d["original"]["hits"]),
                "turboseti_max": observed[i],
                "independent_max": reference[i],
                "controls_recovered": recovered[i],
                "controls_injected": 5,
                "legacy_controls_recovered": legacy[i],
            }
        )
    (out / "summary.json").write_text(
        json.dumps({"source_run_id": RUN, "rows": rows}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
