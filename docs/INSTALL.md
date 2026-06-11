# Wigent Installation Guide

## Prerequisites

- Python 3.11+
- git
- An API key for at least one LLM provider (OpenAI, Anthropic, etc.)

## Option 1: One-line Install (Like Kilo!)

```bash
curl -fsSL https://raw.githubusercontent.com/eminemahjoub/Wigent/main/install.sh | bash
```

**No venv activation needed!** Works from any directory.

## Option 2: Manual Install

```bash
# Install pipx
sudo apt install pipx
pipx ensurepath

# Install wigent
git clone https://github.com/eminemahjoub/Wigent.git
cd Wigent
pipx install -e . --force

# Configure API keys
cp .env.example .env
# Edit .env with your API keys

# Test from anywhere!
cd ~
wigent --version
```

## Option 3: pip Install (from source)

```bash
pip install git+https://github.com/eminemahjoub/Wigent.git
```

## Post-Install

1. **Reload your shell** (if using install.sh):
   ```bash
   source ~/.bashrc
   ```

2. **Configure API keys** in `.env`:
   ```env
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. **Verify** — works from ANY directory:
   ```bash
   cd /tmp
   wigent --help
   ```
   **No venv activation needed!**

## Updating

```bash
# One-line update
curl -fsSL https://raw.githubusercontent.com/eminemahjoub/Wigent/main/update.sh | bash

# Or if installed manually
bash ~/.wigent/update.sh
```

## Uninstalling

```bash
# One-line uninstall
curl -fsSL https://raw.githubusercontent.com/eminemahjoub/Wigent/main/uninstall.sh | bash

# Or if installed manually
bash ~/.wigent/uninstall.sh
```

## Troubleshooting

- **`wigent: command not found`** — run `source ~/.bashrc` or ensure `~/.local/bin` is in your `PATH`
- **Import errors** — run `pipx reinstall wigent` to fix dependencies
- **API errors** — verify your `.env` has valid keys and the provider is supported

See [GitHub Issues](https://github.com/eminemahjoub/Wigent/issues) for help.
