# Scientific dependency compatibility

**Project baseline:** CPython 3.15.0, pinned in `.python-version`, `pyproject.toml`, `uv.lock`, CI and the devcontainer. The science packages are an optional `radio` extra so the static Mission Control demo remains installable without native astronomy dependencies.

## Verified compatibility evidence (2026-10-12)

| Package | Version/evidence | Current conclusion |
|---|---|---|
| CPython | [Python 3.15.0 release](https://www.python.org/downloads/release/python-3150/) | Stable baseline, released 2026-10-09. |
| `turbo-seti` | [PyPI 2.3.2 metadata](https://pypi.org/pypi/turbo-seti/2.3.2/json) | Resolved and imported on CPython 3.15.0 in the isolated test environment; its metadata does not declare `Requires-Python`. Actual Voyager detection remains a separate acceptance test. |
| `setigen` | [PyPI 2.7.0 metadata](https://pypi.org/pypi/setigen/2.7.0/json) | Resolved and imported on CPython 3.15.0 with NumPy 2.5.4 in the isolated test environment; its injection/recovery behavior still needs the project test suite. |
| `blimpy` | [PyPI 2.1.4 metadata](https://pypi.org/pypi/blimpy/2.1.4/json), [upstream requirements](https://github.com/UCBerkeleySETI/blimpy/blob/master/requirements.txt) | Upstream pins `pyparsing==2.4.7`. Installing that exact version on CPython 3.15 fails with `ModuleNotFoundError: No module named 'sre_constants'`. `blimpy` imported in the isolated environment with `pyparsing==3.3.3` and `setuptools==80.9.0`. This repository therefore records an explicit uv override and compatibility test; it does **not** claim upstream has declared Python 3.15 support. Revisit when upstream releases a corrected dependency constraint. |
| `h5py` | [PyPI 3.16.0 metadata](https://pypi.org/pypi/h5py/3.16.0/json) | No CPython 3.15 wheel was available in the verified metadata. The source build succeeded after installing `libhdf5-dev`, `pkg-config`, and build-essential. CI and the devcontainer must install those system packages before syncing the `radio` extra. |
| `fsspec` / `aiohttp` | Isolated versions `fsspec==2026.9.0`, `aiohttp==3.14.5` | `fsspec`'s HTTP filesystem and `h5py` opened the verified 15.4 GB Berkeley HDF5 object via HTTP ranges and read metadata without downloading the whole file. A 1 MHz data-slice read and measured egress are not yet verified. |

## Explicit resolver override

`pyproject.toml` pins `pyparsing==3.3.3` through `tool.uv.override-dependencies`. This is a visible compatibility workaround for `blimpy`'s exact 2.4.7 pin, not an upstream compatibility claim or a Python-baseline downgrade. `setuptools==80.9.0` is also pinned in the radio extra because `blimpy` still imports `pkg_resources`.

The exact `uv.lock` is the resolved environment record. CI must test the radio extra on CPython 3.15, including a real `blimpy` import and deterministic scientific tests. If the override breaks a supported operation, stop and raise a compatibility blocker; do not lower the project baseline silently.

## Primary data endpoints checked

- Official Breakthrough Listen Voyager tutorial notebook: [source notebook](https://raw.githubusercontent.com/ucberkeleyseti/breakthrough/master/GBT/voyager/voyager.ipynb); public file URL and verified SIGPROC header are recorded in [`mission-control-m0.md`](mission-control-m0.md) as the source for EXP-001.
- Official Breakthrough Listen archive: [archive search](https://breakthroughinitiatives.org/opendatasearch); the selected GBT HDF5 record is a Berkeley HTTPS object, not an assumed universal S3 bucket. The exact six A-B-A-C-A-D records, archive query, sizes and MD5 values are recorded in the EXP-030 evidence notes and will be captured in the source manifest before worker runs.

The live M3 worker is not yet deployed. Host egress billing, persistence, restart behavior, and long-running throughput remain unverified until Michael attaches the VM and authorizes the setup described in EXP-030.
