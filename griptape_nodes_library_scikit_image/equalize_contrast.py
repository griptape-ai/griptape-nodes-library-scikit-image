"""Equalize Contrast: even out contrast across an image in small regions."""

from __future__ import annotations

from typing import Any

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode
from griptape_nodes_library_scikit_image.params import float_parameter

__all__ = ["EqualizeContrast"]


class EqualizeContrast(ImageNode):
    """Bring out detail in dark and bright parts with adaptive histogram equalization (CLAHE).

    It works on lightness only, so colours stay where they are.
    """

    INPUT_TOOLTIP = "The image to work on."
    OUTPUT_TOOLTIP = "The image with evened-out contrast."
    OUTPUT_FILENAME = "equalized.png"

    def add_settings(self) -> None:
        self.add_parameter(
            float_parameter(
                "clip_limit",
                0.02,
                "How strongly to boost contrast. Higher brings out more detail and more noise.",
                0.005,
                0.1,
                0.005,
            )
        )
        self.add_parameter(
            float_parameter(
                "strength", 1.0, "How much of the effect to apply. 1 is all of it, 0 changes nothing.", 0.0, 1.0, 0.05
            )
        )

    def transform(self, image: Any) -> Any:
        return tools.equalize_contrast(
            image,
            float(self.get_parameter_value("clip_limit") or 0.02),
            float(self.get_parameter_value("strength") or 0.0),
        )
