import numpy as np
import PIL.Image
import pytest

from griptape_nodes_library_scikit_image import tools


def drawing():
    """Uneven-lit grey paper with a dark blue square and an orange square."""
    paper = np.full((200, 300, 3), 225, dtype=np.float32)
    paper *= np.linspace(1.0, 0.8, 300)[None, :, None]
    paper[40:100, 40:120] = (40, 90, 200)
    paper[120:180, 170:260] = (210, 120, 40)
    return PIL.Image.fromarray(paper.astype(np.uint8))


def test_a_colour_is_read_from_hex_with_or_without_the_hash():
    assert tools.parse_colour("#2a8fd6") == (42, 143, 214)
    assert tools.parse_colour("fff") == (255, 255, 255)


def test_a_bad_colour_says_how_to_write_one():
    with pytest.raises(ValueError, match="#rrggbb"):
        tools.parse_colour("blue")


def test_flattening_makes_the_paper_even():
    flat = np.asarray(tools.flatten_paper(drawing(), 1.0)).astype(int)
    assert abs(int(flat[10:30, 10:30].mean()) - int(flat[10:30, 270:290].mean())) <= 3
    assert flat[10:30, 10:30].mean() > 240


def test_lines_to_alpha_is_just_the_alpha_white_on_marks_and_black_on_paper():
    result = tools.lines_to_alpha(drawing(), 0.12, 0.15)
    assert result.mode == "L"
    alpha = np.asarray(result)
    assert alpha[10:30, 10:30].max() == 0
    assert alpha[60:80, 60:100].min() == 255
    assert alpha[140:160, 190:240].min() == 255


def test_lines_to_alpha_on_a_blank_page_says_there_are_no_marks():
    with pytest.raises(ValueError, match="No marks"):
        tools.lines_to_alpha(PIL.Image.new("RGB", (100, 100), (230, 230, 230)), 0.12, 0.15)


def test_trimming_crops_to_the_marks_plus_padding():
    trimmed = tools.trim_to_content(drawing(), 0.12, 0.0)
    assert 215 <= trimmed.size[0] <= 225
    assert 135 <= trimmed.size[1] <= 145


def test_a_blank_image_has_no_marks_to_trim_or_trace():
    blank = PIL.Image.new("RGB", (100, 100), (230, 230, 230))
    with pytest.raises(ValueError, match="No marks"):
        tools.trim_to_content(blank, 0.12, 0.0)
    with pytest.raises(ValueError, match="No marks"):
        tools.lines_to_svg(blank, 0.12, 1.0, "#000000")


def test_aligning_recovers_a_known_shift():
    image = drawing()
    moved = image.transform(image.size, PIL.Image.Transform.AFFINE, (1, 0, -6, 0, 1, 4))
    _aligned, down, right, angle, factor = tools.align_images(moved, image)
    assert (round(down), round(right)) == (4, -6)
    assert (angle, factor) == (0.0, 1.0)


def test_comparing_an_image_with_itself_scores_one_and_shows_no_difference():
    score, difference = tools.compare_images(drawing(), drawing(), 3.0)
    assert score == pytest.approx(1.0)
    assert np.asarray(difference).max() == 0


def test_comparing_different_images_scores_lower():
    score, difference = tools.compare_images(drawing(), tools.flatten_paper(drawing(), 1.0), 3.0)
    assert score < 0.99
    assert np.asarray(difference).max() > 0


def test_equalizing_keeps_the_size():
    assert tools.equalize_contrast(drawing(), 0.02, 1.0).size == drawing().size


def test_boiling_makes_the_frames_asked_for_and_each_differs():
    frames = tools.boiling_frames(drawing(), 4, 0.5, 3.0, 1)
    assert len(frames) == 4
    assert all(frame.size == drawing().size for frame in frames)
    assert not np.array_equal(np.asarray(frames[0]), np.asarray(frames[1]))


def test_boiling_with_the_same_seed_gives_the_same_frames():
    first = tools.boiling_frames(drawing(), 2, 0.5, 3.0, 7)
    again = tools.boiling_frames(drawing(), 2, 0.5, 3.0, 7)
    assert np.array_equal(np.asarray(first[1]), np.asarray(again[1]))


def test_inbetweens_make_the_frames_asked_for():
    image = drawing()
    other = image.transform(image.size, PIL.Image.Transform.AFFINE, (1, 0, -12, 0, 1, 6))
    frames = tools.inbetween_frames(image, other, 3)
    assert len(frames) == 3
    assert all(frame.size == image.size for frame in frames)


def test_the_svg_has_one_path_per_shape_and_a_preview_of_the_same_size():
    svg, count, preview = tools.lines_to_svg(drawing(), 0.12, 1.0, "#112233")
    assert svg.startswith("<svg") and 'fill="#112233"' in svg
    assert count == 2
    assert svg.count("M") >= count
    assert preview.size == drawing().size
    marks = np.asarray(preview)
    assert tuple(marks[70, 80]) == (0x11, 0x22, 0x33)
    assert tuple(marks[10, 10]) == (40, 40, 40) or tuple(marks[10, 10]) == (255, 255, 255)


def scribbles():
    """A page of random blobs and strokes, with enough detail to line up by."""
    from skimage import draw

    rng = np.random.default_rng(3)
    page = np.full((300, 400), 0.92)
    for _ in range(40):
        rows, columns = draw.ellipse(
            rng.integers(30, 270), rng.integers(30, 370), rng.integers(4, 18), rng.integers(4, 18)
        )
        keep = (rows >= 0) & (rows < 300) & (columns >= 0) & (columns < 400)
        page[rows[keep], columns[keep]] = rng.uniform(0.1, 0.5)
    return PIL.Image.fromarray((np.stack([page] * 3, axis=-1) * 255).astype(np.uint8))


def agreement(first, second):
    one = np.asarray(first.convert("L")).astype(float)[50:-50, 50:-50]
    other = np.asarray(second.convert("L")).astype(float)[50:-50, 50:-50]
    return float(np.corrcoef(one.ravel(), other.ravel())[0, 1])


def moved(image, angle, factor, right=0.0, down=0.0):
    centre = np.array(image.size) / 2
    from skimage import transform

    mapping = (
        transform.SimilarityTransform(translation=-centre)
        + transform.SimilarityTransform(scale=factor, rotation=np.deg2rad(angle))
        + transform.SimilarityTransform(translation=centre + (right, down))
    )
    pixels = np.asarray(image).astype(float) / 255
    warped = np.stack(
        [transform.warp(pixels[..., c], mapping.inverse, order=1, mode="edge") for c in range(3)], axis=-1
    )
    return PIL.Image.fromarray((warped * 255).astype(np.uint8))


def test_identical_images_come_back_unchanged_in_every_mode():
    page = scribbles()
    for mode in tools.ALIGN_CHOICES:
        _aligned, down, right, angle, factor = tools.align_images(page, page, mode)
        assert (round(down), round(right), angle, factor) == (0, 0, 0.0, 1.0)


def test_aligning_can_undo_a_turn():
    page = scribbles()
    turned = moved(page, 10.0, 1.0)
    aligned, _down, _right, angle, factor = tools.align_images(turned, page, tools.ALIGN_ROTATE)
    assert angle == pytest.approx(-10.0, abs=1.0)
    assert factor == 1.0
    assert agreement(aligned, page) > 0.9
    assert agreement(aligned, page) > agreement(turned, page) + 0.3


def test_aligning_can_undo_a_turn_a_scale_and_a_shift():
    page = scribbles()
    changed = moved(page, -8.0, 1.06, right=5.0, down=-3.0)
    aligned, _down, _right, angle, factor = tools.align_images(changed, page, tools.ALIGN_SCALE)
    assert angle == pytest.approx(8.0, abs=1.5)
    assert factor == pytest.approx(1 / 1.06, abs=0.02)
    assert agreement(aligned, page) > 0.85


def test_shift_only_mode_never_turns_the_image():
    page = scribbles()
    _aligned, _down, _right, angle, factor = tools.align_images(moved(page, 10.0, 1.0), page, tools.ALIGN_SHIFT)
    assert (angle, factor) == (0.0, 1.0)


def test_an_odd_size_is_cropped_by_a_pixel_for_video():
    odd = PIL.Image.new("RGB", (387, 540))
    assert tools.make_even(odd).size == (386, 540)
    assert tools.make_even(PIL.Image.new("RGB", (300, 201))).size == (300, 200)


def test_an_even_size_is_left_alone():
    even = PIL.Image.new("RGB", (400, 540))
    assert tools.make_even(even) is even
