"""Diff Images: score how alike two images are and show where they differ."""

from __future__ import annotations

import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.widget import Widget

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode, browser_url, data_url, image_location, open_image
from griptape_nodes_library_scikit_image.params import float_parameter, int_parameter
from griptape_nodes_library_scikit_image.splitting import CompareView

__all__ = ["DiffImages"]

logger = logging.getLogger("griptape_nodes")

LIBRARY_NAME = "Griptape Nodes scikit-image Library"
WIDGET_NAME = "DiffImages"
EDITOR = "diff_editor"
# The gain, view and wipe position only change how the widget draws what it has, and they are what the node saves. The
# preview size changes what is compared, so Python compares again when it is released.
SYNCED_PARAMETERS = ["gain", "preview_size", "view", "wipe", "heat_colours"]
COMPARE_PARAMETERS = {"image_1", "image_2", "preview_size"}
DEFAULT_PREVIEW_SIZE = 1024
MIN_PREVIEW_SIZE = 64


def default_widget_value() -> dict[str, Any]:
    """The widget's value: both images to show, their size, and the map of where they differ."""
    return {
        "image_url": "",
        "other_url": "",
        "width": 0,
        "height": 0,
        "map_url": "",
        "score": None,
        "message": "",
        "palettes": {
            name: [[position, list(colour)] for position, colour in stops]
            for name, stops in tools.HEAT_PALETTES.items()
        },
        "heat_alpha": tools.HEAT_ALPHA,
    }


class DiffImages(ImageNode):
    """Measure the structural similarity (SSIM) of two images.

    Use it to check how far a generated character drifted from its sketch, or how much changed between two versions of a
    page. The widget lets you wipe between the images, flip between them, and see where they differ, before you run the
    node. The node saves the view the widget is showing.
    """

    INPUT_NAME = "image_1"
    INPUT_LABEL = "Image 1"
    INPUT_TOOLTIP = "The first image."
    OUTPUT_FILENAME = "compare.png"

    def add_settings(self) -> None:
        self.add_image_input("image_2", "The second image. It is resized to the size of the first.")
        self.add_parameter(
            ParameterDict(
                name=EDITOR,
                default_value=default_widget_value(),
                tooltip=(
                    "Wipe between the two images, flip between them, or see where they differ. It updates when you "
                    "change an image or the preview detail, without running the node."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Widget(name=WIDGET_NAME, library=LIBRARY_NAME, synced_parameters=SYNCED_PARAMETERS)},
                ui_options={"display_name": "Diff"},
                serializable=False,
            )
        )
        self.add_parameter(
            ParameterString(
                name="view",
                default_value=CompareView.DIFFERENCE,
                tooltip=(
                    "What the widget shows, and what the node saves. Wipe splits the images at the wipe position. Image 1 and Image 2 "
                    "are the images. Difference is white where they differ. Heat tints the first image red where they "
                    "differ."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=[view.value for view in CompareView])},
            )
        )
        self.add_parameter(
            float_parameter(
                "wipe",
                50.0,
                "Where the Wipe view splits the images, as a percentage of the width. The first image is on the left.",
                0.0,
                100.0,
                0.1,  # the widget rounds the divider to a tenth, and the engine accepts only multiples of the step
                slider=True,
            )
        )
        self.add_parameter(
            ParameterString(
                name="heat_colours",
                default_value=tools.DEFAULT_HEAT_PALETTE,
                tooltip=(
                    "The colours of the Heat view. Spectrum runs from blue through green and yellow to red where the "
                    "images differ most. Fire runs from yellow through orange to red. Red is a single colour."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=list(tools.HEAT_PALETTES))},
            )
        )
        self.add_parameter(
            float_parameter(
                "gain",
                3.0,
                "How bright to draw the differences. Raise it to see small ones.",
                0.5,
                20.0,
                0.1,
                slider=True,
            )
        )
        self.add_parameter(
            int_parameter(
                "preview_size",
                DEFAULT_PREVIEW_SIZE,
                (
                    "The longest side, in pixels, of the copies the widget compares. Raise it for finer detail in the "
                    "widget, which is slower. The saved difference image and the similarity always use the full size."
                ),
                256,
                2048,
                slider=True,
            )
        )

    def add_outputs(self) -> None:
        self.add_parameter(
            ParameterFloat(
                name="similarity",
                tooltip="1 means the images are the same. Lower means they differ more.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_image_output(
            "output", "The view the widget is showing, at the full size of the first image.", self.OUTPUT_FILENAME
        )
        self._show_settings_for_view()

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Work the widget out again while a workflow loads, because loading skips after_value_set."""
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )
        if initial_setup and param_name in COMPARE_PARAMETERS:
            self._update_widget()
        if initial_setup and param_name == "view":
            self._show_settings_for_view()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in COMPARE_PARAMETERS:
            self._update_widget()
        if parameter.name == "view":
            self._show_settings_for_view()
        return super().after_value_set(parameter, value)

    def _show_settings_for_view(self) -> None:
        """Show the wipe position only for Wipe, and the heat colours only for Heat."""
        view = self.get_parameter_value("view")
        for name, shown_for in (("wipe", CompareView.WIPE), ("heat_colours", CompareView.HEAT)):
            parameter = self.get_parameter_by_name(name)
            if parameter is not None:
                parameter.hide = view != shown_for

    def _update_widget(self) -> None:
        """Compare the two images at the preview size and hand the widget both of them and the map of differences.

        Editing a setting must never fail, so this only logs. With only one image, the widget shows it alone.
        """
        try:
            data = default_widget_value()
            first, second = self.get_parameter_value("image_1"), self.get_parameter_value("image_2")
            data["image_url"], data["other_url"] = browser_url(first), browser_url(second)
            if image_location(first):
                image = open_image(image_location(first), "Image 1")
                data["width"], data["height"] = image.size
                if image_location(second):
                    size = int(self.get_parameter_value("preview_size") or DEFAULT_PREVIEW_SIZE)
                    score, difference = tools.compare_preview(
                        image, open_image(image_location(second), "Image 2"), max(MIN_PREVIEW_SIZE, size)
                    )
                    data["map_url"] = data_url(difference)
                    data["score"] = score
            self.parameter_output_values[EDITOR] = data
            self.set_parameter_value(EDITOR, data)
            self.publish_update_to_parameter(EDITOR, data)
        except Exception as e:  # noqa: BLE001
            logger.warning("%s: could not update the comparison: %s", self.name, e)

    def run(self, image: Any) -> None:
        other = self.load_input("image_2", "Image 2")
        score, shown = tools.compare_view(
            image,
            other,
            str(self.get_parameter_value("view") or CompareView.DIFFERENCE),
            float(self.get_parameter_value("gain") or 3.0),
            float(self.get_parameter_value("wipe") if self.get_parameter_value("wipe") is not None else 50.0),
            str(self.get_parameter_value("heat_colours") or tools.DEFAULT_HEAT_PALETTE),
        )
        self.publish("output", shown)
        self.parameter_output_values["similarity"] = score
