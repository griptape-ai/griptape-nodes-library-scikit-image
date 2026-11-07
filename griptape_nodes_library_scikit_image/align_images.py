"""Align Images: shift an image so it lines up with a reference."""

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
from griptape_nodes_library_scikit_image.node_base import ImageNode, data_url, image_location, open_image
from griptape_nodes_library_scikit_image.params import float_parameter, int_parameter
from griptape_nodes_library_scikit_image.tools import ALIGN_CHOICES, ALIGN_SCALE

__all__ = ["AlignImages"]

logger = logging.getLogger("griptape_nodes")

LIBRARY_NAME = "Griptape Nodes scikit-image Library"
WIDGET_NAME = "AlignImages"
EDITOR = "align_editor"
# The mode and preview size change the alignment, which Python does again when they are released. The gain only changes how
# the widget draws the differences.
SYNCED_PARAMETERS = ["mode", "gain", "preview_size"]
ALIGN_PARAMETERS = {"image_to_align", "reference", "mode", "preview_size"}
DEFAULT_PREVIEW_SIZE = 1024
MIN_PREVIEW_SIZE = 64


def default_widget_value() -> dict[str, Any]:
    """The widget's value: the reference and the aligned image, and the maps of how they differ before and after."""
    return {
        "reference_data": "",
        "aligned_data": "",
        "before_map": "",
        "after_map": "",
        "width": 0,
        "height": 0,
        "before": None,
        "after": None,
        "shift_down": 0.0,
        "shift_right": 0.0,
        "rotation": 0.0,
        "scale": 1.0,
    }


class AlignImages(ImageNode):
    """Line up two scans or photos of the same page that were taken a little off from each other.

    The image is moved to where it best matches the reference. Depending on the mode it can also be turned and scaled. The
    shift, turn and scale are given back as numbers. The widget shows the result against the reference before you run the
    node: wipe between them, flip between them, or see where they differ before and after.
    """

    INPUT_NAME = "image_to_align"
    INPUT_LABEL = "Image to align"
    INPUT_TOOLTIP = "The image to align. It is moved, turned and scaled to line up with the reference."
    OUTPUT_FILENAME = "aligned.png"

    def add_settings(self) -> None:
        self.add_image_input(
            "reference", "The fixed image to line up with. It is never changed. The image is resized to its size."
        )
        self.add_parameter(
            ParameterDict(
                name=EDITOR,
                default_value=default_widget_value(),
                tooltip=(
                    "The aligned image against the reference. Wipe between them, flip between them, or see where they "
                    "differ before and after. It updates when you change an image, the mode, or the preview detail, "
                    "without running the node."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Widget(name=WIDGET_NAME, library=LIBRARY_NAME, synced_parameters=SYNCED_PARAMETERS)},
                ui_options={"display_name": "Align"},
                serializable=False,
            )
        )
        self.add_parameter(
            ParameterString(
                name="mode",
                default_value=ALIGN_SCALE,
                tooltip=(
                    "What the image may do to line up. Shift only slides it. Adding rotate lets it turn, and adding scale "
                    "lets it grow or shrink. It tries each and keeps what matches best, so a pair that only needed a slide "
                    "is not turned."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=ALIGN_CHOICES)},
            )
        )
        self.add_parameter(
            float_parameter(
                "gain",
                3.0,
                "How bright to draw the differences in the widget. Raise it to see small ones. It does not change the result.",
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
                    "The longest side, in pixels, of the copies the widget aligns and compares. Raise it for finer detail "
                    "in the widget, which is slower. The saved image is always aligned at the full size."
                ),
                256,
                2048,
                slider=True,
            )
        )

    def add_outputs(self) -> None:
        self.add_image_output("output", "The image, moved to line up with the reference.", self.OUTPUT_FILENAME)
        for name, tooltip in (
            ("shift_down", "How many pixels the image was moved down."),
            ("shift_right", "How many pixels the image was moved right."),
            ("rotation", "How many degrees the image was turned, about its centre."),
            ("scale", "How much the image was scaled, about its centre. 1 is no change."),
        ):
            self.add_parameter(ParameterFloat(name=name, tooltip=tooltip, allowed_modes={ParameterMode.OUTPUT}))

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
        if initial_setup and param_name in ALIGN_PARAMETERS:
            self._update_widget()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ALIGN_PARAMETERS:
            self._update_widget()
        return super().after_value_set(parameter, value)

    def _update_widget(self) -> None:
        """Align the two images at the preview size and hand the widget the pictures, the maps and the numbers.

        Editing a setting must never fail, so this only logs. With only one image, the widget stays empty.
        """
        try:
            data = default_widget_value()
            first, second = self.get_parameter_value("image_to_align"), self.get_parameter_value("reference")
            if image_location(first) and image_location(second):
                result = tools.align_preview(
                    open_image(image_location(first), "Image to align"),
                    open_image(image_location(second), "Reference"),
                    str(self.get_parameter_value("mode") or ALIGN_SCALE),
                    max(MIN_PREVIEW_SIZE, int(self.get_parameter_value("preview_size") or DEFAULT_PREVIEW_SIZE)),
                )
                data.update(
                    {
                        "reference_data": data_url(result["reference"], "JPEG"),
                        "aligned_data": data_url(result["aligned"], "JPEG"),
                        "before_map": data_url(result["before"][1]),
                        "after_map": data_url(result["after"][1]),
                        "width": result["reference"].width,
                        "height": result["reference"].height,
                        "before": result["before"][0],
                        "after": result["after"][0],
                        **{key: result[key] for key in ("shift_down", "shift_right", "rotation", "scale")},
                    }
                )
            self.parameter_output_values[EDITOR] = data
            self.set_parameter_value(EDITOR, data)
            self.publish_update_to_parameter(EDITOR, data)
        except Exception as e:  # noqa: BLE001
            logger.warning("%s: could not update the alignment: %s", self.name, e)

    def run(self, image: Any) -> None:
        reference = self.load_input("reference", "Reference")
        aligned, down, right, rotation, scale = tools.align_images(
            image, reference, str(self.get_parameter_value("mode") or ALIGN_SCALE)
        )
        self.publish("output", aligned)
        self.parameter_output_values["rotation"] = rotation
        self.parameter_output_values["scale"] = scale
        self.parameter_output_values["shift_down"] = down
        self.parameter_output_values["shift_right"] = right
