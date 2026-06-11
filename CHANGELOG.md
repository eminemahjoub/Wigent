# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2025-06-11

### Added

- 25 mode configuration tests (definitions, lookup, immutability, tool sets)
- 37 tool integration tests (file reader/writer/lister/search, bash, code search, AST, git, schemas, safe path)
- 20 full integration tests (workspace → memory → safety, checkpoints, UI commands, safety pipeline, auto-indexer)
- 36 UI smoke tests (components, commands, CLI args, diff display, completer)
- `docs/ARCHITECTURE.md` — system architecture overview
- `docs/CONTRIBUTING.md` — contribution guide
- `docs/EXAMPLES.md` — usage examples
- `CHANGELOG.md` — this file
- `Makefile` — install, test, lint, format, typecheck, coverage, build, publish

### Changed

- Bumped version to `1.0.0` (stable release)
- `pyproject.toml` — pinned dependencies, added `click` and `prompt-toolkit`, added `[dev]` extras, added tool configs for ruff, black, mypy, pytest
- `wigent/__init__.py` — version bump to `1.0.0`

### Fixed

- `wigent/tools/git_tool.py:_get_repo` — handle `ImportError` when `gitpython` is not installed (was `UnboundLocalError`)
- `wigent/tools/git_tool.py:check_is_git_repo` — same `ImportError` fix
- `wigent/tools/git_tool.py:get_repo_root` — same `ImportError` fix

## [0.6.0] — 2025-06-11

### Added

- Rich CLI UI (Phase 6): 20 Rich UI render methods, ASCII logo, mode emojis, thinking spinner, syntax-highlighted code panels
- 17 slash commands: `/mode`, `/model`, `/clear`, `/save`, `/load`, `/checkpoint`, `/restore`, `/status`, `/history`, `/cost`, `/index`, `/workspace`, `/rules`, `/approve-all`, `/compact`, `/help`, `/exit`
- `prompt-toolkit` REPL with `FileHistory`, `CommandCompleter`, key bindings (Ctrl+C, Ctrl+D, Ctrl+L)
- Click-based CLI argument parser (`--provider`, `--model`, `--mode`, `--session`, `--workspace`, `--no-banner`, `--debug`, `--yes`, `--version`)
- Diff display with risk-based border colors (green/yellow/red)

### Changed

- `wigent/cli/app.py` — integrated all UI components, lazy model import inside `main()`
- Lazy import architecture: `wigent/__init__.py`, `wigent/cli/__init__.py`, `wigent/cli/app.py` — model chain only loads when agent runs, not at import time

### Fixed

- `RuntimeWarning: 'wigent.cli.app' found in sys.modules` — eliminated by lazy import pattern
- Click 8.4.1 stdin hang — uses `make_context()` + `invoke()` API instead of `standalone_mode=True`

## [0.5.5] — 2025-06-09

### Added

- Project context detection and workspace awareness (Phase 5.5)
- Dotenv (.env) configuration
- `wigent/cli/` module structure (pre-Phase-6 groundwork)

### Fixed

- Various workspace path resolution edge cases

## [0.5.0] — 2025-06-07

### Added

- Think-act-observe loop via LangGraph (Phase 5)
- Safety system with 3-layer approval gate (Phase 4)
- Vector store and AutoIndexer
- Memory system with checkpoint/session persistence

## [0.4.0] — 2025-06-05

### Added

- Full tool suite: file reader/writer/lister/search, bash executor, code search, AST analyzer, git tool
- `_safe_path.resolve_path()` sandbox enforcement

## [0.3.0] — 2025-06-03

### Added

- Multi-provider model abstraction (OpenAI, Anthropic, Gemini, Groq, Ollama)
- Provider factory pattern

## [0.2.0] — 2025-06-01

### Added

- Agent mode system (orchestrator, architect, coder, debugger, reviewer)
- Mode-specific system prompts

## [0.1.0] — 2025-05-30

### Added

- Initial project structure
- Basic agent loop
- Configuration system via pydantic-settings
- Workspace detector
