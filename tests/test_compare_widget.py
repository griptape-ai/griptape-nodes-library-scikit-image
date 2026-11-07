"""Compare Images' widget: what Python sends it, and that its map agrees with the node's saved difference."""

import base64
import io

import pytest

pytest.importorskip("skimage")

import numpy as np  # noqa: E402
import PIL.Image  # noqa: E402
from griptape_nodes.traits.widget import Widget  # noqa: E402

from griptape_nodes_library_scikit_image import compare_images, tools  # noqa: E402


def picture(shift: int = 0):
    rng = np.random.default_rng(5)
    page = rng.integers(200, 255, (300, 400, 3), dtype=np.uint8)
    page[100 + shift : 200 + shift, 120:260] = (30, 60, 200)
    return PIL.Image.fromarray(page)


@pytest.fixture
def node(monkeypatch):
    images = {"a.png": picture(), "b.png": picture(shift=40)}
    monkeypatch.setattr(
        compare_images, "browser_url", lambda value: f"http://example/{value['value']}" if value else ""
    )
    monkeypatch.setattr(compare_images, "open_image", lambda location, label: images[location])
    node = compare_images.CompareImages(name="node")
    monkeypatch.setattr(node, "publish_update_to_parameter", lambda name, value: None)
    node.set_parameter_value("image", {"value": "a.png"})
    node.set_parameter_value("other", {"value": "b.png"})
    return node


def decoded_map(data):
    prefix = "data:image/png;base64,"
    assert data["map_url"].startswith(prefix)
    return PIL.Image.open(io.BytesIO(base64.b64decode(data["map_url"][len(prefix) :])))


def test_the_widget_is_synced_with_the_gain_and_the_preview_size(node):
    (widget,) = node.get_parameter_by_name(compare_images.EDITOR).find_elements_by_type(Widget)
    assert widget.synced_parameters == compare_images.SYNCED_PARAMETERS
    for name in compare_images.SYNCED_PARAMETERS:
        assert node.get_parameter_by_name(name) is not None


def test_the_widget_is_not_saved_with_the_workflow(node):
    assert node.get_parameter_by_name(compare_images.EDITOR).serializable is False


def test_the_widget_gets_both_images_and_the_map(node):
    data = node.get_parameter_value(compare_images.EDITOR)
    assert (data["image_url"], data["other_url"]) == ("http://example/a.png", "http://example/b.png")
    assert (data["width"], data["height"]) == (400, 300)
    assert 0 <= data["score"] < 1
    assert decoded_map(data).mode == "L"


def test_the_preview_size_sets_the_size_the_images_are_compared_at(node):
    node.set_parameter_value("preview_size", 200)
    assert decoded_map(node.get_parameter_value(compare_images.EDITOR)).size == (200, 150)
    node.set_parameter_value("preview_size", 2048)
    assert decoded_map(node.get_parameter_value(compare_images.EDITOR)).size == (400, 300)  # never enlarged


def test_the_gain_does_not_compare_again(node):
    before = node.get_parameter_value(compare_images.EDITOR)
    node.set_parameter_value("gain", 10.0)
    assert node.get_parameter_value(compare_images.EDITOR) == before


def test_the_widget_map_matches_the_saved_difference_once_the_gain_is_applied():
    score, saved = tools.compare_images(picture(), picture(shift=40), 3.0)
    preview_score, preview = tools.compare_preview(picture(), picture(shift=40), 400)
    applied = np.clip(np.asarray(preview).astype(float) / 255 * 3.0, 0, 1) * 255
    assert preview_score == pytest.approx(score)
    assert (
        np.abs(applied - np.asarray(saved)[..., 0].astype(float)).max() <= 3.0
    )  # one level of 8-bit rounding, times gain


def test_one_image_is_shown_alone(node):
    node.set_parameter_value("other", None)
    data = node.get_parameter_value(compare_images.EDITOR)
    assert data["image_url"] == "http://example/a.png" and data["other_url"] == ""
    assert data["map_url"] == "" and data["score"] is None


def test_no_images_leave_the_widget_empty(node):
    node.set_parameter_value("image", None)
    node.set_parameter_value("other", None)
    data = node.get_parameter_value(compare_images.EDITOR)
    assert (data["image_url"], data["width"], data["map_url"]) == ("", 0, "")


def test_a_saved_workflow_refreshes_the_widget(node):
    node.set_parameter_value(compare_images.EDITOR, compare_images.default_widget_value(), initial_setup=True)
    node.set_parameter_value("other", {"value": "b.png"}, initial_setup=True)
    assert node.get_parameter_value(compare_images.EDITOR)["other_url"] == "http://example/b.png"
