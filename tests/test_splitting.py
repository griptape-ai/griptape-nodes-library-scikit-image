from griptape_nodes_library_scikit_image.splitting import (
    BACKGROUND_CHOICES,
    BACKGROUND_PAPER,
    Region,
    SplitSettings,
    padded,
    piece_file_name,
    reading_order,
    validate_settings,
)

GOOD = SplitSettings(sensitivity=0.12, join_distance=1.5, min_size=3.0, padding=1.5, ignore_corner_pieces=True)


def test_paper_is_a_background_choice():
    assert BACKGROUND_PAPER in BACKGROUND_CHOICES


def test_good_settings_have_no_problems():
    assert validate_settings(GOOD) == []


def test_each_bad_setting_is_named_in_its_message():
    bad = SplitSettings(sensitivity=2.0, join_distance=-1, min_size=0, padding=-5, ignore_corner_pieces=True)
    problems = validate_settings(bad)
    assert len(problems) == 4
    for label in ("Sensitivity", "Join distance", "Minimum size", "Padding"):
        assert any(label in problem for problem in problems)


def test_reading_order_goes_left_to_right_then_top_to_bottom():
    top_left = Region(0, 0, 100, 100)
    top_right = Region(300, 10, 400, 110)
    middle = Region(150, 220, 250, 320)
    bottom = Region(0, 500, 100, 600)
    assert reading_order([bottom, top_right, middle, top_left]) == [top_left, top_right, middle, bottom]


def test_reading_order_of_nothing_is_nothing():
    assert reading_order([]) == []


def test_padding_stays_inside_the_image():
    assert padded(Region(5, 5, 50, 50), 20, 100, 60) == Region(0, 0, 70, 60)


def test_piece_file_names_are_numbered_from_one():
    assert piece_file_name("pose", 1, 4) == "pose.0001.png"
    assert piece_file_name("pose", 12, 2) == "pose.12.png"
