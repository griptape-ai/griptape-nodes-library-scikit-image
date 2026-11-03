"""Flatten Paper: take the shadows and gradients out of a photo or scan so the paper is even and white."""

from __future__ import annotations

from typing import Any

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode
from griptape_nodes_library_scikit_image.params import float_parameter

__all__ = ["FlattenPaper"]


class FlattenPaper(ImageNode):
    """Even out the light on a photo or scan of a drawing.

    The colour of the paper is estimated as a smooth surface across the image and divided out, so a shadow or a gradient
    goes away and the paper turns white. The drawing keeps its own colours.
    """

    INPUT_TOOLTIP = "The photo or scan to flatten."
    OUTPUT_TOOLTIP = "The image with even light and white paper."
    OUTPUT_FILENAME = "flattened.png"

    def add_settings(self) -> None:
        self.add_parameter(
            float_parameter(
                "strength",
                1.0,
                "How much to flatten. 1 is fully flat. Lower keeps some of the original light.",
                0.0,
                1.0,
                0.05,
            )
        )

    def transform(self, image: Any) -> Any:
        return tools.flatten_paper(image, float(self.get_parameter_value("strength") or 0.0))
