# Grok night order 1 — 2026-10-12 → 2026-10-13

**Issued by Michael on the evening of 2026-10-12. Supplements `agents/grok.md`; where the two differ, this file wins for tonight only.**
Phase 0 is done. Tonight you work unattended until the list below is exhausted or 07:00 Europe/Athens, whichever comes first. Tomorrow Manus takes deployment (host, `live` branch bootstrap, Pages, recovery test, soak). Your job is to leave Manus nothing to do but run what you built, and to leave Michael a stack of small, reviewable pull requests plus a morning report.

---

## 1 · Night rules (overrides for tonight)

1. **Do not block on Needs Michael.** The master script says stop; tonight you park the item (row Status `Blocked`, one line saying what is needed), log it in the morning report, and move to the next independent item. Nothing on this list waits for a human.
2. **Everything else in `agents/grok.md` section 3 holds unchanged**: zero spend, no accounts, no publishing outside GitHub and Notion, no contact with anyone, no `UNEXPLAINED`, no raw data in Git, no secrets anywhere, no TLS bypass, Python 3.15.0, manifests for every result.
3. **Never push to `main`, never merge, never create the `live` branch tonight** (Manus bootstraps it tomorrow from merged `main`). Branches and pull requests only. If you have no token, work in patch mode exactly as before: one branch per track in the local repo, commits made, and the morning report lists `git push` commands for Michael.
4. **Stacked PRs are fine; say so.** Independent tracks branch from `main`. A track that needs another's code branches from that track's tip and its PR description starts with "Stacked on #N". The morning report lists the merge order.
5. **Depth over speed.** Michael has the token budget. Every module gets focused tests, a docstring that says what it does and does not claim, and a short docs page. Every command gets a `make` target. Run `make test lint schemas-check files-check docs` before every commit you intend to push.
6. **Fall back to synthetic, never to fiction.** When a network source is unreachable, build the same code path on a synthetic known-answer fixture, say so in the manifest (`demo: false`, inputs `synthetic://...`), and leave the real-data run as a one-line command for tomorrow. Never write a number you did not measure.
7. **Notion as you go**, not at the end: each track has a Task row (create it if missing, Owner Grok, link the EXP-030 task in Notes), each result-producing run has an Experiment row, each blocker a Blocked row. The master script's section 6 report format applies at the end of every track.
8. **Reassignments Michael authorises for tonight** (set Owner to Grok and Status to `Next` when you start them, note "reassigned by Michael 2026-10-12 night order"): Verify every Data Source endpoint (Manus); Weekly Log week 1 (Manus); Budget check (Manus); EXP-020 Nimitz baseline (Manus); EXP-010/011 Blue Book OCR (Manus); Deconfliction brief Nimitz (Grok, `Backlog` → `Next`); Reproduction plan BLC1 and Ma et al. (Claude); CONTRIBUTING.md and five good-first-issues (Claude). Leave every other Manus or Michael row alone. M3.4 (soak) and the host row go to Manus: set M3.4 Owner to Manus with your handover in its Notes (track J).

---

## 2 · Tracks, in order

Work top to bottom. Each track: what, acceptance, PR. Start the next track while a long run is in progress rather than waiting.

### Track A · Housekeeping (15 minutes)

- Commit `agents/grok.md`, this file as `agents/grok-night-01.md`, and the `agents/README.md` pointer. Add `.gitignore` entries if `runs/*/manifest.json` from your Phase 0 `live-build` should not be committed (they are demo build/render manifests; keep only if they reference fixtures, which they do, so keep them but say so in the PR).
- PR: `docs/agent-scripts` → "docs: add Grok master script and night order 1".

### Track B · Fix the ruler, EXP-002 v2 (master script Phase 1, unchanged)

- Failing test first, matcher fix (`uncorrected_frequency` vs `plan.start_frequency_mhz`), H2 sign check, tolerance only if evidence, `make floor-smoke` then `make floor`, docs, Experiment row, first run → `Bug · invalid`.
- Add to the floor artifact a `matching_rule` string and `matching_version: 2` so a reader can tell v1 and v2 grids apart without reading code.
- Acceptance: nonzero-drift cells recovered; `floor_summary` emits the "Recovers SNR ≥ N at drift within ±3 Hz/s." branch; test for it; CI reduced grid green.
- PR: `exp/002-floor-v2`.

### Track C · EXP-004, synthetic ABACAD cadence known-answer (new, host-free, unblocks M3 code)

The ON/OFF logic has never been exercised. Build the fixture that proves it, then every M3 module can be tested against it tonight and in CI forever.

- `xenia.radio.cadence_synth`: generate six setigen frames (A, B, A, C, A, D) with the EXP-002 frame geometry, seeded. Inject: (1) one line at +0.8 Hz/s present only in the three A frames (the expected `ON_ONLY` survivor); (2) one zero-drift line in all six frames (expected `IN_OFF`); (3) one line in a single A frame only (expected `SINGLE_POINTING`); (4) one line inside a `known_sources.yaml` range (expected `KNOWN_SOURCE`). Write six neutral-metadata filterbanks to a temp dir, as EXP-002 does. Record every injected frequency, drift, SNR and the expected verdict in a `truth.json`.
- `xenia.live.search`: `FindDoppler` per file (`max_drift 4.0`, `snr 10`, `n_coarse_chan 1`), then `find_event_pipeline` across the six `.dat` files with `filter_threshold 3`. Wrap turboSETI's known final-logging `TypeError` exactly as EXP-001/EXP-002 do.
- `xenia.live.verdict`: spec §4.5 taxonomy, first match wins, exact badge texts; §8.6 five checks as booleans with notes; `UNEXPLAINED` unreachable (test asserts it).
- `xenia live cadence --synthetic --seed 20261012 --experiment-id EXP-004`: runs the above, writes `runs/<RUN_ID>/manifest.json` with `mission_control.kind = "cadence"` (fixture shape), `hits.parquet` (pyarrow or polars, add to `radio` extra, pin, document in `docs/DEPENDENCIES.md`), `truth.json`, `recovery.json` (expected vs assigned verdict per injection), and outcome `searched_with_survivors`.
- Acceptance: all four injections get their expected verdict; a test runs the reduced version in CI (one seed, small frames, under 3 minutes); `make live-evidence` renders the synthetic cadence as a pointing with four gallery tiles; the page says in the tile explanation that the cadence is synthetic.
- Notion: Task row "EXP-004 · Synthetic ABACAD cadence known-answer for the ON/OFF filter", Experiment row with Outcome `Reproduced published result` only if all four verdicts match, else `Bug · invalid` with what failed.
- PR: `exp/004-synthetic-cadence`.

### Track D · Reach the real data (master script Phase 2.1–2.4)

- Do the §12 verification in full and write every finding into the Data Sources rows with URL and date: where the GBT fine-resolution cadences live today, HTTP `Range` support (expect 206), transport (HTTPS or plain HTTP), file naming and cadence membership, channel width and integration count from a bounded header read, bytes per 1 MHz window per file.
- If the publisher is plain HTTP only: write the D-018 proposal row (`Proposed`, Needs Michael), implement the slicer with `allow_plain_http: false` as the default in `configs/live.yaml`, and prove the slicer on the HTTPS Voyager mirror plus the EXP-004 synthetic files instead. Leave `make cadence` wired to the chosen real cadence so Manus or Michael can run it with one command once D-018 is accepted.
- If HTTPS ranges work: run EXP-003 for real (`xenia live cadence --files ... --window ...`), commit manifest, `hits.parquet`, thumbnails, plots; Experiment row EXP-003 on the original Manus row (now yours).
- `xenia.live.slicer.slice_cadence(...)` extends `xenia.radio.remote` (transfer cap as a parameter, recorded) and `xenia.radio.hdf5.slice_hdf5_filterbank`; optional anonymous S3 transport behind the same interface only if a bucket is verified.
- PR: `exp/003-cadence` (stacked on `exp/004-synthetic-cadence`).

### Track E · M3 code, runnable locally (master script 3.1–3.5 and the code half of 3.6–3.7)

- `configs/live.yaml` (§8.5 plus `transfer_cap_bytes`, `allow_plain_http`), `configs/known_sources.yaml` with a verified `source` per range (drop any range you cannot source), `xenia live queue build` → `configs/queue.jsonl` (breadth-first, `priority`, header line with listing URL and sha; if the real listing is unreachable tonight, a synthetic queue of EXP-004 cadences with a `synthetic: true` flag).
- `xenia.live.plots`: 320×140 thumbnails with `theoxenia_night`, six-panel `plot_event` unmodified, hero reuse; all PNGs under 2 MiB.
- `xenia.live.worker`: `xenia live run --once [--max-pairs N]` and `--forever` per §8.3; worker manifest at `runs/worker-<host>/manifest.json` overwritten each heartbeat; `git pull --ff-only` at loop top; commit every 30 minutes or on a survivor to the branch named in `configs/live.yaml` (`live` by default, never `main`); push only if `THEOXENIA_PUSH=1`; `data/tmp` deleted per pair; two retries then `failed`. `.gitignore` allow-list extended for `hits.parquet`, `thumbs/*.png`, `plots/*.png`, the worker manifest.
- Run `xenia live run --forever` against the synthetic queue for 60 minutes locally with `THEOXENIA_PUSH=0`. Record pairs/hour, peak RSS, disk, and that the heartbeat never aged past 10 minutes. Those are the first throughput numbers for the EXP-030 Experiment row (labelled synthetic).
- `deploy/run.sh` (real flags, as in the master script), `deploy/README.md` (supervisor contract, env vars, what `/healthz` means, how to run on a VM with systemd, on a Manus persistent task, or nothing), `scripts/recovery_check.py` (normalise heartbeat and ticker, diff two `index.html`), `.github/workflows/pages.yml` (rebuild from manifests on `live`, mirror pill), `.github/workflows/live-pulse.yml` (schedule commented out, `/healthz` guard, D-017 row `Proposed`).
- Acceptance: `make test` covers queue, verdict, search, worker (with a fake slicer), plots; `make live-evidence` renders a page with worker status, pointings, gallery from the synthetic run; `deploy/run.sh` executes end to end on your machine with `THEOXENIA_PUSH=0` and serves `/healthz` 200 while the loop runs.
- PRs: `feat/mission-control-m3-queue`, `feat/mission-control-m3-worker`, `feat/mission-control-m3-deploy` (stacked in that order on Track C/D).

### Track F · Mission Control, the page grows (master script Phase 4 plus expansion)

- Copy to §4.4 word for word except the gallery heading; D-019 row; banned-word test on the rendered page.
- Status pill three states with frozen-clock tests; mirror variant.
- **Detail pages (new):** `site/cadences/<cadence_id>/index.html` (target, coordinates, window, six-panel plots, every hit with verdict and the five checks, manifest link, the exact command to reproduce) and `site/hits/<hit_id>.html`. Rendered by `xenia live render`, linked from sky-map dots and gallery tiles, same tokens, no JavaScript required, listed in a `site/sitemap.xml`.
- **Experiments index (new):** `docs/experiments.md` generated from every manifest under `runs/` by `xenia docs experiments` (ID, date, outcome, command, manifest link); wired into `mkdocs.yml`; `make docs` fails if stale, same pattern as `schemas-check`.
- Open Graph tags with the newest waterfall; `feed.json` (JSON Feed 1.1) of survivors; README "Mission control" section with the reproduce-one-tile walkthrough; 360 px layout check with no horizontal scroll; `loading="lazy"`; SVG `role`/`aria-label`; contrast ≥ 4.5:1.
- **Later-panel placeholders (spec §10 "Later panels"):** two quiet, honest cards under the gallery, "Disclosure, Project Blue Book incident map: not started" and "Near-Earth baselines, CNEOS and Kp: not started", each becoming live only when a manifest of that pillar exists (Track H can light them tonight).
- PR: `feat/mission-control-m4-polish` then `feat/mission-control-detail-pages` (stacked).

### Track G · Research deliverables (your strength; interleave with long runs)

- **Verify every Data Source row** (all 19): fetch real bytes or a real response, set `Verified`/`Blocked`, fill Access, Formats, Cost, rate limits, registration needs, Notes with URL and date. Create `configs/sources.yaml` mirroring the database and `xenia sources check --out runs/<RUN_ID>/sources_check.json` with a manifest, so the check reruns in a nightly workflow (add it, schedule on, read-only permissions, no secrets).
- **`docs/known-sources.md`**: one paragraph per range with primary source and date.
- **Deconfliction brief, Nimitz 2004-11-14**: launches, re-entries, satellite passes, exercises, balloons, bolides, each with a source; write into the Nimitz Candidate row and a new Experiment row; no anomaly language.
- **Reproduction plan for BLC1 (Sheikh et al. 2021) and Ma et al. 2023**: data, code, compute, whether the public archive holds the exact files; page under Source Material; update the BLC1 Candidate row.
- **Budget check**: egress per pair and per day from Track D numbers, what would ever cost money, written for D-002.
- **Weekly Log, week 1 entry**: what ran, what was found, what is blocked, three to six bullets, one line of real-world context.

### Track H · Light the other two pillars with one slice each (roadmap Phase 1)

- **EXP-020 · Nimitz public-record baseline** (Pillar III): `xenia fusion baseline --lat 31.0 --lon -118.5 --start 2004-11-14T00:00Z --end 2004-11-15T00:00Z --radius-km 800` → `runs/<RUN_ID>/baseline.json` with CNEOS fireballs (API verified in Track G) and GFZ Kp for those dates; no Space-Track (needs Michael's account; say so in the manifest notes). Pydantic model, schema export, tests with recorded fixtures, manifest, Experiment row, Nimitz Candidate row `Checks done` updated. Light the CNEOS/Kp card on the page from this manifest.
- **EXP-010 · Project Blue Book OCR baseline** (Pillar II): `xenia disclosure ocr file.pdf` with pymupdf + OpenCV + Tesseract on five to twenty case files from the Black Vault or NARA (download to `data/`, never commit; record exact URLs and sha256); per-page text and a manifest; a character-error-rate check on three hand-verified pages; `xenia disclosure prompt` printing the IncidentTelemetry schema prompt and `xenia disclosure validate` (Pydantic model from the scaffold's intent, re-derived, not copied); Experiment row. Light the Blue Book card with a count of pages processed.
- PRs: `exp/020-nimitz-baseline`, `exp/010-bluebook-ocr`, each from `main`.

### Track I · Hardening and community (when the above is done, never instead of it)

- Property-based tests (hypothesis) for the verdict function and the floor matcher; mutation-style negative tests for the banned-word scanner.
- `mypy --strict` on `src/xenia` as a CI job (fix what it finds; `# type: ignore` only with a reason).
- `SECURITY.md`, `.github/dependabot.yml` (uv/pip and actions, weekly), `CODEOWNERS` (Michael), issue template for a cadence claim, `.zenodo.json` prepared (no release).
- `CONTRIBUTING.md` refresh and five good-first-issues filed on GitHub as issues labelled `good first issue`: reproductions and small data-source additions, not greenfield features.
- Pre-commit hook that runs the banned-word scan on `site/templates/`.

### Track J · Morning handover (last thing you do, before 07:00 Athens)

- **For Manus**, in the Notes of the M3.4 row (Owner → Manus) and in `deploy/README.md`: the exact sequence for tomorrow: merge order of your PRs; `git push origin main:live` after merges; enable Pages (Michael) and first `pages.yml` run; put `GITHUB_TOKEN` and `THEOXENIA_HOST` in the host secret store; start `deploy/run.sh`; run `scripts/recovery_check.py` on a second fresh box; 24-hour soak with the numbers to record; fill spec section 16. One command per line, nothing that needs interpretation.
- **For Michael**, the morning report (section 6 format) plus: PR list in merge order with one line each; every Blocked row; every decision row you proposed (D-017, D-018, D-019); what you could not verify; what surprised you.
- Update the status block at the top of `agents/grok.md`.

---

## 3 · Not tonight

Hosting or provisioning anything; creating the `live` branch; enabling any schedule that pushes; merging; touching `main`; the exoplanet half of Pillar I (D-007 says Phase 2; a decision row is the only way in); Space-Track, NARA key, Hugging Face (accounts); contacting anyone; FOIA; any page copy containing the banned words; any verdict beyond `ON_ONLY`.

---

## 4 · If you run out of list

Re-run `make floor` with two more seeds and report seed-to-seed variance; profile turboSETI on one slice and write the numbers into `docs/mission-control-m3.md`; add a `xenia live replay --at <git-sha>` that rebuilds the page as of any commit; add a Greek translation of the page subtitle and legend behind a `lang` query switch with no JavaScript required; write `docs/architecture-asbuilt.md` describing what actually exists versus the Notion Architecture page, section by section, with no claims beyond the code.
