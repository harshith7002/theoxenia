UV ?= uv

.PHONY: install test lint format schemas schemas-check schemas-validate live-build live-dev live-evidence voyager floor-smoke floor floor-evidence cadence cadence-synthetic cadence-synthetic-reduced queue queue-synthetic docs clean files-check

install:
	$(UV) sync --all-groups --extra radio --python 3.15.0

test:
	$(UV) run --locked pytest --cov=xenia --cov-report=term-missing

lint:
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .

format:
	$(UV) run --locked ruff check --fix .
	$(UV) run --locked ruff format .

schemas:
	$(UV) run --locked xenia schemas export

schemas-check:
	$(UV) run --locked xenia schemas export --check

schemas-validate:
	$(UV) run --locked xenia live build-state --runs tests/fixtures/live --output runs/state.json --demo --experiment-id EXP-030
	$(UV) run --locked xenia schemas validate-state --state runs/state.json --schema schemas/live_state.schema.json

files-check:
	$(UV) run --locked python scripts/check_repository_files.py

docs:
	$(UV) run --locked mkdocs build --strict --site-dir /tmp/theoxenia-docs

live-build:
	$(UV) run --locked xenia live build-state --runs tests/fixtures/live --output runs/state.json --demo --experiment-id EXP-030
	$(UV) run --locked xenia schemas validate-state --state runs/state.json --schema schemas/live_state.schema.json
	$(UV) run --locked xenia live render --state runs/state.json --runs tests/fixtures/live --output site --experiment-id EXP-030

live-dev: live-build
	$(UV) run --locked xenia live serve --directory site --port 8080

voyager:
	$(UV) run --locked xenia live hero --voyager

floor-smoke:
	$(UV) run --locked xenia live floor --mode reduced --seed 20261012 --experiment-id EXP-002

floor:
	$(UV) run --locked xenia live floor --mode full --seed 20261012 --experiment-id EXP-002

floor-evidence: floor
	$(UV) run --locked xenia live build-state --runs runs --output runs/state.json --manifest-root runs --experiment-id EXP-030
	$(UV) run --locked xenia schemas validate-state --state runs/state.json --schema schemas/live_state.schema.json
	$(UV) run --locked xenia live render --state runs/state.json --runs runs --output site --manifest-root runs --experiment-id EXP-030

cadence:
	$(UV) run --locked xenia live cadence --experiment-id EXP-003 \
		--cadence-id bl-opendata-63460 \
		--target HIP544 \
		--ra-deg 1.6549208333 \
		--dec-deg 29.0205625 \
		--window 1380.0 1381.0 \
		--sources HIP544 HIP1024 HIP544 HIP114 HIP544 HIP1344 \
		--roles A B A C A D \
		--catalog-md5 \
		b66f9ddb87204955651b45d0c80296c1 \
		6297e6e0d5f7a35f9bc13b693ffc12ce \
		759ed97559ceaebb10b9668b69274768 \
		4e865518c50e98054916d6dee45043e1 \
		8a76c8117c5eb5466f7f3de5f3f9d235 \
		2d1a206e18819aeec1594df5cf6807f9 \
		--catalog-size-bytes \
		15489328869 15489102500 15487221734 15486312975 15488259815 15485972200 \
		--files \
		https://bldata.berkeley.edu/pipeline/AGBT16B_999_13/holding/spliced_blc0001020304050607_guppi_57622_33057_Hip544_0039.gpuspec.0000.h5 \
		https://bldata.berkeley.edu/pipeline/AGBT16B_999_13/holding/spliced_blc0001020304050607_guppi_57622_33396_Hip1024_0040.gpuspec.0000.h5 \
		https://bldata.berkeley.edu/pipeline/AGBT16B_999_13/holding/spliced_blc0001020304050607_guppi_57622_33734_Hip544_0041.gpuspec.0000.h5 \
		https://bldata.berkeley.edu/pipeline/AGBT16B_999_13/holding/spliced_blc0001020304050607_guppi_57622_34076_Hip114_0042.gpuspec.0000.h5 \
		https://bldata.berkeley.edu/pipeline/AGBT16B_999_13/holding/spliced_blc0001020304050607_guppi_57622_34417_Hip544_0043.gpuspec.0000.h5 \
		https://bldata.berkeley.edu/pipeline/AGBT16B_999_13/holding/spliced_blc0001020304050607_guppi_57622_34759_Hip1344_0044.gpuspec.0000.h5

cadence-synthetic:
	$(UV) run --locked xenia live cadence --synthetic --seed 20261012 --experiment-id EXP-004 --known-sources configs/fixtures/exp004_known_sources.yaml

cadence-synthetic-reduced:
	$(UV) run --locked xenia live cadence --synthetic --mode reduced --seed 20261012 --experiment-id EXP-004 --known-sources configs/fixtures/exp004_known_sources.yaml

queue:
	$(UV) run --locked xenia live queue build --config configs/live.yaml --output configs/queue.jsonl --listing tests/fixtures/opendata_cadence_63460.json --cadence-id 63460 --receiver L --limit 200

queue-synthetic:
	$(UV) run --locked xenia live queue build --synthetic --seeds 20261012 --config configs/live.yaml --output configs/queue.synthetic.jsonl --limit 200

live-evidence:
	$(UV) run --locked xenia live build-state --runs runs --output runs/state.json --manifest-root runs --experiment-id EXP-030
	$(UV) run --locked xenia schemas validate-state --state runs/state.json --schema schemas/live_state.schema.json
	$(UV) run --locked xenia live render --state runs/state.json --runs runs --output site --manifest-root runs --experiment-id EXP-030

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	rm -rf site/runs
	rm -f site/index.html site/state.json site/sky.svg site/floor.svg runs/state.json
