#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/eminemahjoub/Wigent.git"
INSTALL_DIR="${HOME}/.wigent"

echo "==> Cloning Wigent into ${INSTALL_DIR} ..."
git clone --depth=1 "${REPO_URL}" "${INSTALL_DIR}" 2>/dev/null || {
    echo "==> Updating existing clone ..."
    git -C "${INSTALL_DIR}" pull --ff-only
}

cd "${INSTALL_DIR}"

echo "==> Creating Python virtual environment ..."
python3 -m venv venv

echo "==> Installing Wigent ..."
./venv/bin/pip install --quiet -e ".[dev]"

echo "==> Setting up .env ..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "==>   Edit ${INSTALL_DIR}/.env and add your API keys"
fi

echo "==> Adding ~/.local/bin/wigent symlink ..."
mkdir -p "${HOME}/.local/bin"
ln -sf "${INSTALL_DIR}/venv/bin/wigent" "${HOME}/.local/bin/wigent"

echo ""
echo "Wigent installed successfully!"
echo "Make sure ~/.local/bin is in your PATH:"
echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "Run: wigent --help"
