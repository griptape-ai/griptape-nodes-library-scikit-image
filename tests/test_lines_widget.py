"""Lines to SVG's widget: what Python sends it, and that it matches the saved SVG."""

import pytest

pytest.importorskip("skimage")

import numpy as np  # noqa: E402
import PIL.Image  # noqa: E402
from griptape_nodes.traits.widget import Widget  # noqa: E402

from griptape_nodes_library_scikit_image import lines_to_svg  # noqa: E402


def drawing():
    paper = np.full((200, 300, 3), 235, dtype=np.uint8)
    paper[40:120, 50:130] = (30, 30, 40)
    paper[130:180, 180:290] = (30, 30, 40)
    return PIL.Image.fromarray(paper)


@pytest.fixture
def node(monkeypatch):
    image = drawing()
    monkeypatch.setattr(lines_to_svg, "browser_url", lambda value: "http://example/drawing.png")
    monkeypatch.setattr(lines_to_svg, "open_image", lambda location, label: image)
    node = lines_to_svg.LinesToSvg(name="node")
    monkeypatch.setattr(node, "publish_update_to_parameter", lambda name, value: None)
    node.set_parameter_value("image", {"value": "drawing.png"})
    return node


def test_the_widget_is_synced_with_the_settings(node):
    (widget,) = node.get_parameter_by_name(lines_to_svg.EDITOR).find_elements_by_type(Widget)
    assert widget.synced_parameters == lines_to_svg.SYNCED_PARAMETERS
    for name in lines_to_svg.SYNCED_PARAMETERS:
        assert node.get_parameter_by_name(name) is not None


def test_the_widget_gets_the_image_and_the_trace(node):
    data = node.get_parameter_value(lines_to_svg.EDITOR)
    assert data["image_url"] == "http://example/drawing.png"
    assert (data["width"], data["height"]) == (300, 200)
    assert data["count"] == 2
    assert data["path"].count("M") == 2 and data["message"] == ""


def test_the_widget_path_is_the_one_saved_in_the_svg(node):
    data = node.get_parameter_value(lines_to_svg.EDITOR)
    saved, count = lines_to_svg.tools.lines_to_svg(drawing(), 0.12, 1.0, "#000000")
    assert f'd="{data["path"]}"' in saved
    assert count == data["count"]


def test_a_setting_that_changes_the_trace_traces_again(node):
    node.set_parameter_value("sensitivity", 0.9)
    data = node.get_parameter_value(lines_to_svg.EDITOR)
    assert data["path"] == "" and "No marks" in data["message"]


def test_the_fill_colour_does_not_trace_again(node):
    before = node.get_parameter_value(lines_to_svg.EDITOR)
    node.set_parameter_value("fill_colour", "#ff0000")
    assert node.get_parameter_value(lines_to_svg.EDITOR) == before


def test_no_image_leaves_the_widget_empty(node):
    node.set_parameter_value("image", None)
    data = node.get_parameter_value(lines_to_svg.EDITOR)
    assert (data["image_url"], data["path"], data["count"]) == ("", "", 0)


def test_a_saved_workflow_refreshes_the_image_url(node):
    stale = {**lines_to_svg.default_widget_value(), "image_url": "http://old/session.png"}
    node.set_parameter_value(lines_to_svg.EDITOR, stale, initial_setup=True)
    node.set_parameter_value("image", {"value": "drawing.png"}, initial_setup=True)
    assert node.get_parameter_value(lines_to_svg.EDITOR)["image_url"] == "http://example/drawing.png"


def test_the_trace_is_not_saved_with_the_workflow(node):
    assert node.get_parameter_by_name(lines_to_svg.EDITOR).serializable is False
