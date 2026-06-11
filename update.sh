#!/usr/bin/env bash
# Wigent Updater
set -e

echo ""
echo "🔄 Updating Wigent..."
echo ""

WIGENT_DIR="$HOME/.wigent"

if [ ! -d "$WIGENT_DIR" ]; then
    echo "❌ Wigent not installed"
    echo "Run install.sh first"
    exit 1
fi

# Pull latest
cd "$WIGENT_DIR"
git pull

# Reinstall with pipx
pipx reinstall wigent 2>/dev/null || pipx install -e . --force

# Show version
VERSION=$(wigent --version 2>/dev/null || echo "unknown")
echo ""
echo "✅ Updated to: $VERSION"
echo ""
