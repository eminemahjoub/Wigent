# ════════════════════════════════════════
# wigent — Model Picker Modal
# Role: Choose provider, model, and enter API key from within TUI
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Model/provider picker modal for the Wigent TUI."""

from __future__ import annotations

import os

from textual.screen import ModalScreen
from textual.widgets import OptionList, Button, Static, Input, Label
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive

from wigent.config.models_config import PROVIDER_CONFIGS


class ModelPickerModal(ModalScreen[tuple[str, str, str | None] | None]):
    """Modal to pick provider, model, and optionally API key.

    Returns (provider, model, api_key_or_none) or None on cancel.
    """

    DEFAULT_CSS = """
    ModelPickerModal {
        align: center middle;
    }
    #picker-container {
        width: 90;
        height: auto;
        max-height: 90%;
        background: $surface-darken-1;
        border: thick $primary;
        padding: 1 2;
    }
    #picker-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        height: 1;
        margin-bottom: 1;
    }
    #picker-columns {
        height: 1fr;
    }
    #provider-list {
        width: 35%;
        border: solid $primary-darken-2;
        background: $surface;
    }
    #provider-list:focus {
        border: solid $accent;
    }
    #model-list {
        width: 65%;
        border: solid $primary-darken-2;
        background: $surface;
    }
    #model-list:focus {
        border: solid $accent;
    }
    #api-key-section {
        height: auto;
        margin-top: 1;
        border-top: solid $primary-darken-2;
        padding: 1 0 0 0;
    }
    #api-key-label {
        height: 1;
        color: $text-muted;
    }
    #api-key-input {
        height: 1;
        border: solid $primary-darken-1;
    }
    #api-key-input:focus {
        border: solid $accent;
    }
    #picker-footer {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    """

    selected_provider: reactive[str] = reactive("openrouter")

    def __init__(self, current_provider: str = "", current_model: str = "") -> None:
        super().__init__()
        self._current_provider = current_provider
        self._current_model = current_model
        self._providers = list(PROVIDER_CONFIGS.keys())
        self._provider_names = [PROVIDER_CONFIGS[p].name for p in self._providers]
        if current_provider and current_provider in self._providers:
            self.selected_provider = current_provider
        elif "openrouter" in self._providers:
            self.selected_provider = "openrouter"
        else:
            self.selected_provider = self._providers[0]

    def compose(self) -> None:
        with Vertical(id="picker-container"):
            yield Static("⚙  Model / Provider", id="picker-title")

            with Horizontal(id="picker-columns"):
                provider_labels = [
                    f"{PROVIDER_CONFIGS[p].emoji} {PROVIDER_CONFIGS[p].name}"
                    for p in self._providers
                ]
                yield OptionList(*provider_labels, id="provider-list")
                yield OptionList(id="model-list")

            with Vertical(id="api-key-section"):
                yield Label("API Key (leave blank to use existing):", id="api-key-label")
                yield Input(placeholder="sk-...", password=True, id="api-key-input")

            with Horizontal(id="picker-footer"):
                yield Button("Select", variant="success", id="select-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        try:
            idx = self._providers.index(self.selected_provider)
            self.query_one("#provider-list", OptionList).highlighted = idx
        except ValueError:
            pass
        self._refresh_models()
        self._update_api_key_label()

    def _get_env_key(self, provider: str) -> str:
        cfg = PROVIDER_CONFIGS.get(provider)
        if cfg and cfg.env_key:
            return cfg.env_key
        return f"{provider.upper()}_API_KEY"

    def _update_api_key_label(self) -> None:
        """Update API key label to show which env var is used."""
        env_key = self._get_env_key(self.selected_provider)
        existing = os.environ.get(env_key, "")
        label = self.query_one("#api-key-label", Label)
        if existing:
            label.update(f"API Key ([green]set via {env_key}[/]) — type to override:")
        else:
            label.update(f"API Key ([red]missing {env_key}[/]) — enter below:")

    def _refresh_models(self) -> None:
        try:
            model_list = self.query_one("#model-list", OptionList)
        except Exception:
            return

        model_list.clear_options()

        cfg = PROVIDER_CONFIGS.get(self.selected_provider)
        if not cfg:
            return

        labels = []
        self._model_keys = list(cfg.models)
        for model in cfg.models:
            label = model
            tags = []
            if ":free" in model:
                tags.append("[green]FREE[/]")
                if cfg.name == "openrouter":
                    tags.append("[yellow]⚠ no tools[/]")
            elif model == cfg.default_model:
                tags.append("[cyan]default[/]")
            if tags:
                label = f"{model}  {'  '.join(tags)}"
            labels.append(label)
        model_list.add_options(labels)

        if self._current_provider == self.selected_provider:
            try:
                idx = self._model_keys.index(self._current_model)
                model_list.highlighted = idx
            except ValueError:
                pass

    def watch_selected_provider(self, provider: str) -> None:
        self._refresh_models()
        try:
            self._update_api_key_label()
        except Exception:
            pass

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "provider-list":
            self.selected_provider = self._providers[event.option_index]
        elif event.option_list.id == "model-list":
            model = self._model_keys[event.option_index]
            api_input = self.query_one("#api-key-input", Input)
            api_key = api_input.value.strip() or None
            self.dismiss((self.selected_provider, model, api_key))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "provider-list":
            self.selected_provider = self._providers[event.option_index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-btn":
            model_list = self.query_one("#model-list", OptionList)
            idx = model_list.highlighted
            if idx is not None and 0 <= idx < len(self._model_keys):
                api_input = self.query_one("#api-key-input", Input)
                api_key = api_input.value.strip() or None
                self.dismiss((self.selected_provider, self._model_keys[idx], api_key))
            else:
                self.dismiss(None)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)
