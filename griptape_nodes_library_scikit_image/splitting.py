"""The parts of Split Image that need no imaging libraries: the settings, their checks, and the reading order."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

BACKGROUND_PAPER = "paper"
BACKGROUND_TRANSPARENT = "transparent"
BACKGROUND_CHOICES = [BACKGROUND_PAPER, BACKGROUND_TRANSPARENT]

PADDING_CHOICES = ["1", "2", "3", "4", "5", "6", "7", "8"]
DEFAULT_PADDING_DIGITS = 4


class CompareView(StrEnum):
    """What Diff Images shows in its widget, and saves as its output."""

    WIPE = "Wipe"
    IMAGE_1 = "Image 1"
    IMAGE_2 = "Image 2"
    DIFFERENCE = "Difference"
    HEAT = "Heat"


MAX_PIECES = 50
MAX_BOIL_FRAMES = 96


@dataclass(frozen=True)
class Region:
    """One piece found in the image. The box is in pixels, with right and bottom not included."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def box(self) -> list[int]:
        """The box as [left, top, right, bottom], the form the widget sends and receives."""
        return [self.left, self.top, self.right, self.bottom]


@dataclass(frozen=True)
class SplitSettings:
    """The settings of one split. Join distance, minimum size and padding are percentages of the image's longer side."""

    sensitivity: float
    join_distance: float
    min_size: float
    padding: float
    ignore_corner_pieces: bool


@dataclass(frozen=True)
class Candidate:
    """A blob of marks that may become a piece, before the size and corner settings are applied.

    The sizes are the longest side as a percentage of the image's longer side, so they compare directly with the
    'Minimum size' setting.
    """

    region: Region
    blob_size: float  # the joined blob, which is bigger than the marks inside it
    tight_size: float  # just the marks
    edges: int  # how many edges of the image the marks touch


def classify(
    candidates: list[Candidate], min_size: float, ignore_corner_pieces: bool
) -> tuple[list[Candidate], list[Candidate]]:
    """Split candidates into the pieces to keep, in reading order, and the ones dropped for the settings.

    A blob smaller than the minimum is skipped, like a speck. If only its marks are smaller, or it touches two edges
    and corner pieces are ignored, it is dropped and shown as such. The widget's JavaScript (_boxes.js) does the same,
    so the settings can change what is shown while a slider moves. Change one, and change the other.
    """
    kept: list[Candidate] = []
    dropped: list[Candidate] = []
    for candidate in candidates:
        if candidate.blob_size < min_size:
            continue
        if candidate.tight_size < min_size or (ignore_corner_pieces and candidate.edges >= 2):
            dropped.append(candidate)
        else:
            kept.append(candidate)
    by_region = {candidate.region: candidate for candidate in kept}
    return [by_region[region] for region in reading_order([candidate.region for candidate in kept])], dropped


def validate_settings(settings: SplitSettings) -> list[str]:
    """Plain-language problems with the settings, empty when they are fine."""
    problems = []
    if not 0.01 <= settings.sensitivity <= 0.9:
        problems.append(f"'Sensitivity' must be between 0.01 and 0.9. It's set to {settings.sensitivity}.")
    if settings.join_distance < 0:
        problems.append(f"'Join distance' can't be negative. It's set to {settings.join_distance}.")
    if settings.min_size <= 0:
        problems.append(f"'Minimum size' must be more than 0. It's set to {settings.min_size}.")
    if settings.padding < 0:
        problems.append(f"'Padding' can't be negative. It's set to {settings.padding}.")
    return problems


def reading_order(regions: list[Region]) -> list[Region]:
    """Sort pieces left to right within a row and rows from top to bottom.

    A piece joins the current row when its centre is within half the median piece height of the row's first piece.
    """
    if not regions:
        return []
    heights = sorted(region.height for region in regions)
    row_height = heights[len(heights) // 2] / 2
    by_height = sorted(regions, key=lambda region: region.center_y)
    rows: list[list[Region]] = []
    row_start = None
    for region in by_height:
        if row_start is None or region.center_y - row_start > row_height:
            rows.append([])
            row_start = region.center_y
        rows[-1].append(region)
    return [region for row in rows for region in sorted(row, key=lambda region: region.left)]


def padded(region: Region, padding: int, width: int, height: int) -> Region:
    """The region grown by padding on every side, kept inside an image of this size."""
    return Region(
        left=max(0, region.left - padding),
        top=max(0, region.top - padding),
        right=min(width, region.right + padding),
        bottom=min(height, region.bottom + padding),
    )


def excluded_boxes(widget_value: object) -> set[tuple[int, ...]]:
    """The boxes the user switched off in the widget. Anything malformed is ignored."""
    if not isinstance(widget_value, dict):
        return set()
    boxes = set()
    for box in widget_value.get("excluded") or []:
        try:
            left, top, right, bottom = (int(number) for number in box)
        except (TypeError, ValueError):
            continue
        boxes.add((left, top, right, bottom))
    return boxes


def piece_file_name(prefix: str, number: int, digits: int) -> str:
    """The file name of a piece, numbered from 1 and zero-padded like Extract Frames: pieces.0001.png."""
    return f"{prefix}.{number:0{digits}d}.png"
