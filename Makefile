.PHONY: all test smoke lint typecheck fmt clean install

all: lint typecheck test

install:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest tests/ -v --tb=short

smoke:
	python smoke_test.py --verbose

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

fmt:
	ruff format src/ tests/
	ruff check --fix src/ tests/

typecheck:
	mypy src/guiproof/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build *.egg-info
