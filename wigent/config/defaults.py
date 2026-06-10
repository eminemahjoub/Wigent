# ════════════════════════════════════════
# wigent — Default Values
# Role: Central constants and fallback values
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Default configuration values used when environment variables are not set."""

from __future__ import annotations

import os
from typing import Final

# Workspace
DEFAULT_WORKSPACE: Final[str] = os.path.join(os.getcwd(), "agent_workspace")

# LLM defaults
DEFAULT_PROVIDER: Final[str] = "openai"
DEFAULT_MODEL: Final[str] = "gpt-4o"
DEFAULT_MAX_TOKENS: Final[int] = 128_000

# Execution
DEFAULT_COMMAND_TIMEOUT: Final[int] = 30
DEFAULT_SEARCH_TIMEOUT: Final[int] = 15

# Safety
DEFAULT_REQUIRE_APPROVAL: Final[bool] = False

# Logging
DEFAULT_LOG_LEVEL: Final[str] = "INFO"
DEFAULT_LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

# File preview
FILE_SUMMARY_MAX_CHARS: Final[int] = 2000

__all__ = [
    "DEFAULT_WORKSPACE",
    "DEFAULT_PROVIDER",
    "DEFAULT_MODEL",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_COMMAND_TIMEOUT",
    "DEFAULT_SEARCH_TIMEOUT",
    "DEFAULT_REQUIRE_APPROVAL",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOG_FORMAT",
    "FILE_SUMMARY_MAX_CHARS",
]
