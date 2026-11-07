"""Lines to SVG: trace the marks on paper into a vector file."""

from __future__ import annotations

import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.widget import Widget

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.node_base import ImageNode, browser_url, image_location, open_image
from griptape_nodes_library_scikit_image.params import colour_parameter, float_parameter

__all__ = ["LinesToSvg"]

logger = logging.getLogger("griptape_nodes")

LIBRARY_NAME = "Griptape Nodes scikit-image Library"
WIDGET_NAME = "LinesToSvg"
EDITOR = "trace_editor"
# The settings the widget reads. Sensitivity and Simplify change the trace, which Python redoes. The fill colour only
# changes how the widget draws it.
SYNCED_PARAMETERS = ["sensitivity", "simplify", "fill_colour"]
# The settings that decide the trace.
TRACE_PARAMETERS = {"image", "sensitivity", "simplify"}
DEFAULT_SENSITIVITY = 0.12


def default_widget_value() -> dict[str, Any]:
    """The widget's value: the image to draw, the traced path, how many shapes it has, and why there is no trace."""
    return {"image_url": "", "width": 0, "height": 0, "path": "", "count": 0, "message": ""}


class LinesToSvg(ImageNode):
    """Trace the outline of every mark into an SVG, filled with one colour.

    The SVG has the same size as the image, so it can be imported into Blender or another tool as curves. Each stroke
    becomes a filled shape, not a centre line. The widget shows the trace on your image before you run the node.
    """

    INPUT_TOOLTIP = "The photo or scan of a drawing."

    def add_settings(self) -> None:
        self.add_parameter(
            ParameterDict(
                name=EDITOR,
                default_value=default_widget_value(),
                tooltip=(
                    "The traced shapes on your image. Switch between the trace alone, the trace over the image, and the "
                    "image. It updates when you change the image or a setting, without running the node."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Widget(name=WIDGET_NAME, library=LIBRARY_NAME, synced_parameters=SYNCED_PARAMETERS)},
                ui_options={"display_name": "Trace"},
            )
        )
        self.add_parameter(
            float_parameter(
                "sensitivity",
                0.12,
                "How different from the paper a mark must be to count. Lower picks up fainter marks and also paper texture.",
                0.01,
                0.9,
                0.01,
                slider=True,
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
                slider=True,
            )
        )
        self.add_parameter(colour_parameter("fill_colour", "#000000", "The colour of the shapes."))

    def add_outputs(self) -> None:
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

    def _settings(self) -> tuple[float, float, str]:
        sensitivity = self.get_parameter_value("sensitivity")
        return (
            DEFAULT_SENSITIVITY if sensitivity is None else float(sensitivity),
            float(self.get_parameter_value("simplify") or 0.0),
            str(self.get_parameter_value("fill_colour") or "#000000"),
        )

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Keep the widget in step while a workflow loads.

        Loading sets values with initial_setup, which skips after_value_set, so the saved image URL in the widget would
        never be refreshed. The widget is worked out again whenever a value it is built from loads.
        """
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )
        if initial_setup and param_name in TRACE_PARAMETERS:
            self._update_widget()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in TRACE_PARAMETERS:
            self._update_widget()
        return super().after_value_set(parameter, value)

    def _update_widget(self) -> None:
        """Trace the current image and hand the widget the image and the path. Editing a setting must never fail, so
        this only logs. When there is nothing to trace, the widget gets the reason instead of a path."""
        try:
            data = default_widget_value()
            location = image_location(self.get_parameter_value("image"))
            if location:
                data["image_url"] = browser_url(self.get_parameter_value("image"))
                image = open_image(location, "Image")
                data["width"], data["height"] = image.size
                sensitivity, simplify, _ = self._settings()
                try:
                    _, _, paths = tools.trace_lines(image, sensitivity, simplify)
                    data["path"], data["count"] = " ".join(paths), len(paths)
                except ValueError as e:
                    data["message"] = str(e)
            self.parameter_output_values[EDITOR] = data
            self.set_parameter_value(EDITOR, data)
            self.publish_update_to_parameter(EDITOR, data)
        except Exception as e:  # noqa: BLE001
            logger.warning("%s: could not update the trace: %s", self.name, e)

    def run(self, image: Any) -> None:
        sensitivity, simplify, colour = self._settings()
        svg, paths = tools.lines_to_svg(image, sensitivity, simplify, colour)
        saved = self._svg_file.build_file().write_bytes(svg.encode("utf-8"))
        self.parameter_output_values["svg"] = saved.location
        self.parameter_output_values["paths"] = paths
