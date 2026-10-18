"use strict";
(() => {
  const element = document.getElementById("explorer-data");
  if (!element) return;
  const evidence = JSON.parse(element.textContent);
  const byId = new Map(evidence.rows.map((row) => [row.hit_id, row]));
  const $ = (id) => document.getElementById(id);
  const tableRows = new Map([...document.querySelectorAll("#hit-rows tr")].map((tr) => [tr.dataset.hit, tr]));
  const points = new Map([...document.querySelectorAll("#scatter-points a")].map((a) => [a.dataset.hit, a]));
  let selected = null;
  const label = (value) => value === "IN_OFF" ? "In OFF scans" : "Single pointing";
  function text(tag, content, className) {
    const node = document.createElement(tag);
    node.textContent = content;
    if (className) node.className = className;
    return node;
  }
  function select(id, updateHash = true) {
    const row = byId.get(id);
    if (!row) return;
    selected = row;
    $("selected-id").textContent = `Row ${row.hit_id.split("-").pop()}`;
    $("selected-verdict").textContent = label(row.verdict);
    $("selected-explanation").textContent = row.explanation;
    $("selected-association").textContent = row.association_note;
    const metrics = [["Frequency", `${row.freq_mhz.toFixed(6)} MHz`], ["Drift", `${row.drift_hz_s.toFixed(6)} Hz/s`], ["SNR", row.snr.toFixed(2)], ["Matching scans", `${row.on_count} ON / ${row.off_count} OFF`]];
    $("selected-metrics").replaceChildren(...metrics.map(([name, value]) => {
      const item = document.createElement("div"); item.append(text("dt", name), text("dd", value)); return item;
    }));
    const checks = [["Cadence filter", "not_in_off"], ["Known-source catalogue", "not_known_transmitter"], ["Drift check", "drift_sane"], ["Session census", "session_census_clear"], ["Review", "review"]];
    $("selected-checks").replaceChildren(...checks.map(([name, key]) => {
      const note = row[`note_${key}`] || "No note recorded.";
      // The historical boolean is true when the census was not supplied.
      // Preserve its note, but never display that missing check as a pass.
      const missing = key === "session_census_clear" && note.includes("No other cadence");
      const status = missing ? "Not tested" : key === "review" && !row[key] ? "Not reviewed" : row[key] ? "Recorded pass" : "Not passed";
      const box = document.createElement("details");
      const summary = document.createElement("summary");
      summary.append(text("span", name), text("span", status, missing || key === "review" ? "check-open" : ""));
      box.append(summary, text("p", note)); return box;
    }));
    for (const [key, tr] of tableRows) {
      tr.classList.toggle("is-selected", key === id);
      tr.querySelector("button").setAttribute("aria-pressed", String(key === id));
    }
    for (const [key, a] of points) a.classList.toggle("is-selected", key === id);
    $("selection-announcement").textContent = `${row.hit_id}, ${label(row.verdict)}, ${row.freq_mhz.toFixed(6)} MHz selected.`;
    if ($("frequency-centre")) $("frequency-centre").value = row.freq_mhz;
    if (updateHash) history.replaceState(null, "", `#hit=${encodeURIComponent(id)}`);
    drawWaterfalls();
  }
  function filter() {
    const classification = $("verdict-filter").value;
    const minimum = Math.max(0, Number($("snr-filter").value) || 0);
    const query = $("hit-search").value.trim().toLowerCase();
    const visible = evidence.rows.filter((row) => (classification === "all" || row.verdict === classification) && row.snr >= minimum && (!query || `${row.hit_id} ${row.freq_mhz.toFixed(6)}`.toLowerCase().includes(query)));
    const visibleIds = new Set(visible.map((row) => row.hit_id));
    const sort = $("sort-order").value;
    visible.sort((a, b) => sort === "frequency" ? a.freq_mhz - b.freq_mhz : sort === "drift" ? a.drift_hz_s - b.drift_hz_s : b.snr - a.snr);
    for (const [id, tr] of tableRows) tr.hidden = !visibleIds.has(id);
    for (const [id, a] of points) a.style.display = visibleIds.has(id) ? "" : "none";
    visible.forEach((row) => $("hit-rows").append(tableRows.get(row.hit_id)));
    $("result-count").textContent = `${visible.length} of ${evidence.rows.length} rows · Recorded classifications`;
    $("empty-results").hidden = visible.length !== 0;
    if (visible.length && (!selected || !visibleIds.has(selected.hit_id))) select(visible[0].hit_id);
    if (!visible.length) {
      selected = null;
      history.replaceState(null, "", location.pathname);
      $("selected-id").textContent = "No matching rows";
      for (const name of ["selected-verdict", "selected-explanation", "selected-association", "selected-metrics", "selected-checks"]) $(name).replaceChildren();
      for (const tr of tableRows.values()) { tr.classList.remove("is-selected"); tr.querySelector("button").setAttribute("aria-pressed", "false"); }
      for (const a of points.values()) a.classList.remove("is-selected");
      drawWaterfalls();
    }
  }
  function colour(value) {
    const stops = [[6, 13, 29], [22, 57, 92], [26, 132, 149], [111, 227, 221], [255, 225, 156]];
    const scaled = Math.min(0.99999, Math.max(0, value)) * (stops.length - 1);
    const index = Math.floor(scaled), part = scaled - index;
    return stops[index].map((c, i) => Math.round(c + (stops[index + 1][i] - c) * part));
  }
  function drawWaterfalls() {
    if (!evidence.scans.length) return;
    const width = Number($("zoom-window").value);
    const lowBand = evidence.window_mhz[0], highBand = evidence.window_mhz[1];
    const centre = Math.min(highBand - width / 2, Math.max(lowBand + width / 2, Number($("frequency-centre").value)));
    const low = centre - width / 2, high = centre + width / 2;
    $("frequency-centre").value = centre;
    $("frequency-readout").value = centre.toFixed(3);
    $("frequency-left").textContent = low.toFixed(3); $("frequency-right").textContent = high.toFixed(3);
    const maximum = Number($("contrast").value);
    $("contrast-high").textContent = `+${maximum} dB`;
    evidence.scans.forEach((scan, i) => {
      const canvas = document.querySelector(`[data-scan="${i}"]`);
      const context = canvas.getContext("2d");
      const w = canvas.width, h = canvas.height, values = scan.relative_db;
      const pixels = context.createImageData(w, h);
      for (let y = 0; y < h; y++) {
        const row = values[Math.min(values.length - 1, Math.floor(y / h * values.length))];
        for (let x = 0; x < w; x++) {
          const freq = low + (x + 0.5) / w * width;
          const bin = Math.floor((freq - scan.frequency_low_mhz) / (scan.frequency_high_mhz - scan.frequency_low_mhz) * row.length);
          const rgb = bin < 0 || bin >= row.length ? [7, 11, 20] : colour((row[bin] + 1) / (maximum + 1));
          const p = (y * w + x) * 4;
          pixels.data[p] = rgb[0]; pixels.data[p+1] = rgb[1]; pixels.data[p+2] = rgb[2]; pixels.data[p+3] = 255;
        }
      }
      context.putImageData(pixels, 0, 0);
      if (selected && selected.freq_mhz >= low && selected.freq_mhz <= high) {
        const x = (selected.freq_mhz - low) / width * w;
        context.strokeStyle = "#ffffff"; context.lineWidth = 2; context.setLineDash([5, 5]);
        context.beginPath(); context.moveTo(x, 0); context.lineTo(x, h); context.stroke(); context.setLineDash([]);
      }
    });
  }
  document.querySelectorAll("[data-hit]").forEach((element) => {
    if (element.tagName === "TR") return;
    element.addEventListener("click", (event) => {
      event.preventDefault(); select(element.dataset.hit);
      $("selected-hit").focus({preventScroll: true});
      $("selected-hit").scrollIntoView({behavior: "instant", block: "start"});
    });
  });
  $("filters").addEventListener("submit", (event) => event.preventDefault());
  for (const id of ["verdict-filter", "snr-filter", "hit-search", "sort-order"]) $(id).addEventListener("input", filter);
  $("reset-filters").addEventListener("click", () => { $("filters").reset(); history.replaceState(null, "", location.pathname); filter(); });
  if ($("zoom-window")) $("zoom-window").addEventListener("input", () => {
    if (selected) $("frequency-centre").value = selected.freq_mhz;
    drawWaterfalls();
  });
  for (const id of ["frequency-centre", "contrast"]) if ($(id)) $(id).addEventListener("input", drawWaterfalls);
  const initial = new URLSearchParams(location.hash.slice(1)).get("hit");
  if (byId.has(initial)) select(initial, false);
  filter();
})();
