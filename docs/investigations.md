# Guided investigations and public research evidence

The first public edition has three curated investigations, an interactive archive explorer and evidence dossiers. Stories are pinned to specific run IDs in `src/xenia/live/investigations.py`; a later experiment does not silently inherit an older interpretation. Card plots are generated from the pinned records too.

## Visitor experience

- `investigations.html`: three guided stories with four steps each.
- `investigations/voyager.html`: original spacecraft waterfall and recorded carrier measurement.
- `investigations/archive.html`: six-scan method, full classification counts and the open detector issue.
- `investigations/recovery.html`: a keyboard-accessible 72-cell synthetic recovery grid; each cell reports recovered trials, not estimated certainty.
- `explorer.html`: complete 273-row table, frequency/drift scatter, classification/SNR/text filters, sorting, selected check notes, deep links, CSV download, and measured waterfall previews with frequency zoom/pan and common display contrast.
- `dossiers/<run-id>.html`: source identifiers, checks, limitations, parameters, recorded code revision, original notes and a compact downloadable ZIP with checksummed outputs.
- `research.html`: legitimate contribution routes and explicit external status.

The core content remains readable without JavaScript. Canvas previews and linked selection are progressive enhancements. Every asset is local. The static build needs no scientific extras and performs no network requests or experiment processing.

## Real-data preparation (PUB-001)

Run `20261018T175821546488Z-public-evidence` reads the complete committed EXP-003 Parquet table and fetches the same six 1380–1381 MHz archive slices through the bounded HTTPS reader. Each source has a 256 MiB transfer cap. All six resulting slice SHA-256 values exactly match the original inputs. All values in these slices were finite and positive.

The 16 time integrations and 357,913 native frequency channels per scan are reduced to 1,024 display bins by averaging linear power within each bin, then taking dB relative to the median native-channel power of that integration. The browser uses a shared, explicitly labelled contrast range across panels. The display cannot recover native frequency resolution when zoomed. Time increases downward from each scan start; inter-scan gaps are not plotted.

The export includes every Parquet field, preserving the classification and all check notes. Tests compare every exported row with the source table. Runtime rendering checks the preparation output hash, parent-table hash, parent identity, row uniqueness and complete classification counts before showing the explorer.

This is new processing of real archived data, **not a new detector search or additional observation exposure**. In particular, the finite/positive power check does not establish that the detector correctly handled the later ON scans. The empty later ON tables remain an open investigation. The historical `session_census_clear=true` value came with a note that no other cadence was supplied; the inspector therefore displays **Not tested** while preserving the original note. Original scientific records are not rewritten.

To produce another preparation record (radio extras and network access required):

```bash
uv run --locked --extra radio python scripts/prepare_explorer.py \
  --source-run 20261012T203545022355Z-exp-003-cadence --waterfalls
```

Omit `--waterfalls` for a complete table export without archive requests. Each invocation writes a new record. The latest preparation for the pinned source is selected; a table-only preparation deliberately has no waterfall panels. Raw slices are deleted after processing and never enter Git. The exact processor source is preserved as `processor.txt`. In the initial run, the script was an uncommitted addition; the manifest records that fact, its base revision, and the script checksum.

## External contribution routes

There is no verified general submission portal that certifies our routine SETI checks. The following routes serve different purposes; none has been used by this release:

1. **Citable research artifacts:** [Zenodo records](https://help.zenodo.org/docs/deposit/about-records/) support datasets, reports and software. Publication registers a DOI. This is preservation and attribution, not peer review. A first deposit should include a bounded report, code snapshot, compact processed tables, limitations and upstream data credits. Review the existing `CITATION.cff` and `.zenodo.json` before publishing.
2. **Upstream software contributions:** [Berkeley's open-data participation page](https://seti.berkeley.edu/listen/data.html) invites software and algorithm work. Submit a reproducible bug, benchmark or tested patch through the relevant repository's current accepted route. Do not assume issue creation is open: the [turboSETI issue page](https://github.com/UCBerkeleySETI/turbo_seti/issues) currently reports restrictions.
3. **Scientific collaboration:** [Berkeley's contact page](https://seti.berkeley.edu/contact.html) lists `bsrc@berkeley.edu` for scientific collaborations. Prepare a short report before outreach; contact does not imply acceptance, affiliation or a guaranteed review.

Official sources checked 2026-10-18. Some participation material is historical. Verify the current route before sending. No email, issue, DOI deposit or external research submission was made. Public badges must only change when a real external record exists.

## Release checks

Build into an empty directory using `scripts/build_public_site.py`. Run the full Python suite, lint, typing, schema freshness, file policy and strict docs build. Public-site tests check local asset/navigation targets, deterministic builds, source-table parity, hash failures, provenance mismatches, complete no-script content and ZIP checksum integrity. Browser review covers filters, empty results, selection, deep links, recovery cells and measured previews. A small-screen browser frame is useful but is not a claim of physical-device testing.

The Pages deployment remains manual and separate from code pushes. No live-worker, source-archive partnership, external review or discovery claim is introduced by the public edition.
