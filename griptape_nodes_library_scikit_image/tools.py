"""The image operations behind the nodes. Each takes and returns PIL images and raises ValueError with a message an artist can act on.

Every import of numpy, scipy and scikit-image is inside a function, so this module imports even where they are missing.
"""

from __future__ import annotations

from typing import Any

from griptape_nodes_library_scikit_image.runner import estimate_background, find_marks
from griptape_nodes_library_scikit_image.splitting import CompareView, Region, padded

WORK_SIZE = 900
SVG_WORK_SIZE = 1600
HEAT_COLOUR = (255, 60, 60)  # the Heat view of Diff Images, as in widgets/DiffImages
HEAT_ALPHA = 0.85
FLOW_SIZE = 512
MAX_SVG_POINTS = 400_000
ALIGN_SIZE = 512
ALIGN_BLUR = 2.0
ALIGN_REFINEMENTS = ((4.0, 1.0, 0.06, 0.02), (1.0, 0.25, 0.015, 0.005), (0.3, 0.1, 0.006, 0.002))
BAND_LOW = 5
BAND_HIGH = 20
ALIGN_SHIFT = "shift"
ALIGN_ROTATE = "shift and rotate"
ALIGN_SCALE = "shift, rotate and scale"
ALIGN_CHOICES = [ALIGN_SHIFT, ALIGN_ROTATE, ALIGN_SCALE]


def parse_colour(text: str) -> tuple[int, int, int]:
    """A colour written as #rrggbb or rrggbb."""
    value = text.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        if len(value) != 6:
            raise ValueError
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        msg = f"'{text}' is not a colour. Write it as #rrggbb, such as #2a8fd6."
        raise ValueError(msg) from None


def rgb_array(image: Any) -> Any:
    """A float RGB array in 0..1. Transparent pixels are composited on white."""
    import numpy as np
    import PIL.Image

    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        backdrop = PIL.Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        backdrop.alpha_composite(rgba)
        image = backdrop
    return np.asarray(image.convert("RGB")).astype(np.float32) / 255


def to_image(array: Any) -> Any:
    """A PIL image from a float array in 0..1 with 3 or 4 channels."""
    import numpy as np
    import PIL.Image

    return PIL.Image.fromarray((np.clip(array, 0, 1) * 255 + 0.5).astype(np.uint8))


def grey(pixels: Any) -> Any:
    return pixels[..., 0] * 0.299 + pixels[..., 1] * 0.587 + pixels[..., 2] * 0.114


def paper_of(pixels: Any) -> Any:
    return estimate_background(pixels, max(4, max(pixels.shape[:2]) // 60))


def ink_alpha(pixels: Any, sensitivity: float, softness: float) -> Any:
    """How much each pixel is a mark rather than paper, from 0 to 1.

    It is 0 where the pixel is as the paper around it, rises from the sensitivity, and reaches 1 a softness above it.
    """
    import numpy as np

    differs = np.abs(1 - pixels / np.maximum(paper_of(pixels), 1e-3)).max(axis=-1)
    return np.clip((differs - sensitivity) / max(softness, 1e-3), 0, 1)


def flatten_paper(image: Any, strength: float) -> Any:
    """Take the shadows and gradients out of the light, so the paper or backdrop is even and the paper turns white."""
    import numpy as np

    pixels = rgb_array(image)
    flat = np.clip(pixels / np.maximum(paper_of(pixels), 1e-3), 0, 1)
    return to_image(pixels + strength * (flat - pixels))


def lines_to_alpha(image: Any, sensitivity: float, softness: float) -> Any:
    """The alpha of the marks on the paper as a greyscale image: white on a mark, black on paper."""
    import numpy as np
    import PIL.Image

    alpha = ink_alpha(rgb_array(image), sensitivity, softness)
    if not float(alpha.max()) > 0:
        msg = "No marks were found. Lower 'Sensitivity' to pick up fainter marks."
        raise ValueError(msg)
    return PIL.Image.fromarray((alpha * 255 + 0.5).astype(np.uint8), mode="L")


def trim_to_content(image: Any, sensitivity: float, padding: float) -> Any:
    """Crop to the box that holds every mark, plus padding as a percentage of the longer side."""
    import numpy as np
    import PIL.Image

    width, height = image.size
    scale = min(1.0, WORK_SIZE / max(width, height))
    small = image.convert("RGB").resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), PIL.Image.Resampling.LANCZOS
    )
    rows, columns = np.nonzero(find_marks(np.asarray(small), sensitivity))
    if rows.size == 0:
        msg = "No marks were found. Lower 'Sensitivity' to pick up fainter marks."
        raise ValueError(msg)
    region = Region(
        left=int(columns.min() / scale),
        top=int(rows.min() / scale),
        right=min(width, int((columns.max() + 1) / scale) + 1),
        bottom=min(height, int((rows.max() + 1) / scale) + 1),
    )
    box = padded(region, round(padding / 100 * max(width, height)), width, height)
    return image.convert("RGBA" if image.mode == "RGBA" else "RGB").crop((box.left, box.top, box.right, box.bottom))


def equalize_contrast(image: Any, clip_limit: float, strength: float) -> Any:
    """Even out the contrast across the image in small regions (CLAHE), on lightness only so colours stay put."""
    import numpy as np
    from skimage import color, exposure

    pixels = rgb_array(image)
    lab = color.rgb2lab(pixels)
    kernel = max(8, max(pixels.shape[:2]) // 8)
    lightness = exposure.equalize_adapthist(lab[..., 0] / 100, kernel_size=kernel, clip_limit=clip_limit) * 100
    lab[..., 0] = lab[..., 0] + strength * (lightness - lab[..., 0])
    return to_image(np.clip(color.lab2rgb(lab), 0, 1))


def _similarity(shape: tuple[int, ...], angle: float, factor: float, down: float = 0.0, right: float = 0.0) -> Any:
    """A turn by an angle in degrees and a scale about the centre of an image, then a shift."""
    import numpy as np
    from skimage import transform

    centre = np.array([shape[1], shape[0]]) / 2
    return (
        transform.SimilarityTransform(translation=-centre)
        + transform.SimilarityTransform(scale=factor, rotation=np.deg2rad(angle))
        + transform.SimilarityTransform(translation=centre + (right, down))
    )


def _warp(layer: Any, transformation: Any) -> Any:
    import numpy as np
    from skimage import transform

    return np.asarray(transform.warp(layer, transformation.inverse, order=1, mode="edge"))


def _turn_and_scale_candidates(reference: Any, moving: Any, allow_scale: bool) -> list[tuple[float, float]]:
    """Guesses at the turn and scale that line moving up with the reference, from their log-polar spectra.

    The spectrum cannot tell a turn from the same turn plus half a circle, and the signs depend on conventions, so every
    reading is a candidate and the caller picks the one that lines up best.
    """
    import numpy as np
    from skimage import filters, registration, transform

    height, width = reference.shape
    window = filters.window("hann", reference.shape)
    # Band-pass first, or the spectra are dominated by their lowest frequencies, which are the same for any turn or scale.
    banded = [filters.difference_of_gaussians(layer, BAND_LOW, BAND_HIGH) for layer in (reference, moving)]
    spectra = [np.abs(np.fft.fftshift(np.fft.fft2(layer * window))) for layer in banded]
    radius = min(height, width) // 8
    polar = [
        np.asarray(transform.warp_polar(spectrum, radius=radius, output_shape=reference.shape, scaling="log", order=0))[
            : height // 2
        ]
        for spectrum in spectra
    ]
    shifts = registration.phase_cross_correlation(
        polar[0],
        polar[1],
        upsample_factor=10,
        normalization=None,  # pyright: ignore[reportArgumentType]
    )[0]
    angle = 360 / height * float(shifts[0])
    factor = float(np.exp(float(shifts[1]) / (width / np.log(radius)))) if allow_scale else 1.0
    angles = {angle, -angle, angle + 180, 180 - angle, angle - 180, -angle - 180}
    factors = {factor, 1 / factor} if allow_scale else {1.0}
    return [(a, f) for a in angles for f in factors]


def _match(
    sharp: tuple[Any, Any], blurred: tuple[Any, Any], angle: float, factor: float
) -> tuple[float, tuple[float, float]]:
    """How well moving lines up with the reference after a turn, a scale and the best shift. Returns score and shift.

    The shift is found on the sharp images, which have the detail it needs. The score is taken on the blurred ones.
    """
    import numpy as np
    from scipy import ndimage
    from skimage import registration

    transformation = _similarity(sharp[1].shape, angle, factor)
    shift = registration.phase_cross_correlation(sharp[0], _warp(sharp[1], transformation), upsample_factor=10)[0]
    shifted = ndimage.shift(_warp(blurred[1], transformation), shift, order=1, mode="nearest")
    result = (float(shift[0]), float(shift[1]))
    if float(shifted.std()) < 1e-6 or float(blurred[0].std()) < 1e-6:
        return -1.0, result
    return float(np.corrcoef(blurred[0].ravel(), shifted.ravel())[0, 1]), result


def align_images(image: Any, reference: Any, mode: str = ALIGN_SHIFT) -> tuple[Any, float, float, float, float]:
    """Line an image up with a reference by shifting it, and if the mode allows, turning and scaling it too.

    Returns the aligned image, the shift in pixels down and right, the turn in degrees, and the scale. The turn and scale
    are about the centre of the image, and the shift is what is left after them. If nothing lines the images up better
    than they already are, the image comes back unchanged.
    """
    import numpy as np
    import PIL.Image
    from skimage import filters, transform

    full_reference = rgb_array(reference)
    full_moving = rgb_array(image.resize(reference.size, PIL.Image.Resampling.LANCZOS))
    height, width = full_reference.shape[:2]
    scale = min(1.0, ALIGN_SIZE / max(height, width))
    size = (max(1, round(height * scale)), max(1, round(width * scale)))
    small_reference = np.asarray(transform.resize(grey(full_reference), size, order=1))
    small_moving = np.asarray(transform.resize(grey(full_moving), size, order=1))
    # Score on slightly blurred images, so a small error in the turn still scores better than a large one.
    blurred_reference = np.asarray(filters.gaussian(small_reference, sigma=ALIGN_BLUR))
    blurred_moving = np.asarray(filters.gaussian(small_moving, sigma=ALIGN_BLUR))

    start = float(np.corrcoef(blurred_reference.ravel(), blurred_moving.ravel())[0, 1])
    best = (start if np.isfinite(start) else -1.0, 0.0, 1.0, 0.0, 0.0)
    candidates = [(0.0, 1.0)]
    if mode != ALIGN_SHIFT:
        candidates += _turn_and_scale_candidates(small_reference, small_moving, mode == ALIGN_SCALE)
    allow_scale = mode == ALIGN_SCALE

    def consider(angle: float, factor: float) -> None:
        nonlocal best
        score, (down, right) = _match(
            (small_reference, small_moving), (blurred_reference, blurred_moving), angle, factor
        )
        if score > best[0]:
            best = (score, angle, factor, down, right)

    for angle, factor in candidates:
        consider(angle, factor)
    if mode != ALIGN_SHIFT:
        for angle_span, angle_step, scale_span, scale_step in ALIGN_REFINEMENTS:
            _score, centre_angle, centre_factor, _down, _right = best
            factors = [
                centre_factor + k * scale_step
                for k in range(-round(scale_span / scale_step), round(scale_span / scale_step) + 1)
            ]
            for angle in np.arange(centre_angle - angle_span, centre_angle + angle_span + 1e-9, angle_step):
                for factor in factors if allow_scale else [1.0]:
                    consider(float(angle), float(factor))
    _score, angle, factor, down, right = best
    down, right = down / scale, right / scale
    transformation = _similarity(full_reference.shape, angle, factor, down, right)
    aligned = np.stack([_warp(full_moving[..., c], transformation) for c in range(3)], axis=-1)
    return to_image(aligned), down, right, angle, factor


def dissimilarity(image: Any, other: Any, longest: int | None = None) -> tuple[float, Any]:
    """How alike two images are, 1 for the same, and where they differ as 1 minus the similarity at every pixel.

    The second image is resized to the first. With `longest`, both are first reduced so their longer side is at most
    that, which is much faster on a big image. The map has the size of the images that were compared.
    """
    import numpy as np
    import PIL.Image
    from skimage import metrics

    if longest is not None and max(image.size) > longest:
        scale = longest / max(image.size)
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))), PIL.Image.Resampling.LANCZOS
        )
    first = rgb_array(image)
    second = rgb_array(other.resize(image.size, PIL.Image.Resampling.LANCZOS))
    outputs = metrics.structural_similarity(first, second, channel_axis=-1, full=True, data_range=1.0)
    return float(outputs[0]), 1 - np.asarray(outputs[-1]).mean(axis=-1)


def compare_view(image: Any, other: Any, view: str, gain: float, wipe: float) -> tuple[float, Any]:
    """How alike two images are, 1 for the same, and the picture the Compare widget shows for `view`.

    Wipe is the first image up to `wipe` percent of the width and the second after it. A and B are the images, the
    second resized to the first. Difference is white where they differ, and Heat tints the first image red there.
    The widget's JavaScript draws the same views from the preview, so what is saved is what it showed.
    """
    import numpy as np
    import PIL.Image

    score, difference = dissimilarity(image, other)
    level = np.clip(difference * gain, 0, 1)[..., None]
    first = rgb_array(image)
    match view:
        case CompareView.DIFFERENCE:
            result = np.repeat(level, 3, axis=-1)
        case CompareView.HEAT:
            result = first * (1 - level * HEAT_ALPHA) + np.array(HEAT_COLOUR) / 255 * level * HEAT_ALPHA
        case CompareView.A:
            result = first
        case CompareView.B:
            result = rgb_array(other.resize(image.size, PIL.Image.Resampling.LANCZOS))
        case CompareView.WIPE:
            result = first.copy()
            second = rgb_array(other.resize(image.size, PIL.Image.Resampling.LANCZOS))
            cut = round(image.width * min(max(wipe, 0), 100) / 100)
            result[:, cut:] = second[:, cut:]
        case _:
            msg = f"Unknown view: {view!r}"
            raise ValueError(msg)
    return score, to_image(result)


def compare_preview(image: Any, other: Any, longest: int) -> tuple[float, Any]:
    """The similarity and the dissimilarity map as an 8-bit grayscale image, for the widget, which applies the gain.

    The images are reduced to `longest` first. The map is white where the images differ most, with no gain applied.
    """
    import numpy as np
    import PIL.Image

    score, difference = dissimilarity(image, other, longest)
    return score, PIL.Image.fromarray((np.clip(difference, 0, 1) * 255).round().astype(np.uint8), mode="L")


def make_even(image: Any) -> Any:
    """The image with an odd width or height cropped by one pixel, because video encoders need even sizes."""
    width, height = image.size
    if width % 2 == 0 and height % 2 == 0:
        return image
    return image.crop((0, 0, width - width % 2, height - height % 2))


def boiling_frames(image: Any, frames: int, amplitude: float, scale: float, seed: int) -> list[Any]:
    """Frames of the same drawing, each warped by a different smooth wobble, like a hand redrawing it.

    The wobble is the one the Boiling Lines widget previews, so the frames match what it shows.
    """
    import numpy as np
    from scipy import ndimage

    from griptape_nodes_library_scikit_image.noise import displacement

    mode = "RGBA" if image.mode == "RGBA" else "RGB"
    pixels = np.asarray(image.convert(mode)).astype(np.float32) / 255
    height, width = pixels.shape[:2]
    longer = max(height, width)
    rows, columns = np.mgrid[0:height, 0:width].astype(np.float32)
    result = []
    for number in range(frames):
        down, right = displacement(height, width, number, seed, amplitude / 100 * longer, scale / 100 * longer)
        coordinates = [rows + down, columns + right]
        warped = np.stack(
            [
                ndimage.map_coordinates(pixels[..., c], coordinates, order=1, mode="nearest")
                for c in range(pixels.shape[2])
            ],
            axis=-1,
        )
        result.append(to_image(warped))
    return result


def inbetween_frames(image: Any, other: Any, count: int) -> list[Any]:
    """Frames that move from one drawing to the next, found by following the motion between them (optical flow)."""
    import numpy as np
    import PIL.Image
    from scipy import ndimage
    from skimage import registration, transform

    first = rgb_array(image)
    second = rgb_array(other.resize(image.size, PIL.Image.Resampling.LANCZOS))
    height, width = first.shape[:2]
    scale = min(1.0, FLOW_SIZE / max(height, width))
    size = (max(1, round(height * scale)), max(1, round(width * scale)))
    down = [np.asarray(transform.resize(grey(p), size, order=1)) for p in (first, second)]
    down_rows, down_columns = registration.optical_flow_tvl1(down[0], down[1])
    flow_rows = np.asarray(transform.resize(down_rows, (height, width), order=1)) / scale
    flow_columns = np.asarray(transform.resize(down_columns, (height, width), order=1)) / scale
    rows, columns = np.mgrid[0:height, 0:width].astype(np.float32)

    def warp(pixels: Any, along: float) -> Any:
        coordinates = [rows + along * flow_rows, columns + along * flow_columns]
        return np.stack(
            [ndimage.map_coordinates(pixels[..., c], coordinates, order=1, mode="nearest") for c in range(3)], axis=-1
        )

    frames = []
    for number in range(1, count + 1):
        t = number / (count + 1)
        frames.append(to_image((1 - t) * warp(first, -t) + t * warp(second, 1 - t)))
    return frames


def trace_lines(image: Any, sensitivity: float, simplify: float) -> tuple[int, int, list[str]]:
    """Trace the outline of every mark. Returns the image's width and height, and one SVG path per outline.

    The paths are in the image's pixels. Raises a ValueError when nothing is found or when there is too much to trace.
    """
    import numpy as np
    import PIL.Image
    from skimage import measure

    width, height = image.size
    scale = min(1.0, SVG_WORK_SIZE / max(width, height))
    small = image.convert("RGB").resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), PIL.Image.Resampling.LANCZOS
    )
    marks = find_marks(np.asarray(small), sensitivity)
    if not marks.any():
        msg = "No marks were found. Lower 'Sensitivity' to pick up fainter marks."
        raise ValueError(msg)
    paths = []
    points = 0
    for contour in measure.find_contours(np.pad(marks.astype(np.float32), 1), 0.5):
        outline = measure.approximate_polygon(contour, tolerance=simplify * scale)
        if len(outline) < 4:
            continue
        points += len(outline)
        if points > MAX_SVG_POINTS:
            msg = "The drawing has too many marks to trace. Raise 'Sensitivity' or 'Simplify'."
            raise ValueError(msg)
        scaled = (outline[:-1] - 1) / scale
        paths.append(" L".join(f"{x:.1f},{y:.1f}" for y, x in scaled).join(("M", " Z")))
    return width, height, paths


def svg_text(width: int, height: int, paths: list[str], colour: str) -> str:
    """The SVG file for traced outlines: one path filled with one colour, with holes left open by the even-odd rule."""
    fill = parse_colour(colour)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<path fill="#{fill[0]:02x}{fill[1]:02x}{fill[2]:02x}" fill-rule="evenodd" d="{" ".join(paths)}"/></svg>'
    )


def lines_to_svg(image: Any, sensitivity: float, simplify: float, colour: str) -> tuple[str, int]:
    """Trace the outline of every mark into an SVG filled with one colour. Returns the SVG text and the shape count."""
    width, height, paths = trace_lines(image, sensitivity, simplify)
    return svg_text(width, height, paths, colour), len(paths)
