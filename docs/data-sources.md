# Data sources and verification notes

This page records the public sources used by the radio pipeline. A URL or published example is not a Theoxenia result; experiment measurements must come from a committed run manifest.

## EXP-001: Voyager 1 known-answer sample

| Item | Source/evidence |
|---|---|
| Primary project page | [Breakthrough Listen open-data page](https://seti.berkeley.edu/listen/data.html) |
| Tutorial notebook | [Official UCBerkeleySETI Voyager notebook](https://github.com/ucberkeleyseti/breakthrough/blob/master/GBT/voyager/voyager.ipynb) |
| Public sample | [`voyager_f1032192_t300_v2.fil`](https://storage.googleapis.com/gbt_fil/voyager_f1032192_t300_v2.fil) |
| Instrument/context | The notebook identifies a Green Bank Telescope X-band observation of Voyager 1 on 2015-12-30. It reports a two-integration SIGPROC filterbank and points to the public `.fil` file. |
| Bounded header verification | An HTTP byte-range read of the public file returned `Content-Range: bytes 0-65535/528482692`. The parsed header reported `source_name=VOYAGER1`, 66,060,288 channels, one IF, 32-bit samples, `tsamp=105.6964608` s, `fch1=8588.964842330843` MHz, and `foff=-2.838316417875744e-06` MHz. No full source file was downloaded or committed. |
| Two-integration reader caveat | The official sample contains only two integrations. blimpy 2.1.4's [`examine_h5()`](https://github.com/UCBerkeleySETI/blimpy/blob/master/blimpy/io/hdf_reader.py) unconditionally reads `data[2]`, so its normal validation rejects this valid shape. The project runner temporarily replaces only that check for `(2, 1, nchan>=3)`, validates filterbank class/version and readable data endpoints, and restores the upstream validator before returning. Other dataset shapes use blimpy's original validator. |
| Project processing | `xenia live hero --voyager` reads only the header and selected channel ranges. The 1 MHz temporary filterbank slice, HDF5 conversion (if created by turboSETI), and detector `.dat`/`.log` files live outside the repository and are removed after the run. Actual transfer ranges, byte counts, slice hash, hit summary, plot, and manifest are recorded under `runs/<RUN_ID>/`. |

The range-verified header values are source metadata, not a signal-detection claim. The output must identify a hit from the Theoxenia run before `EXP-001` can populate the Mission Control hero.

## Published turboSETI reference example

The upstream [turboSETI README](https://github.com/UCBerkeleySETI/turbo_seti/blob/master/README.md) includes a Voyager example on a separate HDF5 file, `Voyager1.single_coarse.fine_res.h5` (MJD 57650.7821, observed 2016-09-19). Its sample table reports hits at approximately 8419.319368 MHz (drift −0.392226 Hz/s, SNR 30.612) and 8419.297028 MHz (drift −0.373093 Hz/s, SNR 245.708). **That is not the same observation as the 2015-12-30 `.fil` above.** The project uses 8419.319368 MHz only as a documented search-window reference, with an explicit ±0.02 MHz matching tolerance; a Theoxenia hit remains unverified until the run manifest records it.

The reference run uses turboSETI's upstream `FindDoppler` API. The default SNR threshold is 25, matching turboSETI's documented CLI default; the chosen 4 Hz/s maximum drift and 1 MHz slice are explicit experiment parameters, not source facts.

## Data-handling rules

- Use HTTPS and byte ranges only; do not fall back to downloading an entire source file.
- Apply an explicit transfer cap before reading remote data.
- Keep raw telescope data and temporary frequency slices out of Git and persistent project directories.
- Store compact manifests, summaries, and plots; record exact source URL, observed size, transfer ranges, detector version, parameters, code SHA, timestamps, and outcome.
- A null run, a failed read, and a detector error are recorded as such. None is silently converted into a positive finding or a scientific non-detection claim.

## Additional sources

- [turboSETI 2.3.2 on PyPI](https://pypi.org/project/turbo-seti/2.3.2/)
- [SIGPROC filterbank format guide](http://sigproc.sourceforge.net/sigproc.pdf)
- [Official Python 3.15.0 release](https://www.python.org/downloads/release/python-3150/)

Source facts and compatibility evidence last checked: 2026-10-12. Recheck mutable upstream pages before future baseline or source changes.
