# Contributing to guiproof

## Quick start

```bash
git clone https://github.com/sandeep-alluru/guiproof
cd guiproof
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Running checks

```bash
make test       # full test suite
make lint       # ruff check + format
make typecheck  # mypy
make all        # everything
```

## Branch model

- Branch from `main`
- Name: `fix/`, `feat/`, `docs/`, `chore/`
- One logical change per PR

## PR requirements

- All checks pass (`make all`)
- New behaviour has tests
- `CHANGELOG.md` updated under `[Unreleased]`
- PR title follows [Conventional Commits](https://www.conventionalcommits.org/): `fix:`, `feat:`, `docs:`, `chore:`, `test:`

## Review timeline

PRs reviewed within **5 business days**.
