import importlib
import json
from pathlib import Path
from typing import Any

import pytest

LIBRARY = json.loads((Path(__file__).parent.parent / "griptape-nodes-library.json").read_text())


@pytest.mark.parametrize("node", LIBRARY["nodes"], ids=lambda node: node["class_name"])
def test_every_node_in_the_library_json_can_be_imported(node):
    module = importlib.import_module(node["file_path"].removesuffix(".py").replace("/", "."))
    assert hasattr(module, node["class_name"])


def test_every_node_file_is_listed_once():
    listed = [node["file_path"] for node in LIBRARY["nodes"]]
    assert len(listed) == len(set(listed))


def sheet():
    import numpy as np
    import PIL.Image

    paper = np.full((240, 320, 3), 230, dtype=np.uint8)
    paper[40:120, 50:130] = (40, 90, 200)
    paper[130:210, 180:290] = (210, 120, 40)
    return PIL.Image.fromarray(paper)


def load_nodes():
    nodes = []
    for entry in LIBRARY["nodes"]:
        module = importlib.import_module(entry["file_path"].removesuffix(".py").replace("/", "."))
        nodes.append(getattr(module, entry["class_name"]))
    return nodes


def test_every_node_can_be_created():
    for cls in load_nodes():
        assert cls(name="node").get_parameter_by_name(getattr(cls, "INPUT_NAME", "image")) is not None


def test_every_image_node_runs_with_its_default_settings(tmp_path):

    from griptape_nodes_library_scikit_image.node_base import ImageNode

    path = tmp_path / "sheet.png"
    sheet().save(path)
    ran = []
    for cls in load_nodes():
        if not issubclass(cls, ImageNode):
            continue
        node: Any = cls(name="node")
        published = {}
        node.load_input = lambda name="image", label="Image": sheet()
        node.publish = lambda name, image, published=published: published.update({name: image})
        if hasattr(node, "_svg_file"):
            node._svg_file = type(
                "File",
                (),
                {
                    "build_file": lambda self: type(
                        "Dest", (), {"write_bytes": lambda self, data: type("Saved", (), {"location": "x.svg"})()}
                    )()
                },
            )()
        node.run(sheet())
        assert published or node.parameter_output_values.get("svg"), cls.__name__
        ran.append(cls.__name__)
    assert "FlattenPaper" in ran
    assert "LinesToSvg" in ran


def test_the_frame_nodes_render_with_their_default_settings(tmp_path):
    from griptape.artifacts.image_url_artifact import ImageUrlArtifact

    from griptape_nodes_library_scikit_image.node_base import FramesNode

    path = tmp_path / "sheet.png"
    sheet().save(path)
    rendered = {}
    for cls in load_nodes():
        if not issubclass(cls, FramesNode):
            continue
        node = cls(name="node")
        if node.get_parameter_by_name("other") is not None:
            node.set_parameter_value("other", ImageUrlArtifact(value=str(path)))
        assert node.check_settings() == []
        rendered[cls.__name__] = node.render(sheet())
    assert len(rendered["BoilingLines"]) == 8
    assert len(rendered["MakeInbetweens"]) == 3


def test_the_frame_nodes_make_the_size_even_by_default():
    from griptape_nodes_library_scikit_image.node_base import FramesNode

    for cls in load_nodes():
        if issubclass(cls, FramesNode):
            assert cls(name="node").get_parameter_value("even_size") is True


def stub_publishing(node):
    published = []
    node.publish_update_to_parameter = lambda name, value: published.append((name, value))
    return published


def test_boiling_lines_reads_its_settings_from_its_parameters():
    from griptape_nodes_library_scikit_image.boiling_lines import BoilingLines

    node = BoilingLines(name="node")
    assert node.settings() == {"frame_count": 8, "amplitude": 0.3, "wobble_size": 2.0, "seed": 1}
    node.set_parameter_value("amplitude", 1.5)
    node.set_parameter_value("seed", 7)
    assert node.settings() == {"frame_count": 8, "amplitude": 1.5, "wobble_size": 2.0, "seed": 7}
    assert node.check_settings() == []


def test_the_sliders_refuse_a_value_outside_their_range():
    from griptape_nodes_library_scikit_image.boiling_lines import BoilingLines

    node = BoilingLines(name="node")
    with pytest.raises(ValueError, match="between 2 and 96"):
        node.set_parameter_value("frame_count", 500)
    assert node.settings()["frame_count"] == 8
    assert node.check_settings() == []


def test_changing_a_parameter_updates_the_widget():
    from griptape_nodes_library_scikit_image.boiling_lines import BoilingLines

    node = BoilingLines(name="node")
    published = stub_publishing(node)
    node.set_parameter_value("wobble_size", 6.0)
    assert node.get_parameter_value("boil")["wobble_size"] == 6.0
    assert [name for name, _ in published] == ["boil"]
    node.set_parameter_value("wobble_size", 6.0)
    assert len(published) == 1  # the widget already has it, so nothing more is sent


def test_changing_the_widget_updates_the_parameters_and_publishes_the_widget_first():
    from griptape_nodes_library_scikit_image.boiling_lines import BoilingLines

    node = BoilingLines(name="node")
    published = stub_publishing(node)
    widget = {**node.get_parameter_value("boil"), "amplitude": 2.5, "seed": 42, "frame": 4, "view": "noise"}
    node.set_parameter_value("boil", widget)  # as the editor does when the widget changes
    assert node.get_parameter_value("amplitude") == 2.5
    assert node.get_parameter_value("seed") == 42
    assert node.get_parameter_value("frame_count") == 8
    assert [name for name, _ in published] == ["boil", "amplitude", "seed"]
    node.set_parameter_value("boil", widget)
    assert len(published) == 3  # the parameters already match, so nothing more is sent


def test_the_widget_and_the_parameters_do_not_chase_each_other():
    from griptape_nodes_library_scikit_image.boiling_lines import BoilingLines

    node = BoilingLines(name="node")
    published = stub_publishing(node)
    node.set_parameter_value("amplitude", 3.0)
    node.set_parameter_value("boil", node.get_parameter_value("boil"))
    node.set_parameter_value("amplitude", 3.0)
    assert [name for name, _ in published] == ["boil"]


def test_copying_the_widget_onto_the_parameters_never_sends_the_widget_an_old_value():
    from griptape_nodes_library_scikit_image.boiling_lines import BoilingLines

    node: Any = BoilingLines(name="node")
    pushed = []
    node.publish_update_to_parameter = lambda name, value: pushed.append(dict(value)) if name == "boil" else None
    node.set_parameter_value(
        "boil", {**node.get_parameter_value("boil"), "amplitude": 2.5, "seed": 42, "frame_count": 20}
    )
    assert pushed
    assert all((p["amplitude"], p["seed"], p["frame_count"]) == (2.5, 42, 20) for p in pushed)


def test_boiling_lines_hands_the_widget_a_url_the_size_of_the_image_and_its_settings(monkeypatch):
    import PIL.Image

    from griptape_nodes_library_scikit_image import boiling_lines

    monkeypatch.setattr(boiling_lines, "browser_url", lambda value: "http://example/image.png")
    monkeypatch.setattr(boiling_lines, "open_image", lambda location, label: PIL.Image.new("RGB", (387, 540)))
    node = boiling_lines.BoilingLines(name="node")
    node.set_parameter_value("amplitude", 1.25)
    published = stub_publishing(node)
    node._show_image_in_widget({"value": "sheet.png"})
    data = node.get_parameter_value("boil")
    assert (data["image_url"], data["width"], data["height"]) == ("http://example/image.png", 387, 540)
    assert data["amplitude"] == 1.25
    assert published and published[0][0] == "boil"
    node._show_image_in_widget({"value": "sheet.png"})
    assert len(published) == 1  # nothing changed, so nothing is sent again


@pytest.mark.parametrize("widget", LIBRARY["widgets"], ids=lambda widget: widget["name"])
def test_every_widget_is_registered_in_the_library_json_and_its_file_exists(widget):
    assert (Path(__file__).parent.parent / widget["path"]).is_file()
