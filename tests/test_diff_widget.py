"""Diff Images' widget: what Python sends it, and that its map agrees with the node's saved difference."""

import base64
import io

import pytest

pytest.importorskip("skimage")

import numpy as np  # noqa: E402
import PIL.Image  # noqa: E402
from griptape_nodes.traits.widget import Widget  # noqa: E402

from griptape_nodes_library_scikit_image import diff_images, tools  # noqa: E402


def picture(shift: int = 0):
    rng = np.random.default_rng(5)
    page = rng.integers(200, 255, (300, 400, 3), dtype=np.uint8)
    page[100 + shift : 200 + shift, 120:260] = (30, 60, 200)
    return PIL.Image.fromarray(page)


@pytest.fixture
def node(monkeypatch):
    images = {"a.png": picture(), "b.png": picture(shift=40)}
    monkeypatch.setattr(diff_images, "browser_url", lambda value: f"http://example/{value['value']}" if value else "")
    monkeypatch.setattr(diff_images, "open_image", lambda location, label: images[location])
    node = diff_images.DiffImages(name="node")
    monkeypatch.setattr(node, "publish_update_to_parameter", lambda name, value: None)
    node.set_parameter_value("image", {"value": "a.png"})
    node.set_parameter_value("other", {"value": "b.png"})
    return node


def decoded_map(data):
    prefix = "data:image/png;base64,"
    assert data["map_url"].startswith(prefix)
    return PIL.Image.open(io.BytesIO(base64.b64decode(data["map_url"][len(prefix) :])))


def test_the_widget_is_synced_with_the_gain_and_the_preview_size(node):
    (widget,) = node.get_parameter_by_name(diff_images.EDITOR).find_elements_by_type(Widget)
    assert widget.synced_parameters == diff_images.SYNCED_PARAMETERS
    for name in diff_images.SYNCED_PARAMETERS:
        assert node.get_parameter_by_name(name) is not None


def test_the_widget_is_not_saved_with_the_workflow(node):
    assert node.get_parameter_by_name(diff_images.EDITOR).serializable is False


def test_the_widget_gets_both_images_and_the_map(node):
    data = node.get_parameter_value(diff_images.EDITOR)
    assert (data["image_url"], data["other_url"]) == ("http://example/a.png", "http://example/b.png")
    assert (data["width"], data["height"]) == (400, 300)
    assert 0 <= data["score"] < 1
    assert decoded_map(data).mode == "L"


def test_the_preview_size_sets_the_size_the_images_are_compared_at(node):
    node.set_parameter_value("preview_size", 200)
    assert decoded_map(node.get_parameter_value(diff_images.EDITOR)).size == (200, 150)
    node.set_parameter_value("preview_size", 2048)
    assert decoded_map(node.get_parameter_value(diff_images.EDITOR)).size == (400, 300)  # never enlarged


def test_the_gain_does_not_compare_again(node):
    before = node.get_parameter_value(diff_images.EDITOR)
    node.set_parameter_value("gain", 10.0)
    assert node.get_parameter_value(diff_images.EDITOR) == before


def test_the_widget_map_matches_the_saved_difference_once_the_gain_is_applied():
    score, saved = tools.compare_view(picture(), picture(shift=40), "Difference", 3.0, 50.0)
    preview_score, preview = tools.compare_preview(picture(), picture(shift=40), 400)
    applied = np.clip(np.asarray(preview).astype(float) / 255 * 3.0, 0, 1) * 255
    assert preview_score == pytest.approx(score)
    assert (
        np.abs(applied - np.asarray(saved)[..., 0].astype(float)).max() <= 3.0
    )  # one level of 8-bit rounding, times gain


def test_one_image_is_shown_alone(node):
    node.set_parameter_value("other", None)
    data = node.get_parameter_value(diff_images.EDITOR)
    assert data["image_url"] == "http://example/a.png" and data["other_url"] == ""
    assert data["map_url"] == "" and data["score"] is None


def test_no_images_leave_the_widget_empty(node):
    node.set_parameter_value("image", None)
    node.set_parameter_value("other", None)
    data = node.get_parameter_value(diff_images.EDITOR)
    assert (data["image_url"], data["width"], data["map_url"]) == ("", 0, "")


def test_a_saved_workflow_refreshes_the_widget(node):
    node.set_parameter_value(diff_images.EDITOR, diff_images.default_widget_value(), initial_setup=True)
    node.set_parameter_value("other", {"value": "b.png"}, initial_setup=True)
    assert node.get_parameter_value(diff_images.EDITOR)["other_url"] == "http://example/b.png"


@pytest.mark.parametrize("view", ["Wipe", "A", "B", "Difference", "Heat"])
def test_a_run_saves_the_view_the_widget_shows(node, view):
    published = {}
    node.publish = lambda name, image: published.update({name: image})
    node.load_input = lambda name="image", label="Image": picture(shift=40)
    node.set_parameter_value("view", view)
    node.set_parameter_value("wipe", 25.0)
    node.run(picture())
    shown = np.asarray(published["output"]).astype(int)
    first, second = np.asarray(picture()).astype(int), np.asarray(picture(shift=40)).astype(int)
    match view:
        case "A":
            assert np.abs(shown - first).max() <= 1
        case "B":
            assert np.abs(shown - second).max() <= 1
        case "Wipe":
            cut = round(400 * 0.25)
            assert np.abs(shown[:, :cut] - first[:, :cut]).max() <= 1
            assert np.abs(shown[:, cut:] - second[:, cut:]).max() <= 1
        case "Difference":
            assert shown.shape == first.shape and np.array_equal(shown[..., 0], shown[..., 1])  # gray
            assert shown.max() > 0
        case "Heat":
            changed = (shown != first).any(axis=-1)
            assert changed.any() and not changed.all()  # tinted where they differ, untouched elsewhere
            assert (shown[changed][:, 0] >= first[changed][:, 0]).all()  # towards red
    assert node.parameter_output_values["similarity"] < 1


def test_the_view_defaults_to_the_difference_and_the_wipe_position_is_shown_only_for_wipe(node):
    assert node.get_parameter_value("view") == "Difference"
    wipe = node.get_parameter_by_name("wipe")
    assert wipe.hide is True
    node.set_parameter_value("view", "Wipe")
    assert wipe.hide is False
    node.set_parameter_value("view", "Heat")
    assert wipe.hide is True


def test_the_view_and_wipe_position_are_synced_with_the_widget(node):
    assert {"view", "wipe"} <= set(diff_images.SYNCED_PARAMETERS)
    assert node.get_parameter_by_name("view") is not None


def test_an_unknown_view_is_refused():
    with pytest.raises(ValueError, match="Unknown view"):
        tools.compare_view(picture(), picture(), "Sideways", 3.0, 50.0)


def test_every_wipe_position_the_widget_can_send_is_accepted(node):
    for tenth in range(1001):
        node.set_parameter_value("wipe", round(tenth / 10, 1))
    assert node.get_parameter_value("wipe") == 100.0


@pytest.mark.parametrize("gain", [0.5, 2.3, 3.0, 7.7, 20.0])
def test_the_gain_accepts_a_value_between_the_old_half_steps(node, gain):
    node.set_parameter_value("gain", gain)
    assert node.get_parameter_value("gain") == gain
