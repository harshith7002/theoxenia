# Scientific dependency compatibility

**Project baseline:** CPython 3.15.0, pinned in `.python-version`, `pyproject.toml`, `uv.lock`, CI, and the devcontainer. The `radio` extra contains the astronomy/data dependencies; base installs can still render the static Mission Control demo.

## Locked and exercised versions (2026-10-12)

| Package | Locked version | Evidence and current conclusion |
|---|---:|---|
| CPython | 3.15.0 | Stable release from [Python.org](https://www.python.org/downloads/release/python-3150/), released 2026-10-09. |
| `turbo-seti` | 2.3.2 | Resolved and imported on CPython 3.15.0. The EXP-001 pipeline uses the documented HDF5 FILTERBANK input path; both prior operational failures are preserved in manifests, and a successful known-answer run must be verified separately. |
| `blimpy` | 2.1.4 | Resolved on CPython 3.15.0. The temporary frequency-sliced HDF5 file is validated with `blimpy.io.hdf_reader.H5Reader(load_data=False)` before turboSETI receives it. The project uses a 16-integration source and does not patch blimpy’s validator. |
| `setigen` | 2.7.0 | Resolved and imported with NumPy 2.5.4. EXP-002 injection/recovery remains a distinct acceptance milestone. |
| `h5py` | 3.16.0 | No CPython 3.15 wheel was present in the checked PyPI metadata; the source build succeeded with HDF5 headers, `pkg-config`, and build tools. The Python 3.15 CI job installs these prerequisites. |
| `hdf5plugin` | 7.1.0 | Direct radio-extra dependency. Imported before HDF5 reads so upstream compression filters are registered; the version and linked libhdf5 version are recorded in EXP-001 run metadata. |
| `fsspec` | 2026.9.0 | Its HTTP bytes-cache supports the measured range reader used for the bounded source access. Actual range intervals and response payload bytes are written to each experiment manifest. |
| `numpy` | 2.5.4 | Direct radio-extra dependency and the verified float32/HDF5 data-array runtime. |

## Explicit resolver overrides

`blimpy==2.1.4` pins `pyparsing==2.4.7` in its upstream requirements. On CPython 3.15 that release fails to import due to the removed `sre_constants` module. The project records `pyparsing==3.3.3` in `tool.uv.override-dependencies`; `blimpy` imports under the override in the locked Python 3.15 environment. `setuptools==80.9.0` is also pinned because this blimpy release still imports `pkg_resources`.

These are visible compatibility workarounds, not upstream Python 3.15 support claims. Do not lower the project baseline silently. Recheck the lock and both workarounds when upstream dependencies change.

## HDF5 layout and source handling

- The canonical test file is `Voyager1.single_coarse.fine_res.h5`, published by the official blimpy test downloader at a Berkeley HTTP URL. The project uses an immutable HTTPS mirror because it will not disable TLS verification; the manifest keeps the publisher URL, mirror commit/blob SHA-1, actual URL, and measured object length distinct.
- The verified source is a 16-integration, single-IF, float32 FILTERBANK with 1,048,576 channels. The slicer copies root and dataset attributes with their HDF5 datatypes preserved, updates only `fch1` and `nchans`, and validates the resulting temporary file with H5Reader.
- The full source and output HDF5 slice remain in a temporary directory. Only a compact JSON summary, the detector hit table summary, the plot, and the run manifest may be committed; no raw source or slice is committed.
- `libhdf5-dev`, `pkg-config`, and a compiler are required to build the current h5py release for Python 3.15. CI and the devcontainer install these before `uv sync --extra radio`.

## Primary compatibility sources

- [Python 3.15.0 release](https://www.python.org/downloads/release/python-3150/)
- [turboSETI 2.3.2 on PyPI](https://pypi.org/project/turbo-seti/2.3.2/)
- [blimpy 2.1.4 on PyPI](https://pypi.org/project/blimpy/2.1.4/)
- [setigen 2.7.0 on PyPI](https://pypi.org/project/setigen/2.7.0/)
- [h5py 3.16.0 on PyPI](https://pypi.org/project/h5py/3.16.0/)
- [blimpy HDF5 reader](https://github.com/UCBerkeleySETI/blimpy/blob/master/blimpy/io/hdf_reader.py)
- [Exact Voyager source and cross-checks](data-sources.md)

The M3 worker’s egress, persistence, restart behavior, long-running throughput, and host availability remain unverified until Michael attaches the VM and approves the exact setup. The Python 3.15 environment itself is not a substitute for that deployment acceptance.
