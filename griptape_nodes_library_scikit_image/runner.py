"""The parts of Split Image that use numpy, scikit-image and pillow.

Every import of them is inside a function, so this module imports even where they are missing.
"""

from __future__ import annotations

from typing import Any

from griptape_nodes_library_scikit_image.splitting import (
    BACKGROUND_TRANSPARENT,
    Region,
    SplitSettings,
    padded,
    reading_order,
)

WORK_SIZE = 900
EDGE_TOLERANCE = 2
SMOOTHING = 2.0
GOLDEN = 0.618034
HUE_START = 0.08
HUE_RANGE = 0.84
DROPPED_COLOUR = (230, 40, 40)
HATCH_COLOUR = (230, 40, 40, 190)
DROPPED_TINT = (230, 40, 40, 45)
LABEL_COLOUR = (0, 0, 0)
SPECK_AREA = 30
FIT_PASSES = 8
FIT_SPREAD = 2.5
MIN_FIT_TOLERANCE = 0.03
MIN_BACKGROUND_SHARE = 0.2


def open_image(data: bytes) -> Any:
    """Open image bytes as a PIL image, fully loaded."""
    import io

    import PIL.Image

    image = PIL.Image.open(io.BytesIO(data))
    image.load()
    return image


def estimate_background(pixels: Any, block: int) -> Any:
    """The colour of the paper or backdrop at every pixel, as a smooth surface.

    A quadratic in x and y is fitted to the median colour of small blocks, once per colour channel. Blocks that sit far
    from the fit, which are the drawings or figures, are left out and the surface is fitted again. The result follows a
    gradient or a vignette in the light without following the subjects.
    """
    import numpy as np
    from skimage import transform

    height, width = pixels.shape[:2]
    padded_height, padded_width = -(-height // block) * block, -(-width // block) * block
    edged = np.pad(pixels, ((0, padded_height - height), (0, padded_width - width), (0, 0)), mode="edge")
    blocks = np.median(
        edged.reshape(padded_height // block, block, padded_width // block, block, edged.shape[2]), axis=(1, 3)
    )
    rows, columns = blocks.shape[:2]
    y, x = np.mgrid[0:rows, 0:columns]
    x = x / max(columns - 1, 1) * 2 - 1
    y = y / max(rows - 1, 1) * 2 - 1
    terms = np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=-1).reshape(-1, 6)
    colours = blocks.reshape(-1, blocks.shape[2])
    keep = np.ones(len(terms), dtype=bool)
    coefficients = np.zeros((terms.shape[1], colours.shape[1]))
    for _ in range(FIT_PASSES):
        coefficients = np.linalg.lstsq(terms[keep], colours[keep], rcond=None)[0]
        off = np.abs(1 - colours / np.maximum(terms @ coefficients, 1e-3)).max(axis=-1)
        closer = off < max(MIN_FIT_TOLERANCE, FIT_SPREAD * np.median(off[keep]))
        if closer.sum() < MIN_BACKGROUND_SHARE * len(terms) or (closer == keep).all():
            break
        keep = closer
    surface = (terms @ coefficients).reshape(rows, columns, -1)
    return np.asarray(transform.resize(surface, (padded_height, padded_width), order=1))[:height, :width]


def find_marks(small: Any, sensitivity: float) -> Any:
    """A mask of the pixels that differ from the paper or backdrop around them, darker or lighter, in any colour channel.

    The image is smoothed a little first, so the weave of paper or canvas does not count. Specks smaller than a few
    pixels are removed.
    """
    import numpy as np
    from skimage import filters, measure

    pixels = small.astype(np.float32) / 255
    paper = estimate_background(pixels, max(4, max(pixels.shape[:2]) // 60))
    smooth = np.asarray(filters.gaussian(pixels, sigma=SMOOTHING, channel_axis=-1))
    differs = np.abs(1 - smooth / np.maximum(paper, 1e-3)).max(axis=-1) > sensitivity
    labels = np.asarray(measure.label(differs, connectivity=1))
    big = np.bincount(labels.ravel()) >= SPECK_AREA
    big[0] = False
    return big[labels]


def piece_shape(marks: Any, box: tuple[int, int, int, int], join: int) -> Any:
    """The filled shape of one piece: its marks with the gaps up to the join distance closed, and the holes filled."""
    import numpy as np
    from scipy import ndimage
    from skimage import morphology

    top, left, bottom, right = box
    around = max(join, 1) + 2
    height, width = marks.shape
    top, left = max(0, top - around), max(0, left - around)
    bottom, right = min(height, bottom + around), min(width, right + around)
    part = marks[top:bottom, left:right]
    if join:
        part = ndimage.binary_closing(np.pad(part, join), structure=morphology.disk(join))[join:-join, join:-join]
    shape = np.zeros_like(marks)
    shape[top:bottom, left:right] = ndimage.binary_fill_holes(ndimage.binary_dilation(part, iterations=2))
    return shape


def find_pieces(image: Any, settings: SplitSettings) -> list[tuple[Region, Any]]:
    """Find the pieces in a PIL image. Each is a box in the image's pixels and a mask of its shape at working size."""
    return scan_pieces(image, settings)[0]


def scan_pieces(image: Any, settings: SplitSettings) -> tuple[list[tuple[Region, Any]], list[Region]]:
    """Find the pieces in a PIL image, and the candidates that were dropped, as boxes in the image's pixels."""
    import numpy as np
    import PIL.Image
    from scipy import ndimage
    from skimage import measure, morphology

    width, height = image.size
    scale = min(1.0, WORK_SIZE / max(width, height))
    small = np.asarray(
        image.convert("RGB").resize(
            (max(1, round(width * scale)), max(1, round(height * scale))), PIL.Image.Resampling.LANCZOS
        )
    )
    marks = find_marks(small, settings.sensitivity)

    longer = max(width, height)
    join = round(settings.join_distance / 100 * longer * scale)
    dilated = ndimage.binary_dilation(marks, structure=morphology.disk(join)) if join else marks
    labels = measure.label(dilated)
    smallest = settings.min_size / 100 * longer * scale
    small_height, small_width = marks.shape

    found: list[tuple[Region, Any]] = []
    dropped: list[Region] = []
    for prop in measure.regionprops(labels):
        top, left, bottom, right = prop.bbox
        if max(right - left, bottom - top) < smallest:
            continue
        inside = labels == prop.label
        rows, columns = np.nonzero(marks & inside)
        if rows.size == 0:
            continue
        tight_top, tight_bottom = int(rows.min()), int(rows.max()) + 1
        tight_left, tight_right = int(columns.min()), int(columns.max()) + 1
        region = Region(
            left=int(tight_left / scale),
            top=int(tight_top / scale),
            right=min(width, int(tight_right / scale) + 1),
            bottom=min(height, int(tight_bottom / scale) + 1),
        )
        if max(tight_right - tight_left, tight_bottom - tight_top) < smallest:
            dropped.append(region)
            continue
        edges_touched = sum(
            (
                tight_left <= EDGE_TOLERANCE,
                tight_top <= EDGE_TOLERANCE,
                tight_right >= small_width - EDGE_TOLERANCE,
                tight_bottom >= small_height - EDGE_TOLERANCE,
            )
        )
        if settings.ignore_corner_pieces and edges_touched >= 2:
            dropped.append(region)
            continue
        shape = piece_shape(marks & inside, (top, left, bottom, right), join)
        found.append((region, shape))
    ordered = reading_order([region for region, _ in found])
    by_region = dict(found)
    return [(region, by_region[region]) for region in ordered], dropped


def piece_colour(index: int) -> tuple[int, int, int]:
    """A colour for the piece at this position, spread around the colour wheel and never red, which marks dropped pieces."""
    import colorsys

    hue = HUE_START + (index * GOLDEN % 1) * HUE_RANGE
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return round(red * 255), round(green * 255), round(blue * 255)


def dashed_rectangle(draw: Any, region: Region, colour: tuple[int, int, int], width: int, dash: int) -> None:
    """Draw the outline of a box as dashes, with each gap as long as a dash."""
    for left, top, right, bottom in (
        (region.left, region.top, region.right, region.top),
        (region.left, region.bottom, region.right, region.bottom),
        (region.left, region.top, region.left, region.bottom),
        (region.right, region.top, region.right, region.bottom),
    ):
        length = max(right - left, bottom - top)
        for start in range(0, length, dash * 2):
            end = min(start + dash, length)
            if right > left:
                draw.line((left + start, top, left + end, top), fill=colour, width=width)
            else:
                draw.line((left, top + start, left, top + end), fill=colour, width=width)


def hatch_regions(image: Any, regions: list[Region], step: int, width: int) -> Any:
    """The image with red cross-hatching and a light red tint inside each region, so it is clear they are not used."""
    import PIL.Image
    import PIL.ImageDraw

    size = image.size
    lines = PIL.Image.new("RGBA", size, (0, 0, 0, 0))
    drawing = PIL.ImageDraw.Draw(lines)
    for offset in range(-size[1], size[0], step):
        drawing.line((offset, 0, offset + size[1], size[1]), fill=HATCH_COLOUR, width=width)
        drawing.line((offset + size[1], 0, offset, size[1]), fill=HATCH_COLOUR, width=width)
    mask = PIL.Image.new("L", size, 0)
    masking = PIL.ImageDraw.Draw(mask)
    tint = PIL.Image.new("RGBA", size, (0, 0, 0, 0))
    tinting = PIL.ImageDraw.Draw(tint)
    for region in regions:
        masking.rectangle((region.left, region.top, region.right, region.bottom), fill=255)
        tinting.rectangle((region.left, region.top, region.right, region.bottom), fill=DROPPED_TINT)
    clear = PIL.Image.new("RGBA", size, (0, 0, 0, 0))
    layer = PIL.Image.alpha_composite(tint, PIL.Image.composite(lines, clear, mask))
    return PIL.Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def draw_preview(image: Any, kept: list[Region], dropped: list[Region], padding: int = 0) -> Any:
    """The image with each piece outlined in its own colour and numbered in reading order, and the dropped candidates in red.

    A dropped candidate is outlined in red and cross-hatched, so it is clear it will not be used.

    The piece is a solid box. With padding, a dashed box in the same colour shows the crop that is saved.
    """
    import PIL.ImageDraw
    import PIL.ImageFont

    preview = image.convert("RGB")
    longer = max(preview.size)
    line = max(2, longer // 300)
    if dropped:
        preview = hatch_regions(preview, dropped, step=max(10, line * 5), width=max(1, line // 2))
    draw = PIL.ImageDraw.Draw(preview)
    font = PIL.ImageFont.load_default(size=max(14, longer // 40))
    for region in dropped:
        draw.rectangle((region.left, region.top, region.right, region.bottom), outline=DROPPED_COLOUR, width=line)
    for index, region in enumerate(kept):
        colour = piece_colour(index)
        crop = padded(region, padding, *preview.size)
        if padding:
            dashed_rectangle(draw, crop, colour, line, dash=max(6, line * 4))
        draw.rectangle((region.left, region.top, region.right, region.bottom), outline=colour, width=line)
        label = str(index + 1)
        left, top, right, bottom = draw.textbbox((region.left + line, region.top + line), label, font=font)
        draw.rectangle((left - 3, top - 3, right + 3, bottom + 3), fill=colour)
        draw.text((region.left + line, region.top + line), label, fill=LABEL_COLOUR, font=font)
    return preview


def cut_piece(image: Any, region: Region, shape: Any, settings: SplitSettings, background: str) -> Any:
    """Crop one piece out of the image. With a transparent background, everything outside its shape is cleared."""
    import numpy as np
    import PIL.Image
    from skimage import filters

    box = padded(region, round(settings.padding / 100 * max(image.size)), *image.size)
    crop = image.convert("RGB").crop((box.left, box.top, box.right, box.bottom))
    if background != BACKGROUND_TRANSPARENT:
        return crop
    scale = shape.shape[1] / image.size[0]
    left, top = int(box.left * scale), int(box.top * scale)
    right, bottom = max(left + 1, round(box.right * scale)), max(top + 1, round(box.bottom * scale))
    cut = shape[top:bottom, left:right].astype(np.float32)
    cut = filters.gaussian(cut, sigma=1.0)
    alpha = PIL.Image.fromarray((np.clip(cut, 0, 1) * 255).astype(np.uint8)).resize(
        crop.size, PIL.Image.Resampling.BILINEAR
    )
    result = crop.convert("RGBA")
    result.putalpha(alpha)
    return result
