"""Boiling Lines: frames of one drawing, each wobbled a little differently, like a hand redrawing it."""

from __future__ import annotations

import math
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.traits.slider import Slider
from griptape_nodes.traits.widget import Widget

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import FramesNode, browser_url, image_location, open_image
from griptape_nodes_library_scikit_image.splitting import MAX_BOIL_FRAMES

__all__ = ["BoilingLines"]

LIBRARY_NAME = "Griptape Nodes scikit-image Library"
WIDGET_NAME = "BoilingLines"

# The settings that are both parameters of the node and in the widget's dict, with their default, range and label.
SETTINGS = {
    "frame_count": (8, 2, MAX_BOIL_FRAMES, "Frames"),
    "amplitude": (0.3, 0.02, 5.0, "Amount"),
    "wobble_size": (2.0, 0.3, 20.0, "Wobble size"),
    "seed": (1, 0, 100000, "Seed"),
}
WIDGET_ONLY = {"image_url": "", "width": 0, "height": 0, "frame": 1, "view": "result", "fps": 12}


def default_widget_dict() -> dict[str, Any]:
    return {**WIDGET_ONLY, **{key: default for key, (default, _low, _high, _label) in SETTINGS.items()}}


def same(first: Any, second: Any) -> bool:
    """Whether two setting values are the same number, allowing for float rounding."""
    try:
        return math.isclose(float(first), float(second), rel_tol=1e-9, abs_tol=1e-9)
    except (TypeError, ValueError):
        return False


class BoilingLines(FramesNode):
    """Give a still drawing the shimmer of hand-drawn animation.

    Each frame warps the whole drawing by a smooth random wobble. The widget shows the wobble on your image before you
    run the node: scrub through the frames, play them, look at the noise itself, and change the settings. The settings
    are also parameters of the node, so they can be set on it or by a connection. Play the saved frames at 6 to 12 per
    second for the classic boiling-line look. The same seed gives the same frames.
    """

    DIRNAME = "boil"
    INPUT_TOOLTIP = "The drawing to wobble. A transparent PNG keeps its transparency."

    def add_inputs(self) -> None:
        self.add_parameter(
            ParameterDict(
                name="boil",
                default_value=default_widget_dict(),
                tooltip=(
                    "A live preview of the wobble. Play and scrub the frames, switch to the noise, and change the settings. "
                    "The same noise makes the saved frames."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Widget(name=WIDGET_NAME, library=LIBRARY_NAME)},
            )
        )
        with ParameterGroup(name="boil_settings", ui_options={"display_name": "Boil settings"}) as group:
            ParameterInt(
                name="frame_count",
                default_value=SETTINGS["frame_count"][0],
                tooltip="How many frames to make.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Slider(min_val=SETTINGS["frame_count"][1], max_val=SETTINGS["frame_count"][2])},
            )
            ParameterFloat(
                name="amplitude",
                default_value=SETTINGS["amplitude"][0],
                tooltip=(
                    "How far the lines move, at most, as a percentage of the image's longer side. Small values read as "
                    "a shimmer."
                ),
                step=0.01,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Slider(min_val=SETTINGS["amplitude"][1], max_val=SETTINGS["amplitude"][2])},
                ui_options={"display_name": "Amount"},
            )
            ParameterFloat(
                name="wobble_size",
                default_value=SETTINGS["wobble_size"][0],
                tooltip=(
                    "How big the wobbles are, as a percentage of the image's longer side. Small is jittery, large is wavy."
                ),
                step=0.05,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Slider(min_val=SETTINGS["wobble_size"][1], max_val=SETTINGS["wobble_size"][2])},
            )
            ParameterInt(
                name="seed",
                default_value=SETTINGS["seed"][0],
                tooltip="The same seed gives the same wobble. Change it for a different take.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Slider(min_val=SETTINGS["seed"][1], max_val=SETTINGS["seed"][2])},
            )
        self.add_node_element(group)

    # ── widget and parameters stay in step ────────────────────────────────────

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "image":
            self._show_image_in_widget(value)
        elif parameter.name == "boil":
            if isinstance(value, dict):
                self._widget_to_parameters(value)
        elif parameter.name in SETTINGS:
            self._parameter_to_widget(parameter.name, value)
        return super().after_value_set(parameter, value)

    def _widget_dict(self) -> dict[str, Any]:
        current = self.get_parameter_value("boil")
        return dict(current) if isinstance(current, dict) else default_widget_dict()

    def _push_widget(self, data: dict[str, Any]) -> None:
        self.parameter_output_values["boil"] = data
        self.set_parameter_value("boil", data)
        self.publish_update_to_parameter("boil", data)

    def _show_image_in_widget(self, value: Any) -> None:
        """Hand the widget a URL for the image and its size, with the settings the node has."""
        url = browser_url(value)
        width = height = 0
        location = image_location(value)
        if location:
            try:
                width, height = open_image(location, "Image").size
            except Exception:  # noqa: BLE001
                width = height = 0
        data = self._widget_dict()
        if (data.get("image_url"), data.get("width"), data.get("height")) == (url, width, height):
            return
        data.update({"image_url": url, "width": width, "height": height})
        for key in SETTINGS:
            if self.get_parameter_value(key) is not None:
                data[key] = self.get_parameter_value(key)
        self._push_widget(data)

    def _parameter_to_widget(self, name: str, value: Any) -> None:
        """One parameter changed: show its new value in the widget, and only that value. Nothing is sent if the widget
        already has it. Updating just the one setting matters when the widget's dict is being copied onto the parameters
        one at a time, because the others have not been set yet and would put old values back into the widget."""
        data = self._widget_dict()
        if value is None or same(data.get(name), value):
            return
        data[name] = value
        self._push_widget(data)

    def _widget_to_parameters(self, widget_dict: dict[str, Any]) -> None:
        """The widget changed: set the parameters that differ. The widget's value goes out first, so that it is the one the
        editor holds when the parameter updates make it redraw the node, and the widget does not snap back."""
        changes: dict[str, Any] = {}
        for key, (default, _low, _high, _label) in SETTINGS.items():
            if key not in widget_dict:
                continue
            try:
                number = float(widget_dict[key])
            except (TypeError, ValueError):
                continue
            number = int(round(number)) if isinstance(default, int) else number
            if not same(number, self.get_parameter_value(key)):
                changes[key] = number
        if not changes:
            return
        self.publish_update_to_parameter("boil", widget_dict)
        for key, number in changes.items():
            self.set_parameter_value(key, number)
            self.publish_update_to_parameter(key, number)

    # ── running ───────────────────────────────────────────────────────────────

    def settings(self) -> dict[str, Any]:
        """The settings of the node, with anything missing or out of range replaced by the default."""
        result: dict[str, Any] = {}
        for key, (default, low, high, _label) in SETTINGS.items():
            try:
                number = float(self.get_parameter_value(key))
            except (TypeError, ValueError):
                number = float(default)
            number = number if low <= number <= high else float(default)
            result[key] = int(round(number)) if isinstance(default, int) else number
        return result

    def check_settings(self) -> list[str]:
        problems = []
        for key, (_default, low, high, label) in SETTINGS.items():
            raw = self.get_parameter_value(key)
            try:
                number = float(raw)
            except (TypeError, ValueError):
                problems.append(f"'{label}' must be a number. It's set to {raw!r}.")
                continue
            if not low <= number <= high:
                problems.append(f"'{label}' must be between {low:g} and {high:g}. It's set to {number:g}.")
        return problems

    def render(self, image: Any) -> list[Any]:
        settings = self.settings()
        return tools.boiling_frames(
            image, settings["frame_count"], settings["amplitude"], settings["wobble_size"], settings["seed"]
        )
