"""Split Image's widget: what Python sends it, what it sends back, and the geometry it draws with."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("skimage")

import numpy as np  # noqa: E402
import PIL.Image  # noqa: E402
from griptape_nodes.traits.widget import Widget  # noqa: E402

from griptape_nodes_library_scikit_image import split_image  # noqa: E402
from griptape_nodes_library_scikit_image.splitting import Candidate, Region, classify, excluded_boxes  # noqa: E402

WIDGET_DIR = Path(__file__).parent.parent / "griptape_nodes_library_scikit_image" / "widgets" / "SplitImage"


def sheet():
    paper = np.full((240, 320, 3), 230, dtype=np.uint8)
    paper[40:120, 50:130] = (40, 90, 200)
    paper[130:210, 180:290] = (210, 120, 40)
    return PIL.Image.fromarray(paper)


@pytest.fixture
def node(monkeypatch):
    monkeypatch.setattr(split_image, "browser_url", lambda value: "http://example/sheet.png")
    monkeypatch.setattr(split_image.SplitImage, "_load_image", lambda self, location: sheet())
    node = split_image.SplitImage(name="node")
    monkeypatch.setattr(node, "publish_update_to_parameter", lambda name, value: None)
    node.set_parameter_value("image", {"value": "sheet.png"})
    return node


def test_the_widget_is_synced_with_the_settings(node):
    (widget,) = node.get_parameter_by_name(split_image.EDITOR).find_elements_by_type(Widget)
    assert widget.synced_parameters == split_image.SYNCED_PARAMETERS
    for name in split_image.SYNCED_PARAMETERS:
        assert node.get_parameter_by_name(name) is not None


def kept_boxes(node):
    """The boxes of the pieces the widget would show, worked out from the candidates it was sent."""
    data = node.get_parameter_value(split_image.EDITOR)
    candidates = [Candidate(Region(*c["box"]), c["blob"], c["tight"], c["edges"]) for c in data["candidates"]]
    kept, _ = classify(
        candidates, node.get_parameter_value("min_size"), node.get_parameter_value("ignore_corner_pieces")
    )
    return [candidate.region.box for candidate in kept]


def test_the_widget_gets_the_image_and_the_boxes_found(node):
    data = node.get_parameter_value(split_image.EDITOR)
    assert data["image_url"] == "http://example/sheet.png"
    assert (data["width"], data["height"]) == (320, 240)
    assert len(kept_boxes(node)) == 2
    for candidate in data["candidates"]:
        assert len(candidate["box"]) == 4 and candidate["colour"].startswith("#")
        assert {"blob", "tight", "edges"} <= candidate.keys()
    assert node.parameter_output_values[split_image.EDITOR] == data


def test_a_setting_that_changes_the_blobs_scans_again(node):
    before = len(node.get_parameter_value(split_image.EDITOR)["candidates"])
    node.set_parameter_value("join_distance", 30.0)
    assert len(node.get_parameter_value(split_image.EDITOR)["candidates"]) < before


def test_minimum_size_and_corner_pieces_only_change_what_the_widget_keeps(node):
    sent = node.get_parameter_value(split_image.EDITOR)["candidates"]
    node.set_parameter_value("min_size", 60.0)
    assert node.get_parameter_value(split_image.EDITOR)["candidates"] == sent
    assert kept_boxes(node) == []


def test_the_boxes_switched_off_survive_a_scan(node):
    box = kept_boxes(node)[0]
    node.set_parameter_value(split_image.EDITOR, {**node.get_parameter_value(split_image.EDITOR), "excluded": [box]})
    node.set_parameter_value("padding", 2.0)
    assert node.get_parameter_value(split_image.EDITOR)["excluded"] == [box]


def test_a_saved_workflow_refreshes_the_image_url(node):
    stale = {**split_image.default_widget_value(), "image_url": "http://old/session.png"}
    node.set_parameter_value(split_image.EDITOR, stale, initial_setup=True)
    node.set_parameter_value("image", {"value": "sheet.png"}, initial_setup=True)
    assert node.get_parameter_value(split_image.EDITOR)["image_url"] == "http://example/sheet.png"


def test_no_image_leaves_the_widget_empty(node):
    node.set_parameter_value("image", None)
    data = node.get_parameter_value(split_image.EDITOR)
    assert (data["image_url"], data["width"], data["candidates"]) == ("", 0, [])


def test_the_excluded_boxes_are_read_and_bad_ones_are_ignored():
    assert excluded_boxes({"excluded": [[1, 2, 3, 4], ["5", 6, 7, 8], [1, 2], "x", None]}) == {
        (1, 2, 3, 4),
        (5, 6, 7, 8),
    }
    assert excluded_boxes(None) == set()
    assert excluded_boxes({"excluded": None}) == set()


def test_a_region_gives_its_box_in_the_order_the_widget_uses():
    assert Region(1, 2, 3, 4).box == [1, 2, 3, 4]


def test_a_run_leaves_out_the_pieces_switched_off(node, tmp_path, monkeypatch):
    monkeypatch.setattr(split_image.SplitImage, "_scan_sequence", lambda self, *args: None)
    box = kept_boxes(node)[0]
    node.set_parameter_value(split_image.EDITOR, {**node.get_parameter_value(split_image.EDITOR), "excluded": [box]})
    node.set_parameter_value("output_dir", str(tmp_path / "pieces"))
    node._split()
    assert node.parameter_output_values["count"] == 1
    assert sorted(path.name for path in (tmp_path / "pieces").iterdir()) == ["pieces.0001.png"]


def test_a_run_with_every_piece_switched_off_says_so(node, tmp_path):
    boxes = kept_boxes(node)
    node.set_parameter_value(split_image.EDITOR, {**node.get_parameter_value(split_image.EDITOR), "excluded": boxes})
    node.set_parameter_value("output_dir", str(tmp_path / "pieces"))
    with pytest.raises(Exception, match="switched off"):
        node._split()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run the widget's JavaScript.")
def test_the_widget_geometry_matches_the_node():
    script = """
import { paddedBox, numbering, pieceAt, toggleExcluded, fitSize } from "%s";
const out = {
  padded: paddedBox([100, 100, 200, 200], 1.5, 320, 240),
  clamped: paddedBox([2, 2, 318, 238], 20, 320, 240),
  numbers: numbering([{ box: [0, 0, 5, 5] }, { box: [6, 0, 9, 5] }, { box: [10, 0, 15, 5] }], [[6, 0, 9, 5]]).map((p) => p.number),
  inner: pieceAt([{ box: [0, 0, 100, 100], id: "outer" }, { box: [10, 10, 20, 20], id: "inner" }], 15, 15).id,
  outer: pieceAt([{ box: [0, 0, 100, 100], id: "outer" }, { box: [10, 10, 20, 20], id: "inner" }], 50, 50).id,
  none: pieceAt([{ box: [0, 0, 10, 10] }], 10, 10),
  on: toggleExcluded([], [1, 2, 3, 4]),
  off: toggleExcluded([[1, 2, 3, 4]], [1, 2, 3, 4]),
  fit: fitSize(400, 400, 200, 100),
  empty: fitSize(400, 400, 0, 0),
};
console.log(JSON.stringify(out));
""" % (WIDGET_DIR / "_boxes.js")
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    out = json.loads(done.stdout)
    padding = round(1.5 / 100 * 320)
    assert out["padded"] == [100 - padding, 100 - padding, 200 + padding, 200 + padding]
    assert out["clamped"] == [0, 0, 320, 240]
    assert out["numbers"] == [1, None, 2]
    assert (out["inner"], out["outer"], out["none"]) == ("inner", "outer", None)
    assert (out["on"], out["off"]) == ([[1, 2, 3, 4]], [])
    assert (out["fit"], out["empty"]) == ([400, 200], [0, 0])


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run the widget's JavaScript.")
@pytest.mark.parametrize("min_size", [0.1, 3.0, 8.0, 20.0])
@pytest.mark.parametrize("ignore_corner_pieces", [True, False])
def test_the_widget_picks_the_same_pieces_in_the_same_order_as_the_node(min_size, ignore_corner_pieces):
    rng = np.random.default_rng(7)
    candidates = []
    for _ in range(60):
        left, top = int(rng.integers(0, 700)), int(rng.integers(0, 500))
        width, height = int(rng.integers(5, 200)), int(rng.integers(5, 200))
        tight = float(rng.uniform(1, 30))
        candidates.append(
            Candidate(
                Region(left, top, left + width, top + height),
                tight + float(rng.uniform(0, 5)),
                tight,
                int(rng.integers(0, 4)),
            )
        )
    kept, dropped = classify(candidates, min_size, ignore_corner_pieces)
    script = """
import { classify } from "%s";
const input = JSON.parse(process.argv[1]);
const { kept, dropped } = classify(input.candidates, input.minSize, input.ignoreCornerPieces);
console.log(JSON.stringify({ kept: kept.map((c) => c.box), dropped: dropped.map((c) => c.box) }));
""" % (WIDGET_DIR / "_boxes.js")
    payload = json.dumps(
        {
            "candidates": [
                {"box": c.region.box, "blob": c.blob_size, "tight": c.tight_size, "edges": c.edges} for c in candidates
            ],
            "minSize": min_size,
            "ignoreCornerPieces": ignore_corner_pieces,
        }
    )
    done = subprocess.run(
        ["node", "--input-type=module", "-e", script, payload], capture_output=True, text=True, check=True
    )
    out = json.loads(done.stdout)
    assert out["kept"] == [c.region.box for c in kept]
    assert out["dropped"] == [c.region.box for c in dropped]
    assert kept  # the cases are not all empty


def test_switching_a_piece_off_updates_the_count(node, monkeypatch):
    published = []
    monkeypatch.setattr(node, "publish_update_to_parameter", lambda name, value: published.append((name, value)))
    data = node.get_parameter_value(split_image.EDITOR)
    boxes = kept_boxes(node)
    assert len(boxes) == 2
    node.set_parameter_value(split_image.EDITOR, {**data, "excluded": [boxes[0]]})
    assert node.parameter_output_values["count"] == 1
    assert ("count", 1) in published
    node.set_parameter_value(split_image.EDITOR, {**data, "excluded": []})
    assert node.parameter_output_values["count"] == 2


def test_the_count_follows_the_size_filter_without_scanning_again(node):
    node.set_parameter_value("min_size", 60.0)
    assert node.parameter_output_values["count"] == 0
