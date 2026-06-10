"""
agent.py  –  Autonomous AI Coding Agent
========================================

This script implements a fully autonomous coding agent powered by
OpenAI's function‑calling API.  Given a natural‑language task, the
agent enters a think‑act‑observe loop:

  1. It asks the LLM (GPT‑4o) what to do next.
  2. If the LLM requests a tool (write_file / read_file / run_command),
     the tool is executed inside a sandboxed workspace and the
     observation is fed back.
  3. The loop repeats until the LLM delivers a final answer without
     tool calls.

Requirements
────────────
  • Python ≥ 3.9
  • openai  –  pip install openai
  • The environment variable OPENAI_API_KEY must be set.
"""

import os          # operating system interfaces – files, env vars, paths
import json        # serialise / deserialise structured data
import sys         # system‑level operations (e.g. sys.exit)
import subprocess  # spawn & interact with shell commands

from openai import OpenAI  # official OpenAI Python SDK


# ── workspace ────────────────────────────────────────────────────────────
# All generated files / code will be written inside this folder.
WORKSPACE = os.path.join(os.getcwd(), "agent_workspace")
os.makedirs(WORKSPACE, exist_ok=True)


# ── API key guard ────────────────────────────────────────────────────────
if not os.environ.get("OPENAI_API_KEY"):
    print("ERROR: OPENAI_API_KEY environment variable is not set.")
    print("Please export your OpenAI API key and try again.")
    sys.exit(1)

# Initialise the OpenAI client – it reads OPENAI_API_KEY automatically.
client = OpenAI()


# ── tool implementations ────────────────────────────────────────────────

def write_file(path: str, content: str) -> str:
    """Write `content` into a file at `WORKSPACE/path`.  Returns confirmation."""
    full_path = os.path.abspath(os.path.join(WORKSPACE, path))
    # Sandbox escape guard – every file must stay under WORKSPACE.
    if not full_path.startswith(os.path.abspath(WORKSPACE)):
        return "Error: path escapes the workspace."
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Successfully wrote to {path}."


def read_file(path: str) -> str:
    """Return the text content of `WORKSPACE/path`, or an error message."""
    full_path = os.path.abspath(os.path.join(WORKSPACE, path))
    # Sandbox escape guard.
    if not full_path.startswith(os.path.abspath(WORKSPACE)):
        return "Error: path escapes the workspace."
    if not os.path.isfile(full_path):
        return f"Error: file {path} does not exist."
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def run_command(command: str) -> str:
    """Execute `command` inside WORKSPACE and return its combined output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)


def list_files(path: str = ".") -> str:
    """Recursively list files and directories under WORKSPACE/path."""
    target = os.path.abspath(os.path.join(WORKSPACE, path))
    if not target.startswith(os.path.abspath(WORKSPACE)):
        return "Error: path escapes the workspace."
    if not os.path.isdir(target):
        return f"Error: {path} is not a directory."
    lines = []
    for root, dirs, files in os.walk(target):
        rel = os.path.relpath(root, WORKSPACE)
        lines.append(f"📁 {rel}/")
        for f in sorted(files):
            lines.append(f"   📄 {os.path.join(rel, f)}")
    return "\n".join(lines) if lines else "(empty)"


def search_codebase(query: str) -> str:
    """Search for a string across files in the workspace."""
    try:
        result = subprocess.run(
            ["rg", "--heading", "--line-number", query, WORKSPACE],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            # Strip the WORKSPACE prefix from paths for cleaner output.
            out = result.stdout.replace(os.path.abspath(WORKSPACE) + "/", "")
            return out.strip() or f"No matches for '{query}'."
        if result.returncode == 1:
            return f"No matches for '{query}'."
        return result.stderr.strip() or f"rg failed (exit {result.returncode})."
    except FileNotFoundError:
        # Fallback: pure-Python search.
        matches = []
        for root, _, files in os.walk(WORKSPACE):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if query in line:
                                rel = os.path.relpath(fpath, WORKSPACE)
                                matches.append(f"{rel}:{i}: {line.rstrip()}")
                except Exception:
                    pass
        return "\n".join(matches) if matches else f"No matches for '{query}'."
    except Exception as e:
        return str(e)


def get_file_summary(path: str) -> str:
    """Return the first 2000 characters of a file inside the workspace."""
    full_path = os.path.abspath(os.path.join(WORKSPACE, path))
    if not full_path.startswith(os.path.abspath(WORKSPACE)):
        return "Error: path escapes the workspace."
    if not os.path.isfile(full_path):
        return f"Error: file {path} does not exist."
    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read(2000)
    return content


# ── tool schemas (OpenAI function-calling format) ────────────────────────

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Relative file path inside the workspace."},
                    "content": {"type": "string", "description": "Text content to write."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path inside the workspace."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command inside the workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Recursively list files and directories inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default '.')."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Search for a string across all files in the workspace. Uses ripgrep if available, falls back to Python search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "String to search for."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_summary",
            "description": "Read the first 2000 characters of a file. Useful for quickly previewing a file before editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path inside the workspace."},
                },
                "required": ["path"],
            },
        },
    },
]

# Map function names to their Python implementations.
available_functions = {
    "write_file": write_file,
    "read_file": read_file,
    "run_command": run_command,
    "list_files": list_files,
    "search_codebase": search_codebase,
    "get_file_summary": get_file_summary,
}


# ── agent orchestrator ───────────────────────────────────────────────────
def run_agent(user_prompt: str):
    """Autonomous agent loop: plans, acts, observes, repeats until done."""

    # Initial conversation – system instruction + user request.
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert autonomous coding agent. "
                "You have access to a sandbox workspace. "
                "Write code, test it by running shell commands, "
                "read error output, fix bugs, and repeat until "
                "the task is complete. Think step‑by‑step.\n\n"
                "IMPORTANT WORKFLOW:\n"
                "1. First, inspect the workspace with `list_files` "
                "and `search_codebase` to understand what already exists.\n"
                "2. Read relevant files with `read_file` or "
                "`get_file_summary` before editing them.\n"
                "3. Do NOT overwrite unrelated code — only modify "
                "files that are relevant to the task.\n"
                "4. After making changes, test them with `run_command`."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    print(f"🤖 Agent thinking about: '{user_prompt}'...\n")

    while True:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )

        message = response.choices[0].message
        messages.append(message)

        # If the model didn't request any tool, it's delivering the final answer.
        if not message.tool_calls:
            print(message.content)
            break

        # Otherwise, execute every tool call the model made.
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            print(f"🛠️  Agent is using tool: {function_name}({function_args})")

            # Look up and invoke the real Python function.
            func = available_functions[function_name]
            try:
                observation = func(**function_args)
            except Exception as e:
                observation = f"Error executing {function_name}: {e}"

            # Feed the observation back to the model.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": observation,
                }
            )


# ── CLI entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    task = input("What should the agent build? > ")
    run_agent(task)
