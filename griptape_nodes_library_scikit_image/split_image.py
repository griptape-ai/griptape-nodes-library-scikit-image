"""Split Image: cut an image, such as a model sheet of poses on paper, into one image per piece."""

from __future__ import annotations

import io
import logging
import pathlib
from typing import Any

from griptape.artifacts.image_url_artifact import ImageUrlArtifact
from griptape_nodes.common.sequences import MissingItemPolicy, Sequence
from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_directory_parameter import ProjectDirectoryParameter
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.events.os_events import ScanSequencesRequest, ScanSequencesResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

from griptape_nodes_library_scikit_image.params import build_output_directory
from griptape_nodes_library_scikit_image.splitting import (
    BACKGROUND_CHOICES,
    BACKGROUND_PAPER,
    DEFAULT_PADDING_DIGITS,
    MAX_PIECES,
    PADDING_CHOICES,
    Region,
    SplitSettings,
    piece_file_name,
    validate_settings,
)

logger = logging.getLogger("griptape_nodes")

__all__ = ["SplitImage"]

DEFAULT_SENSITIVITY = 0.12
DEFAULT_JOIN_DISTANCE = 0.6
DEFAULT_MIN_SIZE = 3.0
DEFAULT_PADDING = 1.5
DEFAULT_PREFIX = "pieces"
PREVIEW_PARAMETERS = {"image", "join_distance", "padding", "sensitivity", "min_size", "ignore_corner_pieces"}


def image_location(value: Any) -> str:
    """The file or URL named by an image value: an artifact, the dict form of one, or plain text."""
    if isinstance(value, dict):
        return str(value.get("value", "") or "").strip()
    if isinstance(value, str):
        return value.strip()
    location = getattr(value, "value", None)
    return str(location).strip() if isinstance(location, str) else ""


class SplitImage(SuccessFailureNode):
    """Split an image into one image per piece.

    Made for a model sheet: several drawings on one sheet of paper. The node finds the marks on the paper, joins the
    marks that sit close together into one piece, and crops each piece out in reading order. It saves every piece as a
    PNG and gives them back as a list.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="The image to split, such as a photo or scan of a model sheet.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide_property=True,
            )
        )
        self.add_parameter(
            ParameterImage(
                name="preview",
                tooltip=(
                    "The image with each piece outlined in its own colour and numbered in reading order. With padding, a "
                    "dashed box in the same colour shows the crop that is saved. Pieces that were dropped are outlined in "
                    "red and cross-hatched. It updates when you change the image or a setting, without running the node."
                ),
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Preview", "expander": True},
            )
        )
        self.add_parameter(
            ParameterString(
                name="background",
                default_value=BACKGROUND_PAPER,
                tooltip="Paper keeps the paper around each piece. Transparent clears everything outside the piece's shape.",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=BACKGROUND_CHOICES)},
            )
        )
        self.add_parameter(
            ParameterFloat(
                name="join_distance",
                default_value=DEFAULT_JOIN_DISTANCE,
                tooltip=(
                    "Marks closer together than this count as one piece, as a percentage of the image's longer side. "
                    "Raise it if a pose comes apart, for example a tail or a hand that is drawn a little away from the "
                    "body. Lower it if two poses merge."
                ),
                min_val=0.0,
                max_val=20.0,
                step=0.1,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            ParameterFloat(
                name="padding",
                default_value=DEFAULT_PADDING,
                tooltip="Space to keep around each piece, as a percentage of the image's longer side.",
                min_val=0.0,
                max_val=20.0,
                step=0.1,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            ParameterString(
                name="file_prefix",
                default_value=DEFAULT_PREFIX,
                tooltip="The start of each file name. The pieces are saved as prefix.0001.png, prefix.0002.png and so on.",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            ParameterString(
                name="number_padding",
                default_value=str(DEFAULT_PADDING_DIGITS),
                tooltip="Number of digits used to zero-pad the piece number in each file name.",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=PADDING_CHOICES)},
            )
        )
        self._output_dir = ProjectDirectoryParameter(node=self, name="output_dir", default_dirname=DEFAULT_PREFIX)
        self._output_dir.add_parameter()
        with ParameterGroup(name="advanced", ui_options={"display_name": "Advanced", "collapsed": True}) as advanced:
            ParameterFloat(
                name="sensitivity",
                default_value=DEFAULT_SENSITIVITY,
                tooltip=(
                    "How much darker than the paper a mark must be to count. Lower picks up fainter marks, such as light "
                    "crayon, and also paper texture and shadows. Higher keeps only strong lines."
                ),
                min_val=0.01,
                max_val=0.9,
                step=0.01,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterFloat(
                name="min_size",
                default_value=DEFAULT_MIN_SIZE,
                tooltip=(
                    "Pieces whose longest side is shorter than this are dropped, as a percentage of the image's longer "
                    "side. This removes specks."
                ),
                min_val=0.1,
                max_val=100.0,
                step=0.1,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterBool(
                name="ignore_corner_pieces",
                default_value=True,
                tooltip=(
                    "Drop pieces that touch two edges of the image, such as a thumb holding the paper in a corner or the "
                    "edge of the table. A piece that touches only one edge is kept."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        self.add_node_element(advanced)

        self._preview_file = ProjectFileParameter(node=self, name="preview_file", default_filename="preview.jpg")
        self._preview_file.add_parameter()
        self.add_parameter(
            Parameter(
                name="pieces",
                type="list",
                output_type="list",
                default_value=[],
                tooltip="The pieces as images, in reading order: left to right, then top to bottom.",
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
                tooltip=(
                    "The pieces as a sequence, with piece numbers, paths and the filename pattern in one object. Wire it "
                    "into Inspect Sequence or any other node that takes a sequence."
                ),
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Sequence"},
            )
        )
        self.add_parameter(
            ParameterInt(
                name="count",
                tooltip="How many pieces were found.",
                allowed_modes={ParameterMode.OUTPUT},
            )
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
            result_details_tooltip="Details about the split or any errors",
            result_details_placeholder="Split status will appear here.",
        )
        details = self.get_parameter_by_name("result_details")
        if details is not None:
            # The details name the folder as a project macro such as {outputs}/split_v001. Keep them plain text,
            # because the engine treats a {name} in a value as a workflow variable.
            details.allow_variable_substitution = False

    def _settings(self) -> SplitSettings:
        sensitivity = self.get_parameter_value("sensitivity")
        return SplitSettings(
            sensitivity=DEFAULT_SENSITIVITY if sensitivity is None else float(sensitivity),
            join_distance=float(self.get_parameter_value("join_distance") or 0),  # 0 is a real choice
            min_size=float(self.get_parameter_value("min_size") or DEFAULT_MIN_SIZE),
            padding=float(self.get_parameter_value("padding") or 0),
            ignore_corner_pieces=bool(self.get_parameter_value("ignore_corner_pieces")),
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in PREVIEW_PARAMETERS:
            self._refresh_preview()
        return super().after_value_set(parameter, value)

    def _refresh_preview(self) -> None:
        """Redraw the preview from the current image and settings. Editing a setting must never fail, so this only logs."""
        try:
            location = image_location(self.get_parameter_value("image"))
            settings = self._settings()
            if not location or validate_settings(settings):
                self.parameter_output_values["preview"] = None
                self.publish_update_to_parameter("preview", None)
                return
            from griptape_nodes_library_scikit_image import runner

            image = self._load_image(location)
            found, dropped = runner.scan_pieces(image, settings)
            self._save_preview(image, found, dropped, settings)
            self.publish_update_to_parameter("preview", self.parameter_output_values["preview"])
            self.publish_update_to_parameter("count", len(found))
        except Exception as e:  # noqa: BLE001
            logger.warning("%s: could not update the preview: %s", self.name, e)

    def _save_preview(
        self, image: Any, found: list[tuple[Region, Any]], dropped: list[Region], settings: SplitSettings
    ) -> None:
        """Draw the preview, save it, and set it and the count as outputs."""
        from griptape_nodes_library_scikit_image import runner

        padding = round(settings.padding / 100 * max(image.size))
        preview = runner.draw_preview(image, [region for region, _ in found], dropped, padding)
        buffer = io.BytesIO()
        preview.save(buffer, format="JPEG", quality=90)
        saved = self._preview_file.build_file().write_bytes(buffer.getvalue())
        self.parameter_output_values["preview"] = ImageUrlArtifact(value=saved.location)
        self.parameter_output_values["count"] = len(found)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if not image_location(self.get_parameter_value("image")):
            exceptions.append(NodeError("There is no image to split. Connect an image to 'Image'."))
        exceptions.extend(NodeError(problem) for problem in validate_settings(self._settings()))
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        # The engine runs the callable and sends its result back. It never throws an error into this generator, so the
        # failure handling has to live inside the callable.
        yield self._split_and_report

    def _split_and_report(self) -> None:
        try:
            self._split()
        except Exception as e:
            self.parameter_output_values["pieces"] = []
            self.parameter_output_values["sequence"] = None
            self.parameter_output_values["count"] = 0
            self.parameter_output_values["output_directory"] = ""
            self._set_status_results(was_successful=False, result_details=f"Split failed: {e}")
            self._handle_failure_exception(e)

    def _load_image(self, location: str) -> Any:
        from griptape_nodes_library_scikit_image import runner

        try:
            return runner.open_image(File(location).read_bytes())
        except Exception as e:
            msg = f"Could not read the image connected to 'Image' ({location}): {e}"
            raise NodeError(msg) from e

    def _scan_sequence(self, folder: pathlib.Path, prefix: str, digits: int, count: int) -> Sequence | None:
        """Scan the pieces just written into a Sequence. The sequence is a convenience, so a failure only logs."""
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

    def _split(self) -> None:
        from griptape_nodes_library_scikit_image import runner

        settings = self._settings()
        background = str(self.get_parameter_value("background") or BACKGROUND_PAPER)
        prefix = str(self.get_parameter_value("file_prefix") or DEFAULT_PREFIX).strip() or DEFAULT_PREFIX
        digits = int(self.get_parameter_value("number_padding") or DEFAULT_PADDING_DIGITS)
        location = image_location(self.get_parameter_value("image"))
        if not location:
            msg = "There is no image to split. Connect an image to 'Image'."
            raise NodeError(msg)

        image = self._load_image(location)
        found, dropped = runner.scan_pieces(image, settings)
        self._save_preview(image, found, dropped, settings)
        if not found:
            msg = (
                "No pieces were found. Lower 'Sensitivity' to pick up fainter marks, lower 'Minimum size', or turn off "
                "'Ignore corner pieces' if a drawing sits in a corner of the image."
            )
            raise NodeError(msg)
        if len(found) > MAX_PIECES:
            msg = (
                f"{len(found)} pieces were found, which is more than the {MAX_PIECES} this node saves. Raise "
                "'Minimum size' or 'Join distance', or raise 'Sensitivity' if paper texture is being picked up."
            )
            raise NodeError(msg)

        directory = build_output_directory(self, self._output_dir, "output_dir").create()
        folder = directory.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        pieces = []
        for number, (region, shape) in enumerate(found, start=1):
            name = piece_file_name(prefix, number, digits)
            runner.cut_piece(image, region, shape, settings, background).save(folder / name, format="PNG")
            pieces.append(ImageUrlArtifact(value=f"{directory.location}/{name}", name=name))

        self.parameter_output_values["pieces"] = pieces
        self.parameter_output_values["sequence"] = self._scan_sequence(folder, prefix, digits, len(pieces))
        self.parameter_output_values["count"] = len(pieces)
        self.parameter_output_values["output_directory"] = directory.location
        self._set_status_results(
            was_successful=True,
            result_details=f"Found {len(pieces)} pieces and saved them in {directory.location}.",
        )
