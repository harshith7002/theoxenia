"use strict";
document.querySelectorAll(".recovery-cell").forEach((cell) => {
  cell.addEventListener("click", () => {
    document.querySelectorAll(".recovery-cell").forEach((other) => other.setAttribute("aria-pressed", "false"));
    cell.setAttribute("aria-pressed", "true");
    const d = cell.dataset;
    document.getElementById("recovery-selection").textContent = `Injected SNR ${d.snr} · Drift ${Number(d.drift) > 0 ? "+" : ""}${d.drift} Hz/s → ${d.count} of ${d.trials} recovered. These are recorded trials, not a probability estimate.`;
  });
});
