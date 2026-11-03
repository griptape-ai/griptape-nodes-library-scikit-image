"""Parameter builders shared by the image nodes."""

from __future__ import annotations

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.color_picker import ColorPicker

__all__ = ["bool_parameter", "colour_parameter", "float_parameter", "int_parameter", "string_parameter"]

MODES = {ParameterMode.INPUT, ParameterMode.PROPERTY}


def float_parameter(name: str, default: float, tooltip: str, low: float, high: float, step: float) -> ParameterFloat:
    return ParameterFloat(
        name=name, default_value=default, tooltip=tooltip, min_val=low, max_val=high, step=step, allowed_modes=MODES
    )


def int_parameter(name: str, default: int, tooltip: str, low: int, high: int) -> ParameterInt:
    return ParameterInt(
        name=name, default_value=default, tooltip=tooltip, min_val=low, max_val=high, allowed_modes=MODES
    )


def string_parameter(name: str, default: str, tooltip: str) -> ParameterString:
    return ParameterString(name=name, default_value=default, tooltip=tooltip, allowed_modes=MODES)


def bool_parameter(name: str, default: bool, tooltip: str) -> ParameterBool:
    return ParameterBool(name=name, default_value=default, tooltip=tooltip, allowed_modes=MODES)


def colour_parameter(name: str, default: str, tooltip: str) -> ParameterString:
    """A colour chosen with the colour picker. The value is a hex string such as #2a8fd6."""
    return ParameterString(
        name=name,
        default_value=default,
        tooltip=tooltip,
        allowed_modes={ParameterMode.PROPERTY},
        traits={ColorPicker(format="hex")},
    )
