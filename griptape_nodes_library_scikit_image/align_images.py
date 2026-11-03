"""Align Images: shift an image so it lines up with a reference."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode
from griptape_nodes_library_scikit_image.tools import ALIGN_CHOICES, ALIGN_SCALE

__all__ = ["AlignImages"]


class AlignImages(ImageNode):
    """Line up two scans or photos of the same page that were taken a little off from each other.

    The image is moved to where it best matches the reference. Depending on the mode it can also be turned and scaled. The
    shift, turn and scale are given back as numbers.
    """

    INPUT_TOOLTIP = "The image to move."
    OUTPUT_FILENAME = "aligned.png"

    def add_settings(self) -> None:
        self.add_image_input("reference", "The image to line up with. The other image is resized to its size.")
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

    def add_outputs(self) -> None:
        self.add_image_output("output", "The image, moved to line up with the reference.", self.OUTPUT_FILENAME)
        self.add_parameter(
            ParameterFloat(
                name="shift_down",
                tooltip="How many pixels the image was moved down.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            ParameterFloat(
                name="shift_right",
                tooltip="How many pixels the image was moved right.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

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
