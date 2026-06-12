# Wigent — AI Coding Agent

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/eminemahjoub/Wigent/ci.yml?label=CI&style=for-the-badge" alt="CI Status">
  <img src="https://img.shields.io/codecov/c/github/eminemahjoub/Wigent?style=for-the-badge" alt="Coverage">
  <img src="https://img.shields.io/pypi/v/wigent?style=for-the-badge" alt="PyPI Version">
  <img src="https://img.shields.io/pypi/pyversions/wigent?style=for-the-badge" alt="Python Versions">
  <img src="https://img.shields.io/github/license/eminemahjoub/Wigent?style=for-the-badge" alt="License">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Skills-24%2F24-brightgreen?style=flat-square" alt="24 Skills">
  <img src="https://img.shields.io/badge/Modes-10%2B-blue?style=flat-square" alt="10+ Modes">
  <img src="https://img.shields.io/badge/Safety-4%20Layers-red?style=flat-square" alt="4 Safety Layers">
  <img src="https://img.shields.io/badge/MCP-Enabled-purple?style=flat-square" alt="MCP">
</p>

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-177%20passing-brightgreen)](wigent/tests/)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)

An extensible, multi-provider AI coding agent CLI with memory, safety, sandbox security, and a Rich terminal UI.

---

## What's New in v1.2.0

### Skill-Based Architecture
Wigent now uses a **24-skill professional engineering framework** based on [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills). Every task routes through the right skill workflow with verification gates.

| Phase | Skills | Slash Commands |
|-------|--------|----------------|
| **Define** | `interview-me`, `idea-refine`, `spec-driven-development` | `/interview`, `/ideate`, `/spec` |
| **Plan** | `planning-and-task-breakdown` | `/plan` |
| **Build** | `incremental-implementation`, `test-driven-development`, `context-engineering`, `source-driven-development`, `doubt-driven-development`, `frontend-ui-engineering`, `api-and-interface-design` | `/build`, `/test`, `/source`, `/doubt` |
| **Verify** | `browser-testing-with-devtools`, `debugging-and-error-recovery` | `/test`, `/debug` |
| **Review** | `code-review-and-quality`, `code-simplification`, `security-and-hardening`, `performance-optimization` | `/review`, `/simplify`, `/security`, `/webperf` |
| **Ship** | `git-workflow-and-versioning`, `ci-cd-and-automation`, `deprecation-and-migration`, `documentation-and-adrs`, `observability-and-instrumentation`, `shipping-and-launch` | `/ship`, `/migrate`, `/docs` |

### LLM-Based Intent Classification
Replaced keyword-based `_MODE_SIGNALS` routing with an **LLM intent classifier** that:
- Maps user input to the right skill with confidence scoring
- Falls back to keyword matching on LLM failure
- Requests user confirmation at medium confidence (0.5-0.7)
- Routes to clarification mode at low confidence (<0.5)

### Interview Mode (`/interview`)
Structured one-question-at-a-time interview that:
- Extracts requirements until 95% confidence
- Tracks confidence with weighted signal detection
- Never accepts vague answers without follow-up
- Outputs a complete, testable specification

### Ideation Mode (`/ideate`)
Divergent/convergent thinking workflow that:
- Generates 5 fundamentally different approaches
- Creates 3 variations per approach (speed/robustness/delight)
- Synthesizes 3 hybrid solutions
- Scores all 23 options with weighted matrix

### Task Planner
Decomposes PRDs into atomic tasks with:
- Dependency graph and topological sort (Kahn's algorithm)
- Parallel execution group detection
- Mermaid flowchart generation
- Progress tracking with status icons

### Enhanced Safety
- **Property-based testing** for the safety validator using `hypothesis`
- Adversarial input generation: Unicode edge cases, nested injections, Base64 payloads
- 4-layer safety pipeline: Input Validation → Sandbox → Approval Gate → Egress Firewall

### CI/CD Pipeline
- GitHub Actions with multi-Python testing (3.10, 3.11, 3.12)
- Coverage enforcement at 80% threshold
- Auto-release to PyPI on version tags
- Codecov integration with badge reporting

---

## Features

- **Multi-provider LLM** — OpenAI, Anthropic, Gemini, Groq, Ollama, LiteLLM proxy
- **5 agent modes** — Orchestrator, Architect, Coder, Debugger, Reviewer
- **Rich CLI** — ASCII banner, syntax-highlighted panels, thinking spinner, progress bars, diff display with risk color coding
- **17 slash commands** — `/mode`, `/model`, `/clear`, `/save`, `/load`, `/checkpoint`, `/restore`, `/status`, `/history`, `/cost`, `/index`, `/workspace`, `/rules`, `/approve-all`, `/compact`, `/help`, `/exit`
- **Interactive REPL** — prompt-toolkit with tab completion, history, key bindings
- **50+ tools** — File I/O, code search, AST analysis, git (read/write), bash execution
- **Memory system** — Conversation history, vector search, session persistence, checkpoints
- **Safety system** — 3-layer approval gate (validator → sandbox → user prompt), audit logging
- **Auto-indexer** — Builds a vector index of the workspace on startup
- **Lazy imports** — Instant startup, model chain loads only when used

---

## 🚀 Quick Install (Works Like Kilo!)

### One-line install:
```bash
curl -fsSL https://raw.githubusercontent.com/eminemahjoub/Wigent/main/install.sh | bash
```

### Then use it ANYWHERE:
```bash
cd ~/your-project
wigent
```

**No venv activation needed!** Works exactly like `kilo`, `npm`, or `git`.

### Update wigent:
```bash
curl -fsSL https://raw.githubusercontent.com/eminemahjoub/Wigent/main/update.sh | bash
```

### Uninstall:
```bash
curl -fsSL https://raw.githubusercontent.com/eminemahjoub/Wigent/main/uninstall.sh | bash
```

### Manual install:
```bash
# Install pipx
sudo apt install pipx
pipx ensurepath

# Install wigent
git clone https://github.com/eminemahjoub/Wigent.git
cd Wigent
pipx install -e . --force

# Test from anywhere!
cd ~
wigent --version
```

---

### Quick Start with New Features

```bash
# Start an interview to extract requirements
wigent /interview
# → What problem are you trying to solve?

# Explore ideas before committing
wigent /ideate "Build a real-time chat app"
# → 5 approaches, 15 variations, 3 hybrids, scored

# Generate a PRD from interview output
wigent /spec
# → Complete PRD with testable requirements

# Break PRD into atomic tasks
wigent /plan
# → Dependency graph with parallel execution groups
```

---

## CLI Usage

```bash
wigent [OPTIONS] [PROMPT]

Options:
  -p, --provider TEXT      LLM provider (openai, anthropic, gemini, groq,
                           ollama, litellm, mistral, cohere)
  -m, --model TEXT         Model name (e.g. gpt-4o, claude-sonnet-4-20250514)
  --mode TEXT              Agent mode (orchestrator, architect, coder,
                           debugger, reviewer)
  -s, --session TEXT       Session name for persistence
  -w, --workspace TEXT     Workspace directory
  --no-banner              Skip the ASCII logo on startup
  -d, --debug              Enable debug logging
  -y, --yes                Auto-approve all operations
  --version                Show version
  --help                   Show this help

Examples:
  wigent --mode coder "Add input validation"
  wigent --provider anthropic --model claude-sonnet-4-20250514 "Write tests"
  wigent --session my-work "Fix the login bug"
  wigent --no-banner --yes "Run linters across the project"
```

### Interactive Commands

| Command | Description |
|---|---|
| `/mode <name>` | Switch agent mode |
| `/model <provider>` | Switch LLM provider |
| `/clear` | Clear conversation history |
| `/save <name>` | Save session checkpoint |
| `/load <name>` | Load a saved session |
| `/checkpoint` | Create a checkpoint |
| `/restore` | Restore last checkpoint |
| `/status` | Show current agent state |
| `/history` | Show conversation history |
| `/cost` | Show token usage & cost |
| `/index` | Show workspace index stats |
| `/workspace` | Show workspace info |
| `/rules` | Show agent rules |
| `/approve-all` | Approve all pending operations |
| `/compact` | Summarize conversation to save tokens |
| `/help` | Show all commands |
| `/exit` | Exit the REPL |

---

## Configuration

Settings via `.env` or environment variables. See `.env.example` for all options.

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_PROVIDER` | `openai` | LLM provider |
| `DEFAULT_MODE` | `orchestrator` | Agent mode |
| `AUTO_APPROVE` | `false` | Skip human approvals |
| `SANDBOX_MODE` | `true` | Restrict file ops to workspace |
| `MAX_CONTEXT_TOKENS` | `128000` | Context window limit |
| `WORKSPACE_DIR` | `./agent_workspace` | Sandbox root |

---

## Architecture

```
wigent/
├── skills/                    # 24 production-grade engineering skills
│   ├── meta/
│   │   └── using-agent-skills/
│   ├── define/                # interview-me, idea-refine, spec-driven-development
│   ├── plan/                  # planning-and-task-breakdown
│   ├── build/                 # 7 implementation skills
│   ├── verify/                # browser-testing, debugging
│   ├── review/                # 4 quality skills
│   └── ship/                  # 6 deployment skills
├── agents/                    # Multi-agent orchestration (Phase 6)
│   ├── orchestrator.py
│   └── workers/
├── core/                      # Engine
│   ├── agent.py               # Public API facade
│   ├── skill_router.py        # LLM-based intent classification ⭐ NEW
│   ├── planner.py             # Task decomposition & dependency management ⭐ NEW
│   ├── slice_engine.py        # Incremental implementation
│   ├── context_packer.py      # Smart context engineering
│   ├── doubt_engine.py        # Adversarial self-review
│   ├── orchestrator.py        # Mode routing (legacy, being replaced)
│   └── loop.py                # LangGraph StateGraph
├── modes/                     # Agent personas
│   ├── interview.py           # ⭐ NEW
│   ├── ideate.py              # ⭐ NEW
│   ├── architect.py
│   ├── coder.py
│   ├── debugger.py
│   ├── reviewer.py
│   ├── frontend.py            # ⭐ NEW
│   ├── api.py                 # ⭐ NEW
│   ├── simplify.py            # ⭐ NEW
│   ├── perf.py                # ⭐ NEW
│   ├── devops.py              # ⭐ NEW
│   ├── migrate.py             # ⭐ NEW
│   ├── docs.py                # ⭐ NEW
│   └── ship.py                # ⭐ NEW
├── memory/                    # Context & persistence
│   ├── conversation.py
│   ├── vector_store.py
│   ├── checkpoint_store.py    # ⭐ NEW
│   ├── context_window.py      # ⭐ NEW
│   └── llm_cache.py           # ⭐ NEW
├── safety/                    # 4-layer defense
│   ├── validator.py           # Prompt injection detection
│   ├── sandbox.py             # Path confinement
│   ├── approvals.py           # Risk-based gating
│   ├── egress.py              # Network firewall ⭐ NEW
│   ├── owasp_scanner.py       # ⭐ NEW
│   └── secret_scanner.py      # ⭐ NEW
├── tools/                     # 80+ tools
│   ├── source_fetcher.py      # ⭐ NEW
│   ├── test_generator.py      # ⭐ NEW
│   ├── a11y_checker.py        # ⭐ NEW
│   ├── openapi_gen.py         # ⭐ NEW
│   ├── browser_mcp.py         # ⭐ NEW
│   ├── complexity_analyzer.py # ⭐ NEW
│   ├── profiler.py            # ⭐ NEW
│   ├── ci_generator.py        # ⭐ NEW
│   ├── deprecation_analyzer.py# ⭐ NEW
│   ├── adr_generator.py       # ⭐ NEW
│   ├── observability.py       # ⭐ NEW
│   └── launch_checklist.py    # ⭐ NEW
├── models/                    # LLM provider abstraction
│   ├── base_model.py
│   ├── openai_model.py
│   ├── anthropic_model.py
│   ├── gemini_model.py
│   ├── groq_model.py
│   ├── ollama_model.py
│   ├── litellm_model.py
│   ├── openrouter_model.py
│   └── model_factory.py
├── prompts/                   # System prompts
│   ├── interview.md           # ⭐ NEW
│   ├── ideate.md              # ⭐ NEW
│   ├── spec.md                # ⭐ NEW
│   └── ...
├── templates/                 # Output templates
│   ├── task.md                # ⭐ NEW
│   └── prd.md                 # ⭐ NEW
├── eval/                      # Evaluation framework (Phase 7)
├── learning/                  # Self-improvement (Phase 7)
├── observability/             # Monitoring (Phase 7)
├── auth/                      # Enterprise governance (Phase 7)
├── web/                       # Dashboard (Phase 7)
├── ide/                       # IDE extensions (Phase 8)
├── marketplace/               # Plugin ecosystem (Phase 8)
├── cli/                       # Terminal interface
│   ├── cli_args.py
│   ├── repl.py
│   └── tui_app.py
├── config/                    # Configuration
│   ├── settings.py
│   ├── modes.py
│   └── skills.py              # ⭐ NEW
└── tests/                     # 177+ tests
    ├── test_skill_router.py   # ⭐ NEW
    ├── test_interview_mode.py # ⭐ NEW
    ├── test_planner.py        # ⭐ NEW
    └── test_safety_property.py# ⭐ NEW
```

---

## Agent Modes

| Mode | Emoji | Description | Tools | Max Iterations |
|---|---|---|---|---|
| orchestrator | 🧠 | Full autonomy — analyzes, codes, tests | All | 50 |
| architect | 🏛️ | Planning-only, no code writes | Read + git read | 30 |
| coder | 💻 | Implementation, tests, fixes | Read/write + git | 40 |
| debugger | 🔍 | Bug diagnosis, minimal fixes | Read/run + git | 30 |
| reviewer | 👁️ | Code review, no modifications | Read + git read | 20 |

---

## Safety

All tool execution passes through a multi-layer safety pipeline:

1. **Input validation** — command blocklist, path safety
2. **Sandbox** — path confinement to workspace, env sanitization
3. **Approval gate** — risk-based prompts ([y]es/[n]o/[e]xplain)
4. **Audit log** — append-only JSONL at `.agent/audit.log`

Set `AUTO_APPROVE=true` in `.env` to bypass interactive approvals.

### Property-Based Testing

The safety validator is stress-tested with `hypothesis` generating:
- Random Unicode strings (including zero-width characters)
- Nested injection attempts
- Base64-encoded payloads
- Control characters and null bytes
- Adversarial combinations of all above

Run: `make test-property`

---

## Development

```bash
make install      # Install with dev deps
make test         # Run all 177 tests
make lint         # ruff check
make format       # black check
make format-fix   # black format
make typecheck    # mypy
make coverage     # pytest with coverage report
make build        # Build distribution packages
make clean        # Remove build artifacts
```

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for detailed guidelines.

### CI/CD Quality Gates

Every PR must pass:
1. **Format check**: `black --check` + `ruff`
2. **Type check**: `mypy --strict`
3. **Lint**: `ruff` with import sorting
4. **Tests**: `pytest` with >=80% coverage
5. **Property tests**: `hypothesis` adversarial inputs

Run locally: `make all`
Run in CI: `make test-ci`

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — System design and component overview
- [Examples](docs/EXAMPLES.md) — CLI and Python API usage examples
- [Contributing](docs/CONTRIBUTING.md) — Development setup and PR process
- [Changelog](CHANGELOG.md) — Release history

---

## License

MIT

---

## Roadmap

| Phase | Timeline | Status | Key Deliverables |
|-------|----------|--------|------------------|
| **Phase 1: Foundation** | Jun 2026 | ✅ Complete | CI/CD, skill router, interview, ideate, spec, plan |
| **Phase 2: Build Engine** | Jul 2026 | 🔄 In Progress | Incremental implementation, TDD, context engineering, doubt-driven dev |
| **Phase 3: Verify Engine** | Jul 2026 | ⏳ Planned | Browser testing, debugging & error recovery |
| **Phase 4: Review Engine** | Aug 2026 | ⏳ Planned | Code review, simplification, security, performance |
| **Phase 5: Ship Engine** | Aug 2026 | ⏳ Planned | Git workflow, CI/CD, docs, observability, shipping |
| **Phase 6: Multi-Agent** | Sep 2026 | ⏳ Planned | Orchestrator, worker agents, parallel execution |
| **Phase 7: Advanced** | Oct 2026 | ⏳ Planned | Cost intelligence, long-running sessions, self-improvement |
| **Phase 8: Ecosystem** | Nov 2026 | ⏳ Planned | VS Code extension, JetBrains plugin, marketplace, cloud |
