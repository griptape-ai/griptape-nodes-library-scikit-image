"""Parameter builders shared by the image nodes."""

from __future__ import annotations

import pathlib

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.project_directory_parameter import ProjectDirectoryParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files import path_utils
from griptape_nodes.files.directory import DirectoryDestination
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.traits.color_picker import ColorPicker

__all__ = [
    "bool_parameter",
    "build_output_directory",
    "colour_parameter",
    "float_parameter",
    "int_parameter",
    "string_parameter",
]

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


# TODO: remove build_output_directory and _explicit_directory_path once ProjectDirectoryParameter.build_directory()
# uses absolute paths as given. The engine fix is https://github.com/griptape-ai/griptape-nodes-engine/pull/6246, and
# the logic below is copied from it.
def build_output_directory(node: BaseNode, param: ProjectDirectoryParameter, name: str) -> DirectoryDestination:
    """The destination for an output directory parameter.

    A plain name goes through the project's output situation, which nests it under the outputs directory and
    versions it. An absolute path, `~` path, or `file://` address is the directory the user asked for, so it is used
    as given and not versioned.
    """
    value = node.get_parameter_value(name)
    if isinstance(value, str) and value.strip():
        explicit_path = _explicit_directory_path(value.strip())
        if explicit_path is not None:
            return DirectoryDestination(
                explicit_path, existing_dir_policy=ExistingFilePolicy.OVERWRITE, create_parents=True
            )
    return param.build_directory()


def _explicit_directory_path(dirname: str) -> str | None:
    """Return the local path `dirname` names, or None when it is a plain directory name.

    Absolute paths, `~` paths, and `file://` addresses name a location. Any other address, and a drive path from
    another operating system, cannot be saved to and raise.

    Raises:
        ValueError: If `dirname` is an address or drive path that names no location on this computer.
    """
    local_path_from_uri = path_utils.parse_file_uri(dirname)
    if local_path_from_uri is not None:
        if (
            pathlib.PureWindowsPath(local_path_from_uri).is_absolute()
            and not pathlib.Path(local_path_from_uri).is_absolute()
        ):
            msg = (
                f"Attempted to save to directory '{dirname}'. Failed because that address does not name a "
                f"location on this computer. A path from another operating system, such as a 'C:' drive "
                f"on macOS or Linux, has no equivalent here."
            )
            raise ValueError(msg)
        return local_path_from_uri

    if path_utils.is_url(dirname):
        msg = (
            f"Attempted to save to directory '{dirname}'. Failed because that address points somewhere this "
            f"computer cannot save to. Enter a directory name, a folder path, or a 'file://' address "
            f"naming a folder on this machine."
        )
        raise ValueError(msg)

    expanded = pathlib.Path(dirname).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    return None
