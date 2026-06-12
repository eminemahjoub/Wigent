# Role: Development workflow automation for Wigent AI Coding Agent
# Author: Wigent AI
# Version: 1.2.0

.PHONY: help install install-dev test test-ci lint format typecheck coverage coverage-report coverage-view all clean build publish

# =============================================================================
# Configuration
# =============================================================================

PYTHON := python3
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff
BLACK := $(PYTHON) -m black
MYPY := $(PYTHON) -m mypy
BUILD := $(PYTHON) -m build
COVERAGE_THRESHOLD := 80
LINE_LENGTH := 120

# =============================================================================
# Help
# =============================================================================

help:
	@echo "Wigent Development Workflow"
	@echo "========================="
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install production dependencies"
	@echo "  make install-dev   Install development dependencies (includes all tools)"
	@echo ""
	@echo "Development:"
	@echo "  make test          Run tests with coverage (local development)"
	@echo "  make test-ci       Run tests with coverage enforcement (CI/CD)"
	@echo "  make lint          Run ruff linter"
	@echo "  make format        Run black formatter and ruff --fix"
	@echo "  make typecheck     Run mypy static type checker"
	@echo ""
	@echo "Coverage:"
	@echo "  make coverage      Generate coverage report (terminal)"
	@echo "  make coverage-report  Generate HTML coverage report"
	@echo "  make coverage-view    Open HTML coverage report in browser"
	@echo ""
	@echo "Quality Gates:"
	@echo "  make all           Run full pipeline: lint -> format -> typecheck -> test-ci"
	@echo ""
	@echo "Build & Release:"
	@echo "  make build         Build wheel and sdist"
	@echo "  make publish       Publish to PyPI (requires credentials)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean         Remove build artifacts, caches, and generated files"

# =============================================================================
# Installation
# =============================================================================

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev]"
	$(PIP) install -e ".[test]"
	$(PIP) install -e ".[vector]"
	$(PIP) install -e ".[git]"
	@echo "Development dependencies installed. Run 'make all' to verify setup."

# =============================================================================
# Testing
# =============================================================================

test:
	$(PYTEST) -v \
		--cov=wigent \
		--cov-report=term-missing:skip-covered \
		--cov-report=term:skip-covered \
		--no-header \
		-rfEsxX \
		--tb=short \
		--strict-markers \
		--disable-warnings \
		$(PYTEST_ARGS)

test-ci:
	@echo "Running CI test suite with coverage enforcement..."
	$(PYTEST) -v \
		--cov=wigent \
		--cov-report=xml:coverage.xml \
		--cov-report=term-missing:skip-covered \
		--cov-fail-under=$(COVERAGE_THRESHOLD) \
		--no-header \
		-rfEsxX \
		--tb=short \
		--strict-markers \
		--disable-warnings \
		$(PYTEST_ARGS)
	@echo "Coverage threshold $(COVERAGE_THRESHOLD)% passed."

# =============================================================================
# Linting & Formatting
# =============================================================================

lint:
	$(RUFF) check wigent/ tests/ --line-length $(LINE_LENGTH)
	$(RUFF) check wigent/ tests/ --select I --line-length $(LINE_LENGTH)

lint-fix:
	$(RUFF) check wigent/ tests/ --fix --line-length $(LINE_LENGTH)

format:
	$(BLACK) wigent/ tests/ --line-length $(LINE_LENGTH)
	$(RUFF) check wigent/ tests/ --fix --line-length $(LINE_LENGTH)

format-check:
	$(BLACK) wigent/ tests/ --line-length $(LINE_LENGTH) --check
	$(RUFF) check wigent/ tests/ --line-length $(LINE_LENGTH)

# =============================================================================
# Type Checking
# =============================================================================

typecheck:
	$(MYPY) wigent/ \
		--ignore-missing-imports \
		--show-error-codes \
		--pretty \
		--warn-redundant-casts \
		--warn-unused-ignores \
		--warn-return-any \
		--warn-unreachable \
		--strict-equality \
		--strict-optional

# =============================================================================
# Coverage
# =============================================================================

coverage:
	$(PYTEST) --cov=wigent --cov-report=term-missing:skip-covered

coverage-report:
	$(PYTEST) --cov=wigent --cov-report=html:htmlcov --cov-report=term
	@echo "HTML coverage report generated in htmlcov/index.html"

coverage-view:
	@echo "Opening coverage report in browser..."
ifeq ($(shell uname),Darwin)
	@open htmlcov/index.html
else ifeq ($(shell uname),Linux)
	@xdg-open htmlcov/index.html || sensible-browser htmlcov/index.html || echo "Please open htmlcov/index.html manually"
else
	@start htmlcov/index.html || echo "Please open htmlcov/index.html manually"
endif

# =============================================================================
# Quality Gates (Full Pipeline)
# =============================================================================

all: format-check lint typecheck test-ci
	@echo ""
	@echo "All quality gates passed!"
	@echo "   - Formatting: OK"
	@echo "   - Linting: OK"
	@echo "   - Type checking: OK"
	@echo "   - Tests: OK (coverage >= $(COVERAGE_THRESHOLD)%)"

# =============================================================================
# Build & Release
# =============================================================================

build:
	$(BUILD) --wheel --sdist
	@echo "Built artifacts in dist/"

publish:
	@echo "Publishing to PyPI..."
	$(PYTHON) -m twine upload dist/*
	@echo "Published!"

# =============================================================================
# Maintenance
# =============================================================================

clean:
	rm -rf build/ dist/ .eggs/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned build artifacts and caches."

# =============================================================================
# Specialized Targets
# =============================================================================

test-safety:
	$(PYTEST) tests/test_safety*.py -v --no-header

test-property:
	$(PYTEST) tests/test_*property*.py -v --no-header --hypothesis-show-statistics

test-integration:
	$(PYTEST) tests/test_*integration*.py -v --no-header

test-smoke:
	$(PYTEST) tests/test_*smoke*.py -v --no-header

precommit:
	$(BLACK) wigent/ tests/ --line-length $(LINE_LENGTH) --check
	$(RUFF) check wigent/ tests/ --line-length $(LINE_LENGTH)
	$(PYTEST) -x --no-header -q

update-deps:
	$(PIP) install --upgrade -e ".[dev]"
	$(PIP) install --upgrade -e ".[test]"
	$(PIP) install --upgrade -e ".[vector]"
	$(PIP) install --upgrade -e ".[git]"
	@echo "Dependencies updated. Run 'make all' to verify."

requirements:
	$(PIP) freeze > requirements.txt
	$(PIP) freeze --exclude-editable > requirements-lock.txt
	@echo "Requirements exported."
