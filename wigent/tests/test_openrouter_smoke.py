# ════════════════════════════════════════
# wigent — OpenRouter Smoke Tests
# Role: Quick sanity checks for OpenRouter provider
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Smoke tests for the OpenRouter model provider."""

from __future__ import annotations


def test_openrouter_imports():
    """Smoke: OpenRouter model can be imported."""
    from wigent.models.openrouter_model import OpenRouterModel
    assert OpenRouterModel is not None


def test_openrouter_init():
    """Smoke: OpenRouter model initializes correctly."""
    from wigent.models.openrouter_model import OpenRouterModel
    model = OpenRouterModel(api_key="test-key")
    assert model is not None


def test_openrouter_default_model():
    """Smoke: OpenRouter has correct default model."""
    from wigent.models.openrouter_model import OpenRouterModel
    model = OpenRouterModel(api_key="test-key")
    assert "claude" in model.model_name.lower()


def test_openrouter_custom_model():
    """Smoke: Can specify custom model."""
    from wigent.models.openrouter_model import OpenRouterModel
    model = OpenRouterModel(
        api_key="test-key",
        model_name="qwen/qwen-2.5-coder-32b-instruct",
    )
    assert "qwen" in model.model_name.lower()


def test_openrouter_in_factory():
    """Smoke: Model factory knows about OpenRouter."""
    from wigent.models.model_factory import PROVIDER_CLASSES
    assert "openrouter" in PROVIDER_CLASSES
    from wigent.models.openrouter_model import OpenRouterModel
    assert PROVIDER_CLASSES["openrouter"] is OpenRouterModel


def test_openrouter_in_catalog():
    """Smoke: Provider catalog includes OpenRouter."""
    from wigent.config.models_config import PROVIDER_CONFIGS
    assert "openrouter" in PROVIDER_CONFIGS


def test_openrouter_has_free_models():
    """Smoke: OpenRouter catalog has free models."""
    from wigent.models.openrouter_model import OpenRouterModel
    free_models = [
        k for k in OpenRouterModel.MODEL_INFO
        if ":free" in k
    ]
    assert len(free_models) > 0


def test_openrouter_provider_name():
    """Smoke: PROVIDER_NAME is set correctly."""
    from wigent.models.openrouter_model import OpenRouterModel
    assert OpenRouterModel.PROVIDER_NAME == "openrouter"


__all__: list[str] = []
