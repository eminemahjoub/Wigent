#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${HOME}/.wigent"

if [ -d "${INSTALL_DIR}" ]; then
    echo "==> Removing ${INSTALL_DIR} ..."
    rm -rf "${INSTALL_DIR}"
fi

if [ -L "${HOME}/.local/bin/wigent" ]; then
    echo "==> Removing symlink ~/.local/bin/wigent ..."
    rm -f "${HOME}/.local/bin/wigent"
fi

echo "Wigent uninstalled successfully."
