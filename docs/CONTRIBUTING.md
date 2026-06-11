# Contributing to Wigent

## Development Setup

```bash
git clone <repo-url>
cd wigent
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # add your API keys
```

## Commands

```bash
make install    # install with dev deps
make test       # run all tests
make lint       # ruff check
make format     # black format
make typecheck  # mypy
make coverage   # pytest with coverage
make build      # build distribution packages
```

## Code Style

- **Python**: 3.12+ with full type hints
- **Line length**: 120
- **Formatting**: black with double quotes
- **Linting**: ruff (E, F, W, I, N, UP, B, SIM)
- **Type checking**: mypy (non-strict, ignore missing imports)

## Testing

- All tests in `wigent/tests/`
- 170+ tests across unit, integration, and smoke suites
- Run `pytest -v` for verbose output
- Run `pytest -m "not slow"` to skip slow tests
- New tests must bypass `wigent/__init__.py` and import sub-modules directly to avoid triggering the model import chain

## Adding a New Tool

1. Create `wigent/tools/<name>.py` with a public function returning `dict`
2. Add the function signature to `TOOL_SCHEMAS` in `wigent/tools/tool_schemas.py`
3. Use `_safe_path.resolve_path()` for all path arguments
4. Add tests in `wigent/tests/test_tools_integration.py`

## Adding a New Model

1. Create `wigent/models/<name>_model.py` implementing the provider interface
2. Register in `wigent/models/model_factory.py`
3. Add provider option to CLI args in `wigent/cli/cli_args.py`

## Commit Convention

```
<type>(<scope>): <description>

Types: feat, fix, refactor, test, docs, chore, perf, style
Examples:
  feat(cli): add --no-banner flag
  fix(tools): handle ImportError in git_tool._get_repo
  test(modes): add 25 tests for mode config
```

## Pull Request Process

1. Ensure all tests pass: `make test`
2. Run linter and formatter: `make lint && make format`
3. Update docs if adding features
4. Bump version in `pyproject.toml` and `wigent/__init__.py`
