#!/usr/bin/env bash
# Wigent Uninstaller
set -e

echo ""
echo "🗑  Wigent Uninstaller"
echo ""
read -p "Remove Wigent? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Remove from pipx
if command -v pipx &> /dev/null; then
    if pipx list 2>/dev/null | grep -q "wigent"; then
        pipx uninstall wigent
        echo "✓ Removed from pipx"
    fi
fi

# Remove install dir
if [ -d "$HOME/.wigent" ]; then
    rm -rf "$HOME/.wigent"
    echo "✓ Removed ~/.wigent"
fi

echo ""
echo "✅ Wigent uninstalled!"
echo ""
