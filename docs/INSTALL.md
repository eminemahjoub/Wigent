# Wigent Installation Guide

## Prerequisites

- Python 3.12+
- git
- An API key for at least one LLM provider (OpenAI, Anthropic, etc.)

## Option 1: Quick Install via Script

```bash
curl -fsSL https://raw.githubusercontent.com/eminemahjoub/Wigent/main/install.sh | bash
```

## Option 2: Manual Install

```bash
git clone https://github.com/eminemahjoub/Wigent.git
cd Wigent
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with your API keys
```

## Option 3: pip Install (from source)

```bash
pip install git+https://github.com/eminemahjoub/Wigent.git
```

## Post-Install

1. **Add to PATH** (if using install.sh):
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

2. **Configure API keys** in `.env`:
   ```env
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. **Verify**:
   ```bash
   wigent --help
   ```

## Updating

```bash
# If installed via install.sh
bash ~/.wigent/update.sh

# Or pull and reinstall
git pull
pip install -e ".[dev]"
```

## Uninstalling

```bash
# If installed via install.sh
bash ~/.wigent/uninstall.sh

# Manual removal
rm -rf ~/.wigent ~/.local/bin/wigent
```

## Troubleshooting

- **`wigent: command not found`** — ensure `~/.local/bin` is in your `PATH`
- **Import errors** — run `pip install -e ".[dev]"` to reinstall dependencies
- **API errors** — verify your `.env` has valid keys and the provider is supported

See [GitHub Issues](https://github.com/eminemahjoub/Wigent/issues) for help.
