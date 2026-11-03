"""Lines to Alpha: the marks on paper as an alpha channel."""

from __future__ import annotations

from typing import Any

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode
from griptape_nodes_library_scikit_image.params import float_parameter

__all__ = ["LinesToAlpha"]


class LinesToAlpha(ImageNode):
    """Find the marks on the paper and return just their alpha channel.

    The output is a greyscale image: white where there is a mark, black where there is paper, and grey where a faint
    mark fades in. Use it as a mask or matte on the drawing or on anything else.
    """

    INPUT_TOOLTIP = "The photo or scan of a drawing."
    OUTPUT_TOOLTIP = "The alpha of the marks: white on a mark, black on paper."
    OUTPUT_FILENAME = "alpha.png"

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
                "softness",
                0.15,
                "How gradually a mark fades in as it gets more different from the paper. Lower is crisper.",
                0.01,
                1.0,
                0.01,
            )
        )

    def add_outputs(self) -> None:
        self.add_image_output("alpha", self.OUTPUT_TOOLTIP, self.OUTPUT_FILENAME)

    def run(self, image: Any) -> None:
        self.publish(
            "alpha",
            tools.lines_to_alpha(
                image,
                float(self.get_parameter_value("sensitivity") or 0.12),
                float(self.get_parameter_value("softness") or 0.15),
            ),
        )
