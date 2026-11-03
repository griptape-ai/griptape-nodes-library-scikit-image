"""Compare Images: score how alike two images are and show where they differ."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode
from griptape_nodes_library_scikit_image.params import float_parameter

__all__ = ["CompareImages"]


class CompareImages(ImageNode):
    """Measure the structural similarity (SSIM) of two images.

    Use it to check how far a generated character drifted from its sketch, or how much changed between two versions of a
    page.
    """

    INPUT_TOOLTIP = "The first image."
    OUTPUT_FILENAME = "difference.png"

    def add_settings(self) -> None:
        self.add_image_input("other", "The image to compare with. It is resized to the size of the first.")
        self.add_parameter(
            float_parameter(
                "gain", 3.0, "How bright to draw the differences. Raise it to see small ones.", 0.5, 20.0, 0.5
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
        self.add_image_output("output", "Where the images differ, white where they differ most.", self.OUTPUT_FILENAME)

    def run(self, image: Any) -> None:
        other = self.load_input("other", "Other")
        score, difference = tools.compare_images(image, other, float(self.get_parameter_value("gain") or 3.0))
        self.publish("output", difference)
        self.parameter_output_values["similarity"] = score
