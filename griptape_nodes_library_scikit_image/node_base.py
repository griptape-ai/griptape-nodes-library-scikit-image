"""Shared parts of the image nodes: reading images, saving results, and the frame-sequence nodes."""

from __future__ import annotations

import io
import logging
import pathlib
from typing import Any

from griptape.artifacts.image_url_artifact import ImageUrlArtifact
from griptape_nodes.common.sequences import MissingItemPolicy, Sequence
from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, DataNode, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_directory_parameter import ProjectDirectoryParameter
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.events.os_events import ScanSequencesRequest, ScanSequencesResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

from griptape_nodes_library_scikit_image import tools
from griptape_nodes_library_scikit_image.params import bool_parameter, build_output_directory
from griptape_nodes_library_scikit_image.splitting import (
    DEFAULT_PADDING_DIGITS,
    PADDING_CHOICES,
    piece_file_name,
)

logger = logging.getLogger("griptape_nodes")

__all__ = ["FramesNode", "ImageNode", "browser_url", "image_location", "open_image"]


def image_location(value: Any) -> str:
    """The file or URL named by an image value: an artifact, the dict form of one, or plain text."""
    if isinstance(value, dict):
        return str(value.get("value", "") or "").strip()
    if isinstance(value, str):
        return value.strip()
    location = getattr(value, "value", None)
    return str(location).strip() if isinstance(location, str) else ""


def open_image(location: str, label: str) -> Any:
    """Open the image at a file or URL, or raise a NodeError that names the parameter it came from."""
    from griptape_nodes_library_scikit_image import runner

    try:
        return runner.open_image(File(location).read_bytes())
    except Exception as e:
        msg = f"Could not read the image connected to '{label}' ({location}): {e}"
        raise NodeError(msg) from e


def browser_url(value: Any) -> str:
    """A URL the editor can load for an image value, or an empty string if there is none."""
    from griptape_nodes.retained_mode.events.static_file_events import (
        CreateStaticFileDownloadUrlFromPathRequest,
        CreateStaticFileDownloadUrlResultSuccess,
    )

    location = image_location(value)
    if not location:
        return ""
    if location.startswith(("http://", "https://", "data:")):
        return location
    try:
        resolved = File(location).resolve()
        result = GriptapeNodes.handle_request(CreateStaticFileDownloadUrlFromPathRequest(file_path=resolved))
        if isinstance(result, CreateStaticFileDownloadUrlResultSuccess):
            return result.url
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not make a URL for the preview of '%s': %s", location, e)
    return location


class ImageNode(DataNode):
    """A node that takes an image, and maybe a second one, and saves images. Subclasses fill in a few hooks.

    `add_settings` adds the node's own parameters. `run` does the work and calls `publish` for each output image.
    """

    INPUT_TOOLTIP = "The image to work on."
    OUTPUT_TOOLTIP = "The result."
    OUTPUT_FILENAME = "result.png"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._files: dict[str, ProjectFileParameter] = {}
        self.add_image_input("image", self.INPUT_TOOLTIP)
        self.add_settings()
        self.add_outputs()

    def add_image_input(self, name: str, tooltip: str) -> None:
        self.add_parameter(
            ParameterImage(
                name=name,
                tooltip=tooltip,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide_property=True,
            )
        )

    def add_image_output(self, name: str, tooltip: str, filename: str) -> None:
        self.add_parameter(
            ParameterImage(
                name=name,
                tooltip=tooltip,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"expander": True},
            )
        )
        self._files[name] = ProjectFileParameter(node=self, name=f"{name}_file", default_filename=filename)
        self._files[name].add_parameter()

    def add_settings(self) -> None:
        """Add the node's own parameters. The default adds none."""

    def add_outputs(self) -> None:
        self.add_image_output("output", self.OUTPUT_TOOLTIP, self.OUTPUT_FILENAME)

    def load_input(self, name: str = "image", label: str = "Image") -> Any:
        location = image_location(self.get_parameter_value(name))
        if not location:
            msg = f"There is no image in '{label}'. Connect an image to '{label}'."
            raise NodeError(msg)
        return open_image(location, label)

    def publish(self, name: str, image: Any) -> None:
        """Save an image as a PNG in the project and set it as the output."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        saved = self._files[name].build_file().write_bytes(buffer.getvalue())
        self.parameter_output_values[name] = ImageUrlArtifact(value=saved.location)

    def transform(self, image: Any) -> Any:
        raise NotImplementedError

    def run(self, image: Any) -> None:
        self.publish("output", self.transform(image))

    def process(self) -> None:
        image = self.load_input()
        try:
            self.run(image)
        except ValueError as e:
            raise NodeError(str(e)) from e


class FramesNode(SuccessFailureNode):
    """A node that makes several images from one or two, and saves them as a numbered sequence in a versioned folder.

    Subclasses fill in `add_inputs` and `render`. The files are named like Extract Frames: prefix.0001.png.
    """

    DIRNAME = "frames"
    INPUT_TOOLTIP = "The image to work on."

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_image_input("image", self.INPUT_TOOLTIP)
        self.add_inputs()
        self.add_parameter(
            ParameterString(
                name="file_prefix",
                default_value=self.DIRNAME,
                tooltip="The start of each file name, as in Extract Frames: prefix.0001.png, prefix.0002.png and so on.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            ParameterString(
                name="number_padding",
                default_value=str(DEFAULT_PADDING_DIGITS),
                tooltip="Number of digits used to zero-pad the frame number in each file name.",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=PADDING_CHOICES)},
            )
        )
        self.add_parameter(
            bool_parameter(
                "even_size",
                True,
                "Crop a pixel off an odd width or height. Video encoders such as H.264 refuse frames with an odd size, "
                "which Create Video from Frames would report as an ffmpeg error.",
            )
        )
        self._output_dir = ProjectDirectoryParameter(node=self, name="output_dir", default_dirname=self.DIRNAME)
        self._output_dir.add_parameter()
        self.add_parameter(
            Parameter(
                name="frames",
                type="list",
                output_type="list",
                default_value=[],
                tooltip="The frames as images, in order.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="sequence",
                type="Sequence",
                output_type="Sequence",
                default_value=None,
                tooltip="The frames as a sequence. Wire it into Inspect Sequence or any other node that takes a sequence.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Sequence"},
            )
        )
        self.add_parameter(
            ParameterInt(name="count", tooltip="How many frames were made.", allowed_modes={ParameterMode.OUTPUT})
        )
        self.add_parameter(
            ParameterString(
                name="output_directory",
                tooltip="The folder the files were saved in.",
                placeholder_text="The output folder will appear here",
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the result or any errors",
            result_details_placeholder="Status will appear here.",
        )
        details = self.get_parameter_by_name("result_details")
        if details is not None:
            # The details name the folder as a project macro such as {outputs}/frames_v001. Keep them plain text,
            # because the engine treats a {name} in a value as a workflow variable.
            details.allow_variable_substitution = False

    def add_image_input(self, name: str, tooltip: str) -> None:
        self.add_parameter(
            ParameterImage(
                name=name,
                tooltip=tooltip,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide_property=True,
            )
        )

    def add_inputs(self) -> None:
        """Add the node's own parameters. The default adds none."""

    def render(self, image: Any) -> list[Any]:
        raise NotImplementedError

    def check_settings(self) -> list[str]:
        """Plain-language problems with the settings, empty when they are fine."""
        return []

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if not image_location(self.get_parameter_value("image")):
            exceptions.append(NodeError("There is no image to work on. Connect an image to 'Image'."))
        exceptions.extend(NodeError(problem) for problem in self.check_settings())
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        # The engine runs the callable and sends its result back. It never throws an error into this generator, so the
        # failure handling has to live inside the callable.
        yield self._render_and_report

    def _render_and_report(self) -> None:
        try:
            self._render_and_save()
        except Exception as e:
            self.parameter_output_values["frames"] = []
            self.parameter_output_values["sequence"] = None
            self.parameter_output_values["count"] = 0
            self.parameter_output_values["output_directory"] = ""
            self._set_status_results(was_successful=False, result_details=f"Failed: {e}")
            self._handle_failure_exception(e)

    def _render_and_save(self) -> None:
        prefix = str(self.get_parameter_value("file_prefix") or self.DIRNAME).strip() or self.DIRNAME
        digits = int(self.get_parameter_value("number_padding") or DEFAULT_PADDING_DIGITS)
        location = image_location(self.get_parameter_value("image"))
        if not location:
            msg = "There is no image to work on. Connect an image to 'Image'."
            raise NodeError(msg)
        try:
            frames = self.render(open_image(location, "Image"))
        except ValueError as e:
            raise NodeError(str(e)) from e

        if self.get_parameter_value("even_size"):
            frames = [tools.make_even(frame) for frame in frames]

        directory = build_output_directory(self, self._output_dir, "output_dir").create()
        folder = directory.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        artifacts = []
        for number, frame in enumerate(frames, start=1):
            name = piece_file_name(prefix, number, digits)
            frame.save(folder / name, format="PNG")
            artifacts.append(ImageUrlArtifact(value=f"{directory.location}/{name}", name=name))

        self.parameter_output_values["frames"] = artifacts
        self.parameter_output_values["sequence"] = self._scan_sequence(folder, prefix, digits, len(artifacts))
        self.parameter_output_values["count"] = len(artifacts)
        self.parameter_output_values["output_directory"] = directory.location
        self._set_status_results(
            was_successful=True,
            result_details=f"Made {len(artifacts)} frames and saved them in {directory.location}.",
        )

    def _scan_sequence(self, folder: pathlib.Path, prefix: str, digits: int, count: int) -> Sequence | None:
        """Scan the frames just written into a Sequence. The sequence is a convenience, so a failure only logs."""
        result = GriptapeNodes.handle_request(
            ScanSequencesRequest(
                path=str(folder / f"{prefix}.{'#' * digits}.png"),
                policy=MissingItemPolicy.SKIP,
                start_number=1,
                end_number=count,
            )
        )
        if isinstance(result, ScanSequencesResultSuccess) and result.sequences:
            return result.sequences[0]
        logger.warning("%s: could not build the sequence output: %s", self.name, result.result_details)
        return None
