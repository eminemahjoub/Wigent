#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${HOME}/.wigent"

if [ ! -d "${INSTALL_DIR}" ]; then
    echo "Wigent is not installed. Run install.sh first."
    exit 1
fi

echo "==> Pulling latest changes ..."
git -C "${INSTALL_DIR}" pull --ff-only

echo "==> Updating dependencies ..."
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade -e "${INSTALL_DIR}[dev]"

echo "Wigent updated successfully."
