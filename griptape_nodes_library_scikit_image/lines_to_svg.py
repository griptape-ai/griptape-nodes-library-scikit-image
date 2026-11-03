"""Lines to SVG: trace the marks on paper into a vector file."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode
from griptape_nodes_library_scikit_image.params import colour_parameter, float_parameter

__all__ = ["LinesToSvg"]


class LinesToSvg(ImageNode):
    """Trace the outline of every mark into an SVG, filled with one colour.

    The SVG has the same size as the image, so it can be imported into Blender or another tool as curves. Each stroke
    becomes a filled shape, not a centre line. The preview shows the traced shapes as an image.
    """

    INPUT_TOOLTIP = "The photo or scan of a drawing."

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
                "simplify",
                1.0,
                "How far the traced outline may stray from the marks, in pixels. Higher gives fewer points and smoother curves.",
                0.0,
                10.0,
                0.1,
            )
        )
        self.add_parameter(colour_parameter("fill_colour", "#000000", "The colour of the shapes."))

    def add_outputs(self) -> None:
        self.add_image_output(
            "preview",
            "The traced shapes drawn as an image, to check the trace without opening the SVG.",
            "lines_preview.png",
        )
        self._svg_file = ProjectFileParameter(node=self, name="svg_file", default_filename="lines.svg")
        self._svg_file.add_parameter()
        self.add_parameter(
            ParameterString(
                name="svg",
                tooltip=(
                    "The location of the saved SVG file, as a path. It is not the SVG text. Open the file in Blender or an "
                    "editor, or wire the location into another node."
                ),
                placeholder_text="The SVG file location will appear here",
                ui_options={"display_name": "SVG File"},
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            ParameterInt(
                name="paths", tooltip="How many shapes were traced into the SVG.", allowed_modes={ParameterMode.OUTPUT}
            )
        )

    def run(self, image: Any) -> None:
        svg, paths, preview = tools.lines_to_svg(
            image,
            float(self.get_parameter_value("sensitivity") or 0.12),
            float(self.get_parameter_value("simplify") or 0.0),
            str(self.get_parameter_value("fill_colour") or "#000000"),
        )
        self.publish("preview", preview)
        saved = self._svg_file.build_file().write_bytes(svg.encode("utf-8"))
        self.parameter_output_values["svg"] = saved.location
        self.parameter_output_values["paths"] = paths
