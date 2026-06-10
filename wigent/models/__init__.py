# ════════════════════════════════════════
# wigent — Models Package
# Role: LLM provider abstraction layer
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Abstract interface + concrete providers for LLM backends.

Supported providers (planned):
    - OpenAI   (GPT-4o, o1, o3)
    - Anthropic (Claude 3.5 Sonnet, Claude 4)
    - LiteLLM  (generic bridge for 100+ models)
"""

from wigent.models.base import LLMProvider
from wigent.models.registry import ProviderRegistry

__all__ = ["LLMProvider", "ProviderRegistry"]
