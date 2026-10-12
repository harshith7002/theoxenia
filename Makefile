UV ?= uv

.PHONY: install test lint format schemas schemas-check schemas-validate live-build live-dev live-evidence voyager floor-smoke floor floor-evidence docs clean files-check

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

live-evidence:
	$(UV) run --locked xenia live build-state --runs runs --output runs/state.json --manifest-root runs --experiment-id EXP-030
	$(UV) run --locked xenia schemas validate-state --state runs/state.json --schema schemas/live_state.schema.json
	$(UV) run --locked xenia live render --state runs/state.json --runs runs --output site --manifest-root runs --experiment-id EXP-030

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	rm -rf site/runs
	rm -f site/index.html site/state.json site/sky.svg site/floor.svg runs/state.json
