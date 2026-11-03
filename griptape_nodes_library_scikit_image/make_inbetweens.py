"""Make In-Betweens: frames that move from one drawing to the next."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import NodeError

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import FramesNode, image_location, open_image
from griptape_nodes_library_scikit_image.params import int_parameter

__all__ = ["MakeInbetweens"]


class MakeInbetweens(FramesNode):
    """Fill in the frames between two drawings by following how things move from one to the other (optical flow).

    It works best when the two drawings are the same pose a little apart. Large changes smear.
    """

    DIRNAME = "inbetweens"
    INPUT_TOOLTIP = "The first drawing."

    def add_inputs(self) -> None:
        self.add_image_input("other", "The last drawing. It is resized to the size of the first.")
        self.add_parameter(
            int_parameter("in_between_count", 3, "How many frames to make between the two drawings.", 1, 60)
        )

    def check_settings(self) -> list[str]:
        if not image_location(self.get_parameter_value("other")):
            return ["There is no second drawing. Connect an image to 'Other'."]
        return []

    def render(self, image: Any) -> list[Any]:
        location = image_location(self.get_parameter_value("other"))
        if not location:
            msg = "There is no second drawing. Connect an image to 'Other'."
            raise NodeError(msg)
        return tools.inbetween_frames(
            image, open_image(location, "Other"), int(self.get_parameter_value("in_between_count") or 1)
        )
