import pytest

np = pytest.importorskip("numpy")
PIL_Image = pytest.importorskip("PIL.Image")
pytest.importorskip("skimage")

from griptape_nodes_library_scikit_image import runner  # noqa: E402
from griptape_nodes_library_scikit_image.splitting import BACKGROUND_TRANSPARENT, SplitSettings  # noqa: E402

SETTINGS = SplitSettings(sensitivity=0.12, join_distance=3.5, min_size=5.0, padding=1.0, ignore_corner_pieces=True)


def sheet():
    """Grey-lit paper with two dark blobs, one of them in two parts, a speck, a blob on one edge, and one in a corner."""
    height, width = 400, 600
    paper = np.full((height, width, 3), 235, dtype=np.uint8)
    paper[:, :, :] = (paper * np.linspace(1.0, 0.85, width)[None, :, None]).astype(np.uint8)  # uneven light
    paper[50:130, 60:140] = 40
    paper[50:130, 150:170] = 40  # a second part, close to the first
    paper[250:330, 350:450] = 40
    paper[20:23, 300:303] = 40  # a speck
    paper[150:250, 590:600] = 40  # touches the right edge only
    paper[350:400, 550:600] = 40  # in the bottom right corner
    return PIL_Image.fromarray(paper)


def test_it_finds_each_piece_once_in_reading_order():
    found = runner.find_pieces(sheet(), SETTINGS)
    boxes = [(region.left, region.top, region.right, region.bottom) for region, _ in found]
    assert len(boxes) == 3
    left, top, right, bottom = boxes[0]
    assert abs(left - 60) <= 3 and abs(top - 50) <= 3 and abs(right - 170) <= 3 and abs(bottom - 130) <= 3
    assert boxes[1][0] > boxes[0][2]


def test_corner_pieces_come_back_when_asked_for():
    settings = SplitSettings(**{**SETTINGS.__dict__, "ignore_corner_pieces": False})
    assert len(runner.find_pieces(sheet(), settings)) == 4


def test_a_small_join_distance_keeps_close_parts_apart():
    settings = SplitSettings(**{**SETTINGS.__dict__, "join_distance": 0.3, "min_size": 2.5})
    assert len(runner.find_pieces(sheet(), settings)) == 4


def test_a_blank_sheet_has_no_pieces():
    blank = PIL_Image.fromarray(np.full((200, 300, 3), 235, dtype=np.uint8))
    assert runner.find_pieces(blank, SETTINGS) == []


def test_a_cut_piece_is_padded_and_can_be_transparent():
    image = sheet()
    region, shape = runner.find_pieces(image, SETTINGS)[0]
    paper = runner.cut_piece(image, region, shape, SETTINGS, "paper")
    assert paper.mode == "RGB"
    assert paper.size == (region.width + 12, region.height + 12)
    clear = runner.cut_piece(image, region, shape, SETTINGS, BACKGROUND_TRANSPARENT)
    assert clear.mode == "RGBA"
    assert clear.size == paper.size
    assert clear.getpixel((0, 0))[3] == 0


def test_a_scan_reports_the_corner_piece_it_dropped():
    found, dropped = runner.scan_pieces(sheet(), SETTINGS)
    assert len(found) == 3
    assert len(dropped) == 1
    assert dropped[0].left >= 540 and dropped[0].top >= 340


def test_the_preview_marks_kept_and_dropped_pieces():
    image = sheet()
    found, dropped = runner.scan_pieces(image, SETTINGS)
    preview = runner.draw_preview(image, [region for region, _ in found], dropped)
    assert preview.size == image.size
    assert preview.getpixel((found[0][0].left, found[0][0].top)) == runner.piece_colour(0)
    assert preview.getpixel((dropped[0].left, dropped[0].top)) == runner.DROPPED_COLOUR


def test_the_preview_draws_the_padded_crop_around_a_piece():
    image = sheet()
    found, dropped = runner.scan_pieces(image, SETTINGS)
    region = found[0][0]
    preview = runner.draw_preview(image, [region for region, _ in found], dropped, padding=12)
    crop_top = max(0, region.top - 12)
    edge = [preview.getpixel((x, crop_top)) for x in range(max(0, region.left - 12), region.right + 12)]
    assert runner.piece_colour(0) in edge
    assert any(pixel != runner.piece_colour(0) for pixel in edge)  # dashed, so there are gaps


def test_a_dropped_piece_is_cross_hatched():
    image = sheet()
    found, dropped = runner.scan_pieces(image, SETTINGS)
    preview = runner.draw_preview(image, [region for region, _ in found], dropped)
    box = dropped[0]
    inside = [(x, y) for x in range(box.left + 4, box.right - 4) for y in range(box.top + 4, box.bottom - 4)]
    changed = [point for point in inside if preview.getpixel(point) != image.convert("RGB").getpixel(point)]
    assert len(changed) > len(inside) // 20
    untouched = [(x, y) for x in range(5, 30) for y in range(5, 30)]
    assert all(preview.getpixel(point) == image.convert("RGB").getpixel(point) for point in untouched)
