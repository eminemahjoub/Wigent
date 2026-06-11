.PHONY: install test lint format typecheck coverage build clean publish

install:
	pip install -e ".[dev]"

test:
	python -m pytest -v

lint:
	ruff check wigent/

format:
	black --check wigent/

format-fix:
	black wigent/

typecheck:
	python -m mypy wigent/

coverage:
	python -m pytest --cov=wigent --cov-report=term --cov-report=html

build:
	python -m build

publish:
	python -m twine upload dist/*

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

all: install lint format typecheck test coverage
