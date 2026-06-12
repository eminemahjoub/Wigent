# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-06-12

### Added

#### Skill-Based Architecture
- **24 production-grade engineering skills** based on [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
  - Meta: `using-agent-skills` — intent routing and shared operating rules
  - Define (3): `interview-me`, `idea-refine`, `spec-driven-development`
  - Plan (1): `planning-and-task-breakdown`
  - Build (7): `incremental-implementation`, `test-driven-development`, `context-engineering`, `source-driven-development`, `doubt-driven-development`, `frontend-ui-engineering`, `api-and-interface-design`
  - Verify (2): `browser-testing-with-devtools`, `debugging-and-error-recovery`
  - Review (4): `code-review-and-quality`, `code-simplification`, `security-and-hardening`, `performance-optimization`
  - Ship (6): `git-workflow-and-versioning`, `ci-cd-and-automation`, `deprecation-and-migration`, `documentation-and-adrs`, `observability-and-instrumentation`, `shipping-and-launch`
- **Skill router** (`core/skill_router.py`) with LLM-based intent classification
  - Confidence scoring with threshold-based routing (auto-route >=0.7, confirm 0.5-0.7, clarify <0.5)
  - Keyword fallback on LLM failure (exception, invalid JSON, missing fields)
  - Few-shot prompting with conversation history context
  - All 24 skills registered with triggers, phases, and prompt templates
- **Interview mode** (`modes/interview.py`) for structured requirement extraction
  - One-question-at-a-time protocol with max 15 questions
  - Confidence tracking: 10% base + 15% per technology + 10% per constraint/persona
  - Vague answer detection with specific follow-up generation
  - Contradiction detection with -5% penalty and flagging
  - 4-round sequencing: Problem -> Scope -> Deep Dive -> Validation
  - Structured spec output with 8 required sections
- **Ideation mode** (`modes/ideate.py`) for divergent/convergent thinking
  - Round 1: 5 fundamentally different approaches with assumption-breaking
  - Round 2: 3 variations per approach (speed/robustness/delight axes)
  - Round 3: 3 hybrid syntheses combining best elements
  - Weighted scoring: Feasibility 30%, Impact 40%, Speed 20%, Risk 10%
  - Top 3 recommendation with pros/cons and MVP timeline
- **Task planner** (`core/planner.py`) with dependency management
  - LLM-based PRD decomposition into atomic tasks (max effort: M, max dependencies: 5)
  - Kahn's algorithm topological sort for execution ordering
  - Parallel execution group detection for concurrent tasks
  - Mermaid flowchart generation with status-based node coloring
  - Progress tracking with status icons
  - Markdown checklist rendering with acceptance criteria
- **System prompts** for all skills with anti-pattern tables and verification checklists
  - `prompts/interview.md` — 150-line prompt with role definition, protocol, examples
  - `prompts/ideate.md` — 120-line prompt with DIVERGE/CONVERGE phases
  - `prompts/spec.md` — 180-line prompt with 18-section PRD template
- **Task templates** (`templates/task.md`) with Jinja2 macros
  - Master plan rendering with overview, execution order, parallel groups
  - Individual task cards with acceptance criteria checkboxes
  - Progress tracking table with percentage calculations
  - Risk register and dependency visualization
  - Daily standup and sprint summary templates
  - Custom Jinja2 filters: sum_effort, format_effort, status_icon, dependency_chain

#### CI/CD & Quality
- **GitHub Actions CI** (`.github/workflows/ci.yml`) with multi-Python testing
  - Matrix testing across Python 3.10, 3.11, 3.12 on ubuntu-latest
  - pytest with coverage reporting and 80% threshold enforcement
  - Codecov integration with badge reporting
  - 15-minute timeout per job with fail-fast disabled
- **Auto-release workflow** (`.github/workflows/release.yml`) for PyPI publishing
  - Trigger on `v*.*.*` version tags
  - Trusted publishing via OIDC (no hardcoded tokens)
  - GitHub Release with auto-generated notes and artifact attachment
  - Dependency on CI passing via workflow_run trigger
- **Property-based testing** (`tests/test_safety_property.py`) for safety validator
  - `hypothesis` adversarial input generation
  - 7 test properties: never crashes, injection patterns, zero-width chars, Base64, blocked paths, normal code, shell metacharacters
  - 1000 max examples for critical safety paths

#### Testing
- **Skill router tests** (`tests/test_skill_router.py`) — 40+ tests
  - Classification, confidence thresholds, keyword fallback, registry, defaults
  - Parametrized boundary tests (0.95, 0.75, 0.50, 0.49, 0.30)
  - All 24 skills verified routable with correct phases
  - Prompt quality tests: few-shot examples, conversation history, JSON format
  - Performance: <100ms routing, 100+ skill registry
  - Integration scenarios: full workflow routing, mode switching
- **Interview mode tests** (`tests/test_interview_mode.py`) — 35+ tests
  - Confidence calculation: technical details (+15%), constraints (+10%), users (+10%)
  - Vague answer handling: 0% boost + follow-up trigger
  - Question sequencing: 4 rounds, <20 words, single question per turn
  - Spec generation: all 8 sections, confidence score, question count
  - Completion: 95% confidence, 15-question hard limit, user triggers
  - Session persistence: save/resume with state serialization
  - Edge cases: empty input, long answers, special characters, contradictions
- **Planner tests** (`tests/test_planner.py`) — 50+ tests
  - Task validation: effort sizes, acceptance criteria, immutability
  - Plan creation: JSON parsing, invalid JSON, missing fields, cycles
  - Topological sort: dependency respect, independent tasks, deep chains, diamonds
  - Parallel groups: correct grouping, sequential, independent, empty
  - Next task: pending, done skip, blocked, dependency satisfaction
  - Status management: mark_done, mark_blocked, unknown task errors
  - Markdown rendering: all tasks, checkboxes, status icons, dependencies
  - Mermaid rendering: flowchart syntax, nodes, arrows, styles, escaping
  - Edge cases: single task, 10-level chain, diamond pattern, effort calc

### Changed

- **Architect mode** enhanced with spec-driven development PRD generation
  - 18-section PRD template with mandatory anti-requirements
  - Quantified success criteria with metrics, measurements, thresholds
  - Beyonce Rule enforcement: "If you liked it, you should have put a test on it"
- **Mode routing** replaced keyword-based `_MODE_SIGNALS` with skill-based routing
  - Legacy orchestrator preserved for backward compatibility during transition
- **Makefile** enhanced with CI-specific targets and coverage enforcement
  - `test-ci` with --cov-fail-under=80
  - `coverage-report` and `coverage-view` with cross-platform browser opening
  - `format-check`, `lint-fix`, specialized test targets
  - `precommit` for fast local checks, `update-deps` for maintenance

### Security

- **Property-based safety testing** with adversarial input generation
  - Unicode edge cases: zero-width characters, control characters, null bytes
  - Nested injection attempts combining multiple attack vectors
  - Base64-encoded payload detection verification
  - Normal code false-positive prevention
- **Safety validator stress testing** at 1000 examples per critical property

### Deprecated

- Keyword-based `_MODE_SIGNALS` routing in `core/orchestrator.py` — will be removed in v2.0.0
  - Migration path: all modes now register via `config/skills.py`
  - Backward compatibility maintained through skill router fallback

### Fixed

- N/A (no bug fixes in this release — pure feature addition)

### Documentation

- **README.md** updated with:
  - CI status, coverage, PyPI, Python version, license badges
  - Skill count, mode count, safety layers, MCP badges
  - Complete "What's New in v1.2.0" section with all features
  - Updated architecture ASCII tree with 30+ new modules marked
  - Quick start examples for `/interview`, `/ideate`, `/spec`, `/plan`
  - Property-based testing and CI/CD quality gates sections
  - 8-phase roadmap table from Foundation to Ecosystem

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

[1.2.0]: https://github.com/eminemahjoub/Wigent/compare/v1.1.0...v1.2.0
