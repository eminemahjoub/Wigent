from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text


console = Console()

PROVIDERS = {
    "1": {
        "name": "Local (Ollama)",
        "key": "ollama",
        "description": "Free, offline, auto-installs a small coding model",
        "needs_key": False,
    },
    "2": {
        "name": "OpenAI",
        "key": "openai",
        "description": "GPT-4o, GPT-4, o3-mini — requires API key",
        "needs_key": True,
        "env_var": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "3": {
        "name": "Anthropic",
        "key": "anthropic",
        "description": "Claude Sonnet 4, Claude Opus — requires API key",
        "needs_key": True,
        "env_var": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
    },
    "4": {
        "name": "Google Gemini",
        "key": "gemini",
        "description": "Gemini 2.5 Pro, Gemini 2.0 Flash — requires API key",
        "needs_key": True,
        "env_var": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-pro-exp-03-25",
    },
    "5": {
        "name": "Groq",
        "key": "groq",
        "description": "Fast inference, free tier available — requires API key",
        "needs_key": True,
        "env_var": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
}


SMALL_MODELS = [
    ("qwen2.5-coder:1.5b", "~1 GB", "Best for coding, small footprint"),
    ("deepseek-coder:1.3b", "~800 MB", "Good for code, very lightweight"),
    ("llama3.2:1b", "~700 MB", "Smallest, general purpose"),
]


def print_welcome() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Wigent Setup Wizard[/bold cyan]\n\n"
        "This wizard helps you configure Wigent to work with your\n"
        "preferred LLM provider. Choose a provider below.\n\n"
        "[bold]Local (Ollama)[/bold] is recommended — free, offline, and\n"
        "works out of the box with no API keys needed.",
        border_style="cyan",
    ))
    console.print()


def pick_provider() -> str | None:
    table = Table(box=None, show_header=False)
    table.add_column("Option", style="bold yellow")
    table.add_column("Provider", style="bold")
    table.add_column("Description", style="dim")  

    for key, p in PROVIDERS.items():
        table.add_row(f"[{key}]", p["name"], p["description"])

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "Choose a provider",
        choices=list(PROVIDERS.keys()),
        default="1",
    )

    return PROVIDERS[choice]["key"]


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
    console.print("\n[bold]Installing Ollama...[/bold]")
    console.print("This will download and install Ollama on your system.\n")

    if not Confirm.ask("Install Ollama now?"):
        console.print("[yellow]Skipping Ollama installation.[/yellow]")
        console.print("Install manually: [blue]https://ollama.com/download[/blue]")
        return False

    system = sys.platform
    try:
        if system == "linux":
            console.print("[dim]Running: curl -fsSL https://ollama.com/install.sh | sh[/dim]")
            result = subprocess.run(
                "curl -fsSL https://ollama.com/install.sh | sudo sh",
                shell=True, capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                console.print(f"[red]Install failed: {result.stderr.strip()}[/red]")
                return False
        elif system == "darwin":
            if shutil.which("brew"):
                result = subprocess.run(
                    ["brew", "install", "ollama"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    console.print(f"[red]Install failed: {result.stderr.strip()}[/red]")
                    return False
            else:
                console.print("[yellow]Homebrew not found. Download from: https://ollama.com/download[/yellow]")
                return False
        else:
            console.print("[yellow]Windows not supported for auto-install.[/yellow]")
            console.print("Download from: [blue]https://ollama.com/download[/blue]")
            return False

        console.print("[green]✓ Ollama installed![/green]")
        return True

    except subprocess.TimeoutExpired:
        console.print("[red]Install timed out. Try manually: https://ollama.com/download[/red]")
        return False
    except Exception as exc:
        console.print(f"[red]Install error: {exc}[/red]")
        return False


def start_ollama() -> bool:
    console.print("\n[bold]Starting Ollama service...[/bold]")
    try:
        subprocess.run(
            ["ollama", "serve"],
            capture_output=True, text=True, timeout=3,
        )
        return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["nohup", "ollama", "serve", "&"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import time
            time.sleep(2)
            return True
    except Exception:
        pass

    console.print("[yellow]Could not auto-start Ollama. Start it manually:[/yellow]")
    console.print("  [blue]ollama serve[/blue]")
    return False


def pick_small_model() -> str:
    console.print("\n[bold]Select a local model to download:[/bold]")
    console.print("[dim]Smaller models use less disk/RAM but may be less capable.[/dim]\n")

    table = Table(box=None, show_header=True)
    table.add_column("#", style="bold yellow")
    table.add_column("Model", style="bold")
    table.add_column("Size", style="cyan")
    table.add_column("Note", style="dim")

    for i, (name, size, note) in enumerate(SMALL_MODELS, 1):
        table.add_row(str(i), name, size, note)

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "Which model to download?",
        choices=["1", "2", "3"],
        default="1",
    )

    return SMALL_MODELS[int(choice) - 1][0]


def pull_ollama_model(model: str) -> bool:
    console.print(f"\n[bold]Downloading [cyan]{model}[/cyan]...[/bold]")
    console.print("[dim]This may take a few minutes depending on your internet speed.[/dim]\n")

    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            console.print(f"[red]Failed to download {model}: {result.stderr.strip()}[/red]")
            return False
        console.print(f"[green]✓ {model} downloaded![/green]")
        return True
    except subprocess.TimeoutExpired:
        console.print(f"[red]Download timed out. Try manually: ollama pull {model}[/red]")
        return False
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        return False


def write_env_config(
    provider_key: str,
    model: str | None = None,
    api_key: str | None = None,
) -> Path:
    env_path = Path.cwd() / ".env"

    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    # Remove old provider/model lines
    lines = [l for l in lines if not l.startswith(("DEFAULT_PROVIDER=", "LLM_MODEL=", "OPENAI_API_KEY=", "ANTHROPIC_API_KEY=", "GEMINI_API_KEY=", "GROQ_API_KEY="))]

    lines.append(f"\n# Configured by wigent setup")
    lines.append(f"DEFAULT_PROVIDER={provider_key}")
    if model:
        lines.append(f"LLM_MODEL={model}")
    if api_key:
        lines.append(f"{api_key}")

    # Remove leading blank lines
    while lines and lines[0].strip() == "":
        lines.pop(0)

    env_path.write_text("\n".join(lines) + "\n")
    console.print(f"[green]✓ Config written to {env_path}[/green]")
    return env_path


def setup_ollama() -> None:
    console.print("\n[bold cyan]==> Setting up Ollama (Local)[/bold cyan]\n")

    installed = check_ollama_installed()
    if not installed:
        console.print("[yellow]Ollama is not installed on your system.[/yellow]")
        if not install_ollama():
            console.print("\n[red]Cannot continue without Ollama.[/red]")
            console.print("Install it manually, then run [bold]wigent setup[/bold] again.")
            return
        installed = True

    running = check_ollama_running()
    if not running:
        console.print("[yellow]Ollama is not running.[/yellow]")
        start_ollama()
        import time
        time.sleep(1)
        running = check_ollama_running()

    if not running:
        console.print("[yellow]Could not verify Ollama is running. Continuing anyway...[/yellow]")

    model = pick_small_model()

    if running:
        console.print()
        if Confirm.ask(f"Download [cyan]{model}[/cyan] now?", default=True):
            pull_ollama_model(model)

    write_env_config(provider_key="ollama", model=model)

    console.print()
    console.print(Panel.fit(
        "[bold green]✅ Local setup complete![/bold green]\n\n"
        f"Provider: [cyan]Ollama[/cyan]\n"
        f"Model: [cyan]{model}[/cyan]\n\n"
        "You can now use Wigent from any directory:\n"
        f"  [bold]wigent[/bold]\n\n"
        "To change provider later, run:\n"
        "  [bold]wigent setup[/bold]",
        border_style="green",
    ))


def setup_cloud(provider_key: str) -> None:
    info = next(p for p in PROVIDERS.values() if p["key"] == provider_key)
    console.print(f"\n[bold cyan]==> Setting up {info['name']}[/bold cyan]\n")

    env_var = info["env_var"]
    current_key = os.environ.get(env_var, "")

    if current_key:
        console.print(f"[green]✓ {env_var} already set in environment[/green]")
        use_existing = Confirm.ask(f"Use existing key?", default=True)
        if use_existing:
            write_env_config(provider_key=provider_key, model=info["default_model"])
            _print_cloud_done(info["name"], provider_key, info["default_model"])
            return

    console.print(f"Get your API key from: [blue]https://platform.openai.com/api-keys[/blue]"
                  if provider_key == "openai" else
                  f"Get your API key from: [blue]https://console.anthropic.com/settings/keys[/blue]"
                  if provider_key == "anthropic" else
                  f"Get your API key from: [blue]https://aistudio.google.com/app/apikey[/blue]"
                  if provider_key == "gemini" else
                  f"Get your API key from: [blue]https://console.groq.com/keys[/blue]")
    console.print()

    api_key = Prompt.ask(f"Enter your {info['name']} API key", password=True)

    if not api_key.strip():
        console.print("[red]No API key provided. Setup cancelled.[/red]")
        return

    os.environ[env_var] = api_key
    write_env_config(
        provider_key=provider_key,
        model=info["default_model"],
        api_key=f"{env_var}={api_key}",
    )

    _print_cloud_done(info["name"], provider_key, info["default_model"])


def _print_cloud_done(name: str, provider_key: str, model: str) -> None:
    console.print()
    console.print(Panel.fit(
        f"[bold green]✅ {name} setup complete![/bold green]\n\n"
        f"Provider: [cyan]{name}[/cyan]\n"
        f"Model: [cyan]{model}[/cyan]\n\n"
        "You can now use Wigent from any directory:\n"
        f"  [bold]wigent[/bold]\n\n"
        "To change provider later, run:\n"
        "  [bold]wigent setup[/bold]",
        border_style="green",
    ))


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
