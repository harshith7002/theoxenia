# Automated archive observatory

The public site remains at <https://mpetyx.com/theoxenia/>. The observatory processes archived telescope recordings in bounded passes and automatically publishes verified evidence. It is not a live telescope feed. Report 01 and its original guided investigations retain their frozen evidence; new measurements have their own manifests.

## Operating model

The `Observatory` Actions workflow checks the queue every three hours at minute 43, processing at most one unfinished real window per invocation. GitHub may delay scheduled starts. The job has a 35-minute limit and uses standard Linux runners in this public repository. No paid host is required for this initial scheduled mode.

Eight 1 MHz windows are queued from the measured HIP544 six-scan recording. The original 1380–1381 MHz window is recognized from its complete manifest and is not repeated. Additional windows increase measured frequency coverage, not the count of independent cadences. Once the queue is exhausted, the site says so; continuing science requires more reviewed inputs. The original 100-cadence and 24-hour/50-pair acceptance remain open.

`src/xenia/live/observatory.py` verifies stored artifact hashes and independently compares Parquet verdict counts before recognizing a completed window. It resumes from these records on a fresh machine. The mutable `runs/observatory/status.json` is a convenience view; each processing cycle has its own immutable manifest and checksum-backed receipt. Queue and configuration hashes are recorded. The current pinned detector includes the audited PUB-002 correction; its warnings and source revision are retained in each new result.

A failed window is attempted once per cycle, at most three times. Errors remain visible. A successful retry clears the failure. After three failures, an operator must investigate before explicitly clearing that entry in the status file. Do not delete scientific evidence or label a failed fetch as a null result. An invalid historical checksum stops processing rather than silently trusting corrupt evidence.

## Publication and recovery

The source checkout must be committed before processing. Publication adds only the new cycle's compact evidence and the status view. It refuses unrelated staged or modified tracked files. It never creates a branch, force-pushes or rebases experimental code. A competing main update rejects the push; the local evidence commit remains recoverable. GitHub retains the compact `runs/` artifact for 14 days even if the job fails. Review and recover those artifacts rather than discarding an experiment.

The job builds the public site and documentation before publishing. Following a successful evidence push, it calls the reusable Pages workflow directly: pushes made with `GITHUB_TOKEN` do not trigger another workflow. Ordinary host pushes to `main` that change `runs/` trigger Pages automatically. Pages still serializes deployments and builds from current main. An observation failure makes the processing job fail after its receipt is published, while Pages still publishes that honest status.

The homepage exposes completed, pending and blocked windows, the last processing check, run records and workflow history. It offers a refresh when a newer build is detected and warns after eight hours without a processing check. A static page or completed batch is not a continuous heartbeat.

## Run a bounded pass

```bash
uv sync --locked --all-groups --extra radio --python 3.15.0
uv run --locked python scripts/observatory.py --max-pairs 1
# Review the new receipt, build and inspect the site, then publish:
uv run --locked python scripts/build_public_site.py --output .preview/observatory-review
uv run --locked python scripts/observatory.py --publish-only
```

The queue excludes synthetic data and duplicate windows. Each source file has a 256 MiB transfer cap; six files mean a ceiling of 1.5 GiB per attempted window, before retries. Temporary slices are removed after each search. Raw data is never committed. Hit identifiers now include the frequency window to keep separate windows' URLs distinct.

## Proposed dedicated host

A practical starting allocation is an x86-64 Linux VM with 4 vCPUs, 8 GB RAM and 80 GB SSD, running Ubuntu 24.04 LTS in an EU region. This is a sizing proposal to validate with measured peak memory, CPU and transfer totals, not a throughput guarantee. No GPU, database, public web port, new domain or DNS change is required: the VM processes data; GitHub Pages serves the site.

Proposed provider: [Hetzner Cloud](https://www.hetzner.com/cloud/), subject to account availability and the final console quote. Recommend a **€20/month ceiling** for the CX33 (4 vCPUs, 8 GB RAM, 80 GB SSD). The public EU price checked on 20 October 2026 was €11.15/month including IPv4 and the selected 24% VAT, but the plan was explicitly marked unavailable. This is a proposal, not a reservation. The ceiling leaves room for backups; confirm their final price at checkout.

If CX33 remains unavailable, the smaller CPX22 (2 vCPUs, 4 GB RAM, 80 GB SSD) was listed at €24.79/month with the same tax/IP assumptions: propose a separate **€30/month ceiling**, subject to availability and approval. The larger CPX32 was €44.63/month, so do not silently substitute it under either budget. [Cost-optimized prices](https://www.hetzner.com/cloud/cost-optimized/) · [Regular-performance prices](https://www.hetzner.com/cloud/regular-performance/).

The first additional local window took 334.61 seconds, used a measured 547,962,880-byte maximum resident set (~523 MiB), and transferred 525,817,539 bytes. This supports trying a modest single-worker VM; it is not a Linux benchmark or a whole-archive throughput guarantee. For sustained full-CPU processing, assess a dedicated-vCPU plan instead of assuming a shared VM permits or delivers continuous maximum throughput. Official documentation lists [EU traffic allowances](https://docs.hetzner.com/cloud/billing/faq/); alerts are not a hard spending cap.

Needed from Michael before provisioning:

- Approval of the monthly ceiling and provider/region; account and billing setup in the provider UI.
- An SSH access method or a narrowly scoped cloud-project credential stored locally, never in the repository, Notion or report.
- A repository-scoped publishing credential for the dedicated service account, stored in the host's credential store. Contents write is sufficient for data commits; no root-site access is needed.

`deploy/theoxenia.service`, `deploy/theoxenia.timer` and `deploy/run.sh` prepare a bounded, supervised host worker. They have not been installed on a paid server. See [the operator guide](mission-control-deploy.md) for setup, scheduler handover and recovery requirements.

## Domain independence

`mpetyx/mpetyx.github.io` owns the root site and its `mpetyx.com` custom-domain setting. Theoxenia is a separate project Pages deployment at `/theoxenia/`, inheriting that domain. Updating this repository does not replace the root site's files or change its deployment. Both share the same domain/origin and GitHub Pages infrastructure; a root-domain or DNS change can affect both. No root-site settings or DNS records were changed for this worker.

[GitHub's domain behavior](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/about-custom-domains-and-github-pages) · [Actions token trigger behavior](https://docs.github.com/en/actions/concepts/security/github_token) · [Standard public-repository runners](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
