"""Align Images' widget: what Python sends it, and that the numbers it shows match the alignment."""

import base64
import io

import pytest

pytest.importorskip("skimage")

import numpy as np  # noqa: E402
import PIL.Image  # noqa: E402
from griptape_nodes.traits.widget import Widget  # noqa: E402
from skimage import draw  # noqa: E402

from griptape_nodes_library_scikit_image import align_images, tools  # noqa: E402


def reference():
    rng = np.random.default_rng(3)
    page = np.full((300, 400), 0.92)
    for _ in range(40):
        rows, columns = draw.ellipse(
            rng.integers(30, 270), rng.integers(30, 370), rng.integers(4, 18), rng.integers(4, 18)
        )
        page[np.clip(rows, 0, 299), np.clip(columns, 0, 399)] = rng.uniform(0.1, 0.5)
    return PIL.Image.fromarray((np.stack([page] * 3, axis=-1) * 255).astype(np.uint8))


def moved():
    """The reference with its content slid 8 pixels left and 12 down, so it must move 8 right and 12 up."""
    return reference().transform(reference().size, PIL.Image.Transform.AFFINE, (1, 0, 8, 0, 1, -12))


@pytest.fixture
def node(monkeypatch):
    images = {"moved.png": moved(), "reference.png": reference()}
    monkeypatch.setattr(align_images, "open_image", lambda location, label: images[location])
    node = align_images.AlignImages(name="node")
    monkeypatch.setattr(node, "publish_update_to_parameter", lambda name, value: None)
    node.set_parameter_value("mode", tools.ALIGN_SHIFT)
    node.set_parameter_value("image_to_align", {"value": "moved.png"})
    node.set_parameter_value("reference", {"value": "reference.png"})
    return node


def decoded(data_url):
    prefix, _, encoded = data_url.partition(",")
    assert prefix.startswith("data:image/")
    return PIL.Image.open(io.BytesIO(base64.b64decode(encoded)))


def test_the_widget_is_synced_and_not_saved_with_the_workflow(node):
    parameter = node.get_parameter_by_name(align_images.EDITOR)
    (widget,) = parameter.find_elements_by_type(Widget)
    assert widget.synced_parameters == align_images.SYNCED_PARAMETERS
    assert parameter.serializable is False
    for name in align_images.SYNCED_PARAMETERS:
        assert node.get_parameter_by_name(name) is not None


def test_the_widget_gets_the_pictures_the_maps_and_the_numbers(node):
    data = node.get_parameter_value(align_images.EDITOR)
    assert (data["width"], data["height"]) == (400, 300)
    for key in ("reference_data", "aligned_data"):
        assert decoded(data[key]).size == (400, 300)
    for key in ("before_map", "after_map"):
        assert decoded(data[key]).mode == "L"
    assert data["shift_right"] == pytest.approx(8, abs=0.5)
    assert data["shift_down"] == pytest.approx(-12, abs=0.5)
    assert data["after"] > data["before"]
    assert data["after"] > 0.95


def test_the_preview_size_reduces_the_pictures_but_not_the_numbers(node):
    node.set_parameter_value("preview_size", 200)
    data = node.get_parameter_value(align_images.EDITOR)
    assert decoded(data["aligned_data"]).size == (200, 150)
    assert (data["shift_right"], data["shift_down"]) == pytest.approx((8, -12), abs=1.0)  # in full-size pixels


def test_the_mode_aligns_again_and_the_gain_does_not(node, monkeypatch):
    calls = []
    original = tools.align_preview
    monkeypatch.setattr(tools, "align_preview", lambda *args: calls.append(args) or original(*args))
    node.set_parameter_value("gain", 10.0)
    assert calls == []
    node.set_parameter_value("mode", tools.ALIGN_ROTATE)
    assert len(calls) == 1 and calls[0][2] == tools.ALIGN_ROTATE


def test_without_both_images_the_widget_is_empty(node):
    node.set_parameter_value("reference", None)
    data = node.get_parameter_value(align_images.EDITOR)
    assert (data["reference_data"], data["aligned_data"], data["width"]) == ("", "", 0)


def test_a_saved_workflow_refreshes_the_widget(node):
    node.set_parameter_value(align_images.EDITOR, align_images.default_widget_value(), initial_setup=True)
    node.set_parameter_value("reference", {"value": "reference.png"}, initial_setup=True)
    assert node.get_parameter_value(align_images.EDITOR)["aligned_data"].startswith("data:image/jpeg")


def test_the_rotation_and_scale_are_outputs_of_the_node(node):
    for name in ("shift_down", "shift_right", "rotation", "scale"):
        assert node.get_parameter_by_name(name) is not None


def test_a_run_gives_the_same_numbers_the_widget_showed(node):
    published = {}
    node.publish = lambda name, image: published.update({name: image})
    node.load_input = lambda name=None, label=None: reference()
    node.run(moved())
    data = node.get_parameter_value(align_images.EDITOR)
    assert node.parameter_output_values["shift_right"] == pytest.approx(data["shift_right"], abs=0.5)
    assert node.parameter_output_values["shift_down"] == pytest.approx(data["shift_down"], abs=0.5)
    assert published["output"].size == reference().size
