"""Trim to Content: crop an image to the box that holds its marks."""

from __future__ import annotations

from typing import Any

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode
from griptape_nodes_library_scikit_image.params import float_parameter

__all__ = ["TrimToContent"]


class TrimToContent(ImageNode):
    """Cut away the empty paper around a drawing."""

    INPUT_TOOLTIP = "The image to trim."
    OUTPUT_TOOLTIP = "The image cropped to its marks."
    OUTPUT_FILENAME = "trimmed.png"

    def add_settings(self) -> None:
        self.add_parameter(
            float_parameter(
                "sensitivity",
                0.12,
                "How different from the paper a mark must be to count. Lower picks up fainter marks and also paper texture.",
                0.01,
                0.9,
                0.01,
            )
        )
        self.add_parameter(
            float_parameter(
                "padding",
                1.5,
                "Space to keep around the marks, as a percentage of the image's longer side.",
                0.0,
                20.0,
                0.1,
            )
        )

    def transform(self, image: Any) -> Any:
        return tools.trim_to_content(
            image,
            float(self.get_parameter_value("sensitivity") or 0.12),
            float(self.get_parameter_value("padding") or 0.0),
        )
