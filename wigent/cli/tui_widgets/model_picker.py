# ════════════════════════════════════════
# wigent — Model Picker Modal
# Role: Choose provider and model from within TUI
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Model/provider picker modal for the Wigent TUI."""

from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import OptionList, Button, Static
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive

from wigent.config.models_config import PROVIDER_CONFIGS


class ModelPickerModal(ModalScreen[tuple[str, str] | None]):
    """Modal to pick provider and model. Returns (provider, model) or None."""

    DEFAULT_CSS = """
    ModelPickerModal {
        align: center middle;
    }
    #picker-container {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
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
        border: solid $primary-darken-1;
    }
    #model-list {
        width: 65%;
        border: solid $primary-darken-1;
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

    def _refresh_models(self) -> None:
        model_list = self.query_one("#model-list", OptionList)
        model_list.clear_options()

        cfg = PROVIDER_CONFIGS.get(self.selected_provider)
        if not cfg:
            return

        labels = []
        self._model_keys = list(cfg.models)
        for model in cfg.models:
            label = model
            if ":free" in model:
                label = f"{model}  [green]FREE[/]"
            elif model == cfg.default_model:
                label = f"{model}  [cyan]default[/]"
            labels.append(label)
        model_list.add_options(labels)

        # Highlight current model
        if self._current_provider == self.selected_provider:
            try:
                idx = self._model_keys.index(self._current_model)
                model_list.highlighted = idx
            except ValueError:
                pass

    def watch_selected_provider(self, provider: str) -> None:
        self._refresh_models()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "provider-list":
            self.selected_provider = self._providers[event.option_index]
        elif event.option_list.id == "model-list":
            model = self._model_keys[event.option_index]
            self.dismiss((self.selected_provider, model))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "provider-list":
            self.selected_provider = self._providers[event.option_index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-btn":
            model_list = self.query_one("#model-list", OptionList)
            idx = model_list.highlighted
            if idx is not None and 0 <= idx < len(self._model_keys):
                self.dismiss((self.selected_provider, self._model_keys[idx]))
            else:
                self.dismiss(None)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)
