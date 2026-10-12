# Hardening

`make types` runs a strict type check of the library:

```bash
uv run --locked mypy --strict src/xenia
```

The same command is a step in the quality workflow. A `# type: ignore` comment needs a reason on that line. Third-party modules without type stubs are listed under `[tool.mypy.overrides]` with `ignore_missing_imports`.

## Public-page words

`xenia.text_policy.find_banned_words` is the only scanner. It flags these whole words, in any case: alien, extraterrestrial, candidate, anomaly, mysterious. A longer word that merely contains one of those spellings is not a match.

`scripts/check_banned_words.py` walks `site/templates/` for `.html`, `.j2`, `.md`, and `.txt` files. The pre-commit hook runs that script on every commit. Pass another directory only when a test needs a temporary tree.

## What this page does not do

`.zenodo.json` is prepared for a later archive upload. No release was created and no DOI was requested. Dependabot is set to open a weekly pull request for the `uv` lockfile and for GitHub Actions. This repository has no `requirements.txt`, so a second `pip` ecosystem is not configured. That would look at a manifest this tree does not have.
