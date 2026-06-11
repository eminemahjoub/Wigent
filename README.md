# Wigent — AI Coding Agent

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-177%20passing-brightgreen)](wigent/tests/)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)

An extensible, multi-provider AI coding agent CLI with memory, safety, sandbox security, and a Rich terminal UI.

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
├── cli/              # Rich CLI (click, prompt-toolkit, Rich)
│   ├── app.py        # Entry point, REPL loop
│   ├── cli_args.py   # Argument parser
│   ├── commands.py   # 17 slash commands
│   ├── input_handler.py  # prompt-toolkit REPL
│   ├── ui_components.py  # 20 Rich render methods
│   └── diff_display.py   # Diff visualization
├── config/           # Settings, modes, model config
│   └── modes.py      # 5 AgentModeConfig definitions
├── core/             # Agent loop, orchestrator, workspace
├── memory/           # Conversation, sessions, checkpoints, vectors
├── models/           # Provider wrappers (OpenAI, Anthropic, etc.)
├── prompts/          # System prompts per mode (8 .md files)
├── safety/           # Approvals, sandbox, validator
├── tools/            # 10+ tool modules (50+ schemas)
└── tests/            # 177 tests across 6 test files + 4 test dirs
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

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — System design and component overview
- [Examples](docs/EXAMPLES.md) — CLI and Python API usage examples
- [Contributing](docs/CONTRIBUTING.md) — Development setup and PR process
- [Changelog](CHANGELOG.md) — Release history

---

## License

MIT
