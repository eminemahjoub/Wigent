# Repository Analysis Report — Wigent

## 1. File Tree

```
ide agent/
├── agent.py           (12,567 bytes, 323 lines)
├── .gitignore         (1 line — ignores venv/)
├── README.md          (1 line — "# Wigent")
└── venv/              (virtual environment, ignored)
```

**Total source files: 3**

---

## 2. Language & Framework

| Category | Value |
|---|---|
| **Language** | Python 3.12 |
| **Paradigm** | Agentic loop (Think → Act → Observe) |
| **LLM Provider** | OpenAI GPT-4o via `openai` SDK function-calling |
| **Key libs used** | `openai`, `os`, `json`, `subprocess` |
| **Installed but unused** | `langchain`, `langgraph`, `anthropic`, `litellm`, `rich`, `pydantic`, etc. |

---

## 3. Configuration Files

| File | Status | Notes |
|---|---|---|
| `.gitignore` | ✅ Present | Only ignores `venv/` |
| `README.md` | ✅ Present | But essentially empty ("# Wigent") |
| `requirements.txt` / `pyproject.toml` | ❌ Missing | No pinned dependencies |
| `.env` / `.env.example` | ❌ Missing | API key requirement undocumented |
| `ruff.toml` / `.flake8` | ❌ Missing | No linter config |
| `mypy.ini` / `pyrightconfig.json` | ❌ Missing | No type checker config |
| `.github/workflows/` | ❌ Missing | No CI/CD |

---

## 4. Architecture Summary

```
┌──────────────────────────────────────┐
│              CLI (__main__)           │
│  input("What should the agent build?")│
│  → run_agent(prompt)                 │
└──────────┬───────────────────────────┘
           ▼
┌──────────────────────────────────────┐
│           Agent Loop                  │
│  while True:                          │
│    ┌──────┐  ┌──────┐  ┌──────────┐  │
│    │ Think│→ │ Act  │→ │ Observe  │  │
│    │ GPT-4│  │ tool │  │ append   │  │
│    │ +tools│  │ exec │  │ result   │  │
│    └──────┘  └──────┘  └──────────┘  │
│         └── no tool_calls → done     │
└──────────────────────────────────────┘
           │
    ┌──────┼──────┬──────┬──────┐
    ▼      ▼      ▼      ▼      ▼
 write  read  run_cmd  list  search
 file   file           files codebase
    │
    ▼  (sandbox: agent_workspace/)
       path-escape-guarded
```

**Key observations:**
- **Single-file monolith** — all logic (tools, schemas, loop, CLI) in 323 lines
- **No classes** — purely procedural/function-based
- **Model hardcoded** to `"gpt-4o"` as a string literal
- **No streaming** — synchronous round-trips only
- **No conversation management** — `messages` grows unbounded
- **No API error handling** — exceptions crash the agent
- **`venv` has many unused libraries** suggesting aspirational multi-model support that was never implemented

---

## 5. Missing Critical Components

| Category | Gaps |
|---|---|
| **Testing** | No `tests/`, no unit tests, no integration tests, no CI |
| **Packaging** | No `pyproject.toml`, no `requirements.txt`, no version/pins |
| **Code Quality** | No linter, no formatter, no type checker, no pre-commit |
| **Observability** | Uses `print()` with emojis instead of structured logging; no error recovery; no retry logic |
| **Documentation** | README is empty; tool functions have minimal docstrings |
| **Conversation Mgmt** | No token-limit handling; no summarization; `messages` grows forever |
| **Security** | `run_command` uses `shell=True` with no command sanitization; `rg` arg is unescaped |
