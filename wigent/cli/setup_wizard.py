from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


console = Console()

# ── Palette ───────────────────────────────────────────────
PRIMARY = "cyan"
SUCCESS = "green"
WARNING = "yellow"
ERROR = "red"
MUTED = "dim"
BOLD_PRIMARY = "bold cyan"

# ── Providers ─────────────────────────────────────────────
PROVIDERS = {
    "1": {
        "name": "Local (Ollama)",
        "key": "ollama",
        "description": "Free, offline, runs locally — no API keys",
        "needs_key": False,
        "icon": "🏠",
    },
    "2": {
        "name": "OpenAI",
        "key": "openai",
        "description": "GPT-4o, o3-mini — requires API key",
        "needs_key": True,
        "env_var": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "icon": "🌐",
    },
    "3": {
        "name": "Anthropic",
        "key": "anthropic",
        "description": "Claude Sonnet 4, Opus — requires API key",
        "needs_key": True,
        "env_var": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
        "icon": "🌐",
    },
    "4": {
        "name": "Google Gemini",
        "key": "gemini",
        "description": "Gemini 2.5 Pro, 2.0 Flash — requires API key",
        "needs_key": True,
        "env_var": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-pro-exp-03-25",
        "icon": "🌐",
    },
    "5": {
        "name": "Groq",
        "key": "groq",
        "description": "Fast inference, free tier — requires API key",
        "needs_key": True,
        "env_var": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "icon": "🌐",
    },
}

SMALL_MODELS = [
    ("qwen2.5-coder:1.5b", "~1 GB", "Best for coding"),
    ("deepseek-coder:1.3b", "~800 MB", "Good for code"),
    ("llama3.2:1b", "~700 MB", "Smallest, general"),
]


# ── UI Helpers ──────────────────────────────────────────
def _header(title: str, step: str = "") -> None:
    """Print a clean section header like OpenCode."""
    console.print()
    if step:
        console.print(f"[dim]{step}[/dim]  [bold]{title}[/bold]")
    else:
        console.print(f"[bold]{title}[/bold]")
    console.print(Rule(style="dim", characters="─"))


def _status(icon: str, message: str, color: str = MUTED) -> None:
    console.print(f"  [{color}]{icon}[/]  {message}")


def _ok(message: str) -> None:
    _status("✓", message, SUCCESS)


def _warn(message: str) -> None:
    _status("⚠", message, WARNING)


def _err(message: str) -> None:
    _status("✗", message, ERROR)


def _info(message: str) -> None:
    _status("ℹ", message, MUTED)


def _panel(content: str | Group, title: str = "", border: str = PRIMARY) -> Panel:
    return Panel(
        content,
        title=title,
        border_style=border,
        padding=(1, 2),
    )


# ── Welcome ───────────────────────────────────────────────
def print_welcome() -> None:
    welcome = Group(
        Align.center(Text("Wigent", style="bold cyan", justify="center")),
        Align.center(Text("AI Coding Agent — Setup", style="dim", justify="center")),
        Text(""),
        Align.center(
            Text("Choose an LLM provider to get started. Local (Ollama) is recommended."),
            vertical="middle",
        ),
    )
    console.print(_panel(welcome, border=PRIMARY))
    console.print()


# ── Provider Selection ────────────────────────────────────
def pick_provider() -> str | None:
    _header("Select Provider", "Step 1/3")

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("", style="bold", width=3)
    table.add_column("Provider", style="bold", width=18)
    table.add_column("Description", style="dim")

    for key, p in PROVIDERS.items():
        marker = "●" if p["key"] == "ollama" else "○"
        table.add_row(
            f"[cyan]{marker}[/] [{key}]",
            f"{p['icon']}  {p['name']}",
            p["description"],
        )

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "  ▸  Choose",
        choices=list(PROVIDERS.keys()),
        default="1",
    )
    console.print()
    return PROVIDERS[choice]["key"]


# ── Ollama ────────────────────────────────────────────────
def check_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def check_ollama_running() -> bool:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_ollama() -> bool:
    _header("Install Ollama", "Step 2/3")
    _info("Ollama will be downloaded and installed on your system.")
    console.print()

    if not Confirm.ask("  ▸  Proceed with installation?", default=True):
        _warn("Skipped Ollama installation")
        console.print("       Manual install: [blue]https://ollama.com/download[/blue]")
        return False

    system = sys.platform
    try:
        with Progress(
            SpinnerColumn(style=PRIMARY),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Installing Ollama...", total=None)

            if system == "linux":
                result = subprocess.run(
                    "curl -fsSL https://ollama.com/install.sh | sudo sh",
                    shell=True, capture_output=True, text=True, timeout=180,
                )
            elif system == "darwin":
                if shutil.which("brew"):
                    result = subprocess.run(
                        ["brew", "install", "ollama"],
                        capture_output=True, text=True, timeout=180,
                    )
                else:
                    _warn("Homebrew not found")
                    console.print("       Download: [blue]https://ollama.com/download[/blue]")
                    return False
            else:
                _warn("Auto-install not supported on Windows")
                console.print("       Download: [blue]https://ollama.com/download[/blue]")
                return False

            progress.stop()
            if result.returncode != 0:
                _err(f"Install failed: {result.stderr.strip()}")
                return False

    except subprocess.TimeoutExpired:
        _err("Install timed out")
        console.print("       Try manually: [blue]https://ollama.com/download[/blue]")
        return False
    except Exception as exc:
        _err(f"Install error: {exc}")
        return False

    _ok("Ollama installed")
    return True


def start_ollama() -> bool:
    _info("Starting Ollama service...")
    try:
        subprocess.run(
            ["ollama", "serve"],
            capture_output=True, text=True, timeout=3,
        )
        return True
    except Exception:
        pass

    try:
        subprocess.run(
            ["nohup", "ollama", "serve", "&"],
            capture_output=True, text=True, timeout=5,
        )
        time.sleep(2)
        return True
    except Exception:
        pass

    _warn("Could not auto-start Ollama")
    console.print("       Start manually: [bold]ollama serve[/bold]")
    return False


def pick_small_model() -> str:
    _header("Select Model", "Step 3/3")

    table = Table(box=None, show_header=False)
    table.add_column("", style="bold cyan", width=4)
    table.add_column("Model", style="bold", width=22)
    table.add_column("Size", style="cyan", width=10)
    table.add_column("Note", style="dim")

    for i, (name, size, note) in enumerate(SMALL_MODELS, 1):
        table.add_row(f"[{i}]", name, size, note)

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "  ▸  Choose model",
        choices=["1", "2", "3"],
        default="1",
    )
    console.print()
    return SMALL_MODELS[int(choice) - 1][0]


def pull_ollama_model(model: str) -> bool:
    _info(f"Pulling [bold]{model}[/bold]...")

    try:
        with Progress(
            SpinnerColumn(style=PRIMARY),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Downloading {model}...", total=None)
            result = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True, text=True, timeout=600,
            )
            progress.stop()

            if result.returncode != 0:
                _err(f"Failed: {result.stderr.strip()}")
                return False

    except subprocess.TimeoutExpired:
        _err("Download timed out")
        console.print(f"       Try: [bold]ollama pull {model}[/bold]")
        return False
    except Exception as exc:
        _err(f"Error: {exc}")
        return False

    _ok(f"{model} ready")
    return True


# ── Config Writer ─────────────────────────────────────────
def write_env_config(
    provider_key: str,
    model: str | None = None,
    api_key: str | None = None,
) -> Path:
    env_path = Path.cwd() / ".env"

    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    lines = [
        l for l in lines
        if not l.startswith((
            "DEFAULT_PROVIDER=", "LLM_MODEL=",
            "OPENAI_API_KEY=", "ANTHROPIC_API_KEY=",
            "GEMINI_API_KEY=", "GROQ_API_KEY=",
        ))
    ]

    lines.append("")
    lines.append("# ── Wigent config ──")
    lines.append(f"DEFAULT_PROVIDER={provider_key}")
    if model:
        lines.append(f"LLM_MODEL={model}")
    if api_key:
        lines.append(f"{api_key}")

    while lines and lines[0].strip() == "":
        lines.pop(0)

    env_path.write_text("\n".join(lines) + "\n")
    _ok(f"Saved to {env_path}")
    return env_path


# ── Ollama Flow ───────────────────────────────────────────
def setup_ollama() -> None:
    installed = check_ollama_installed()
    if not installed:
        if not install_ollama():
            console.print()
            _err("Cannot continue without Ollama")
            console.print("       Run [bold]wigent setup[/bold] again after installing.")
            return
        installed = True
    else:
        _ok("Ollama already installed")

    running = check_ollama_running()
    if not running:
        start_ollama()
        time.sleep(1)
        running = check_ollama_running()

    if running:
        _ok("Ollama service running")
    else:
        _warn("Ollama status unknown — continuing")

    model = pick_small_model()

    if running:
        if Confirm.ask("  ▸  Download model now?", default=True):
            pull_ollama_model(model)
    else:
        _info("Skipping model download — start Ollama first")

    write_env_config(provider_key="ollama", model=model)
    _print_done("Local (Ollama)", "ollama", model)


# ── Cloud Flow ────────────────────────────────────────────
def setup_cloud(provider_key: str) -> None:
    info = next(p for p in PROVIDERS.values() if p["key"] == provider_key)
    _header(f"Configure {info['name']}", "Step 2/3")

    env_var = info["env_var"]
    current_key = os.environ.get(env_var, "")

    if current_key:
        _ok(f"{env_var} found in environment")
        if Confirm.ask("  ▸  Use existing key?", default=True):
            write_env_config(provider_key=provider_key, model=info["default_model"])
            _print_done(info["name"], provider_key, info["default_model"])
            return

    links = {
        "openai": "https://platform.openai.com/api-keys",
        "anthropic": "https://console.anthropic.com/settings/keys",
        "gemini": "https://aistudio.google.com/app/apikey",
        "groq": "https://console.groq.com/keys",
    }
    console.print(f"       Get key: [blue]{links.get(provider_key, '')}[/blue]")
    console.print()

    api_key = Prompt.ask("  ▸  Paste API key", password=True)

    if not api_key.strip():
        _err("No key provided — setup cancelled")
        return

    os.environ[env_var] = api_key
    write_env_config(
        provider_key=provider_key,
        model=info["default_model"],
        api_key=f"{env_var}={api_key}",
    )

    _print_done(info["name"], provider_key, info["default_model"])


# ── Done Screen ─────────────────────────────────────────────
def _print_done(name: str, provider_key: str, model: str) -> None:
    console.print()
    summary = Group(
        Align.center(Text("Setup Complete", style="bold green")),
        Text(""),
        Text(f"  Provider   {name}", style="dim"),
        Text(f"  Model      {model}", style="dim"),
        Text(""),
        Align.center(Text("Run [bold]wigent[/bold] to start", style="cyan")),
    )
    console.print(_panel(summary, border=SUCCESS))


# ── Main ──────────────────────────────────────────────────
def main() -> None:
    print_welcome()
    provider_key = pick_provider()

    if provider_key == "ollama":
        setup_ollama()
    else:
        setup_cloud(provider_key)

    console.print()
    console.print("[dim]Tip: Run [bold]wigent setup[/bold] anytime to reconfigure.[/dim]")
    console.print()


if __name__ == "__main__":
    main()
