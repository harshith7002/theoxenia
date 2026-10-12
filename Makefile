UV ?= uv

.PHONY: install test lint format schemas schemas-check schemas-validate live-build live-dev clean files-check

install:
	$(UV) sync --all-groups --python 3.15.0

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

live-build:
	$(UV) run --locked xenia live build-state --runs tests/fixtures/live --output runs/state.json --demo --experiment-id EXP-030
	$(UV) run --locked xenia schemas validate-state --state runs/state.json --schema schemas/live_state.schema.json
	$(UV) run --locked xenia live render --state runs/state.json --runs tests/fixtures/live --output site --experiment-id EXP-030

live-dev: live-build
	$(UV) run --locked xenia live serve --directory site --port 8080

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	rm -rf site/runs
	rm -f site/index.html site/state.json site/sky.svg site/floor.svg runs/state.json
