# Wigent — AI Coding Agent

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An extensible, multi-provider AI coding agent with memory, safety, and sandbox security.

---

## Features

- **Multi-provider LLM support** — OpenAI, Anthropic, Gemini, Groq, Ollama, Mistral, Cohere, LiteLLM
- **Agent modes** — Orchestrator, Architect, Coder, Debugger, Reviewer
- **Memory system** — Token-budgeted context, session persistence, checkpoints, vector search
- **Safety system** — Approval gates, sandbox enforcement, prompt injection detection, audit logging
- **59+ tools** — File operations, code search, AST analysis, git, bash execution
- **Human-in-the-loop** — Risk-based approvals with Rich terminal UI
- **Sandboxed execution** — Path confinement, command classification, env sanitization

---

## Quick Start

```bash
git clone <repo>
cd wigent
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Configure API keys
cp .env.example .env
# Edit .env with your provider key

# Run a task
python agent.py "Refactor the auth module"
```

---

## Configuration

Settings are managed via `.env` file or environment variables. See `.env.example` for all options.

Key settings:

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
├── cli/              # CLI entry point
├── config/           # Settings, modes, model config
├── core/             # Agent loop, orchestrator, WigentAgent
├── memory/           # Context, sessions, checkpoints, vector store
├── models/           # Provider wrappers (OpenAI, Anthropic, etc.)
├── prompts/          # System prompts per mode
├── safety/           # Approvals, diffs, sandbox, validator
└── tools/            # 59+ tool implementations
```

---

## Phases

| Phase | Tag | What |
|---|---|---|
| 1 | `v0.1.0` | Core agent loop, multi-provider, 5 modes |
| 2 | `v0.2.0` | Tool system: file, search, git, AST, bash |
| 3 | `v0.3.0` | Orchestrator, mode routing, project loading |
| 4 | `v0.4.0` | Memory system: context, sessions, checkpoints, vectors |
| 5 | `v0.5.0` | Safety system: approvals, sandbox, validation, audit |

---

## Safety

All tool execution passes through a multi-layer safety pipeline:

1. **Input validation** — prompt injection detection, path safety
2. **Sandbox** — command classification (BLOCKED / WARN / SAFE), path confinement
3. **Diff viewer** — risk-assessed diffs before file writes
4. **Approval gate** — [y]es/[n]o/[e]xplain with 60s auto-reject
5. **Audit log** — append-only JSONL at `.agent/audit.log`

Set `AUTO_APPROVE=true` in your `.env` to bypass interactive approvals.

---

## Development

```bash
# Install dev deps
pip install -e ".[dev]"

# Run tests
pytest

# Run specific tests
pytest wigent/tests/test_safety_smoke.py -v
pytest wigent/tests/test_memory_integration.py -v
```

---

## License

MIT
