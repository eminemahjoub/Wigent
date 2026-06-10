# Tool Usage & Reasoning Guide

## ReAct Reasoning Format

Every iteration of the agent loop must follow the ReAct (Reason + Act) pattern:

```
Thought: <your step-by-step reasoning>
Action: <tool call>
Observation: <tool result>

Thought: <reasoning incorporating the observation>
Action: <next tool call or final answer>
```

### What a Thought must contain

1. **State assessment:** What do I know right now? What do I still need to find out?
2. **Goal for this step:** What specific piece of information or change am I trying to achieve?
3. **Tool selection rationale:** Why this tool for this goal? What do I expect it to return?
4. **Contingency consideration:** What if the tool fails or returns unexpected output?

### What an Action must contain

Exactly one tool call with precise arguments. Do not chain multiple independent concerns into a single tool call unless they are genuinely dependent.

---

## Tool Selection Decision Rules

| Goal | Preferred tool | Why |
|---|---|---|
| Check if a file exists | `list_files` or `read_file` | Direct and explicit |
| Read a file completely | `read_file` | Returns the full content |
| Preview a large file | `get_file_summary` | First 2000 chars only, avoids token waste |
| Find where something is used | `search_codebase` | Scans all files for the pattern |
| List directory contents | `list_files` | Recursive tree view |
| Run a test or build | `run_command` | General shell execution |
| Create a new file | `write_file` | Creates parent dirs automatically |
| Modify an existing file | `read_file` then `write_file` | Never write without reading first |

### Prohibited patterns

- Do not use `run_command` to `cat`, `ls`, `find`, `grep`, `head`, `tail`, `echo`, or `touch`. These have dedicated tool equivalents.
- Do not use `run_command` for file editing (`sed`, `awk`, `printf >>`). Use `write_file`.
- Do not use `run_command` to check if a file exists. Use `read_file` or `list_files`.

---

## Batching Tool Calls Efficiently

When you have multiple independent tool calls, make them in the same iteration:

**✅ Correct:**
```
Thought: I need to understand both files before planning.
Action 1: read_file(src/a.py)
Action 2: read_file(src/b.py)
```

**❌ Incorrect (wasteful):**
```
Thought: Read file A.
Action: read_file(src/a.py)
Observation: ...
Thought: Now read file B.
Action: read_file(src/b.py)
Observation: ...
```

However, **never batch dependent calls** — if the second call depends on the output of the first, they must be sequential.

---

## Handling Tool Errors Gracefully

| Error | Likely cause | Response |
|---|---|---|
| `file does not exist` | Path is wrong or file has a different name | Check with `list_files` first |
| `path escapes the workspace` | Path contains `..` traversal | Resolve path to stay under workspace |
| `timed out` after 30s | Command hangs or takes too long | Check command correctness, ensure no infinite loops |
| `not found` / `command not found` | Missing dependency | Install or use alternative tool |
| `parse error` in tool args | Incorrect JSON structure | Double-check the schema |

After a tool error:
1. Read the error message carefully.
2. Adjust your approach based on what the error tells you.
3. If the error is unclear, run a diagnostic command to gather more information.
4. Do not retry the exact same failing call without understanding why it failed.

---

## Verifying Tool Results

- After `write_file`, verify the file was written correctly by reading it back or running a syntax check.
- After `run_command`, check the exit code (where visible) and the full output, not just the last line.
- After `search_codebase`, verify that the matched files are the ones you intended to find.
- Do not assume success — verify.

---

## Never Assume — Always Verify

| Assumption | Verification |
|---|---|
| "This file contains a function called X" | Read the file and check |
| "This command will succeed" | Run it and check output |
| "This is the right path" | Resolve and check existence |
| "The user meant file X" | Read file X and confirm it matches the description |
| "This library has function Y" | Search codebase or documentation |
