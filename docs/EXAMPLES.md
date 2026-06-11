# Wigent Examples

## Basic Usage

### Run a task from the command line

```bash
wigent "Add error handling to the database module"
```

### Run with a specific mode

```bash
wigent --mode coder "Implement the user authentication endpoints"
wigent --mode debugger "Fix the memory leak in the cache layer"
wigent --mode architect "Design the new event-driven architecture"
```

### Run with a specific provider and model

```bash
wigent --provider openai --model o3-mini "Refactor the API routes"
wigent --provider anthropic --model claude-sonnet-4-20250514 "Write tests for the auth module"
```

### Run in a different workspace

```bash
wigent --workspace /path/to/project "Add a CI pipeline"
```

## Interactive REPL

Start the interactive shell:

```bash
wigent
```

Once inside, use slash commands:

```
wigent [orchestrator] ❯ /mode debugger
wigent [debugger] ❯ /model anthropic
wigent [debugger] ❯ What's causing the 500 errors in /api/users?
```

### Available commands

| Command | Description |
|---|---|
| `/mode <name>` | Switch agent mode |
| `/model <provider>` | Switch LLM provider |
| `/clear` | Clear conversation history |
| `/save <name>` | Save session checkpoint |
| `/load <name>` | Load a saved session |
| `/status` | Show current agent state |
| `/history` | Show conversation history |
| `/cost` | Show token usage & cost |
| `/compact` | Summarize conversation to save tokens |
| `/help` | Show all commands |

## Automation

### Non-interactive (single-shot)

```bash
wigent --yes "Run all linters and fix any issues"
```

### With session persistence

```bash
wigent --session my-session "Start working on the login page"
wigent --session my-session "Add password reset flow"
wigent --session my-session "Write tests for login"
```

## Development Workflow

1. **Plan**: `wigent --mode architect "Design the database schema"`
2. **Implement**: `wigent --mode coder "Create the user model and repository"`
3. **Test**: `wigent --mode coder "Write unit tests for the user repository"`
4. **Review**: `wigent --mode reviewer "Review the user repository code"`
5. **Debug**: `wigent --mode debugger "Tests are failing with auth errors"`

## API Usage (Python)

```python
from wigent.core.agent import WigentAgent

agent = WigentAgent(mode="orchestrator", provider="openai")
result = agent.run("Add input validation to the signup form")
print(result["result"])
```

```python
agent = WigentAgent()
agent.chat("What files did you modify?")
agent.chat("Show me the diff")
```

```python
agent.set_mode("coder")
agent.run("Implement the changes we discussed")
```

```python
agent.reset()  # clear conversation, keep mode
```
