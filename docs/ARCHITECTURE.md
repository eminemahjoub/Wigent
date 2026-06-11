# Wigent Architecture

## Overview

Wigent is an autonomous AI coding agent built on a **think-act-observe** loop. It uses LLMs to decompose tasks, execute tools (file I/O, bash, search, git), and iterate until completion.

```
┌─────────────────────────────────────────────────────────┐
│                      CLI (click + Rich)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │cli_args  │  │ app      │  │commands  │  │ ui      │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                     Core                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ agent    │  │ loop     │  │orchstrtr │  │workspace│ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    ▼                  ▼                  ▼
┌────────┐      ┌────────┐         ┌────────┐
│ Tools  │      │ Safety │         │ Memory │
│(10+)   │      │(3-layer│         │(vectors│
│        │      │ gate)  │         │ + msgs)│
└────────┘      └────────┘         └────────┘
```

## Key Components

### 1. Agent (`wigent/core/agent.py`)
Public API: `WigentAgent.run(task)`, `.chat(msg)`, `.set_mode()`, `.set_model()`. Manages lifecycle, mode routing, memory, and safety integration.

### 2. Loop (`wigent/core/loop.py`)
LangGraph-based think-act-observe execution with `_plan_node` → `_act_node` → `_observe_node`. Supports 5 modes with per-mode tool filtering and iteration limits.

### 3. Modes (`wigent/config/modes.py`)
| Mode | Emoji | Tools | Iterations |
|---|---|---|---|
| orchestrator | 🧠 | All | 50 |
| architect | 🏛️ | Read-only + git read | 30 |
| coder | 💻 | Read/write + git | 40 |
| debugger | 🔍 | Read/run + git | 30 |
| reviewer | 👁️ | Read + git read | 20 |

### 4. Tools (`wigent/tools/`)
10+ tool modules: `file_reader`, `file_writer`, `file_lister`, `file_search`, `bash_executor`, `code_search`, `ast_analyzer`, `git_tool`, `tool_schemas`. All paths validated through `_safe_path.resolve_path()` which enforces the workspace sandbox.

### 5. Safety (`wigent/safety/`)
Three-layer approval gate: command validation → sandbox check → user approval prompt.

### 6. Models (`wigent/models/`)
Provider abstraction layer: OpenAI, Anthropic, Gemini, Groq, Ollama, LiteLLM proxy. Model selection via `model_factory`.

### 7. Memory (`wigent/memory/`)
`MemorySystem` facade over conversation history, vector store (via `AutoIndexer`), sessions, and checkpoints.

### 8. CLI (`wigent/cli/`)
- `cli_args.py`: Click argument parser
- `app.py`: Main entry point, REPL loop
- `commands.py`: 17 slash commands (/mode, /model, /clear, /save, ...)
- `input_handler.py`: prompt-toolkit REPL with tab completion
- `ui_components.py`: Rich-based UI (20+ render methods)
- `diff_display.py`: diff visualization with risk color coding

## Data Flow

```
User Input → CLI → WigentAgent.run(task)
  → Orchestrator.analyze_request()     [mode selection]
  → AgentLoop (LangGraph)              [think-act-observe × N]
    → _plan_node: LLM decides next tool
    → _act_node: Execute tool, enforce mode permissions
    → _observe_node: Collect result, check safety
  → User sees result via UI panels
```

## Safety Architecture

1. **Validator**: Checks command strings against blocklist
2. **Sandbox**: Verifies paths stay in workspace
3. **Approval Gate**: Prompts user for risky operations

## Extension Points

- Add a new tool: create module in `wigent/tools/`, add to `TOOL_SCHEMAS`
- Add a new model: create class in `wigent/models/`, register in factory
- Add a new mode: add `AgentModeConfig` in `config/modes.py`, create prompt file
