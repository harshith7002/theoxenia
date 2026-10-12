# Data-source endpoint check

`configs/sources.yaml` mirrors the nineteen Data Sources rows. `make sources-check` runs:

```bash
xenia sources check --config configs/sources.yaml --out runs/sources-check/sources_check.json
```

Each row is one HTTP request. The client uses the default TLS trust store. Plain HTTP is rejected unless the row sets `allow_plain_http` or the host is loopback. The body read stops at `cap_bytes` (65536). The recorded hash is the hash of those bytes, and `truncated` says whether the response continued.

A row is `verified` only when the live status is 2xx and either some body bytes or a positive `Content-Length` came back. A `content_type_prefix` must match when the row sets one. Rows marked `credential_required` stay `blocked` even when the server answers, because the data product needs an account or a paid agreement. A transport failure with no status can use `synthetic_fixture`. That result is `synthetic`, `numbers_from` is `fixture`, and `probe_url` is `synthetic://<id>`. `elapsed_s` on that row is the failed live attempt. The run manifest sets `demo` true when any row is synthetic.

The nightly workflow `.github/workflows/sources-check.yml` runs the same command on a schedule. Its permission is `contents: read`. It uploads the JSON as an artifact and does not push.

Accounts for Space-Track and the NARA catalog key are not created by this command.

## Measured run

Run `20261012T220933913511Z-sources-check` started 2026-10-12T22:09:33.913511Z and finished 2026-10-12T22:11:24.316962Z. `git_sha` is `e9db4be`. The manifest is `demo: true` because `cneos-fireball` used the synthetic fixture. Counts were verified 12, blocked 6, synthetic 1. The blocked ids were `aaro`, `technosearch`, `galileo`, `nara-catalog-api`, `space-track`, and `enigma`.

The synthetic row's HTTP 200 and 73-byte body are `tests/fixtures/sources/unreachable.json`, not a CNEOS response. The live error was `CERTIFICATE_VERIFY_FAILED` / `unable to get local issuer certificate`. OpenSSL `s_client` to `ssd-api.jpl.nasa.gov` on this host returned verify error 20 (unable to get local issuer certificate) for a chain ending at Entrust OV TLS Issuing RSA CA 2. No fireball count is taken from the fixture.

The GFZ probe followed a redirect to `https://kp.gfz.de/app/json/` and returned 394 bytes, sha256 `22b8fb82c275247b70696a1150fe17f6561590bbe299a107592de4ea5b057276`. That body is `tests/fixtures/sources/gfz-kp-2004-11-14.json`. The nine Kp values from 2004-11-14T00:00:00Z through 2004-11-15T00:00:00Z are 4.0, 2.667, 2.0, 1.333, 1.0, 1.333, 1.0, 0.333, 0.333. Each `status` entry was `def`. The license field in the payload was `CC BY 4.0`.
