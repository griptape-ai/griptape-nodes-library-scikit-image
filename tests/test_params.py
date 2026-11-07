"""Tests for build_output_directory."""

from __future__ import annotations

import pathlib
from unittest import mock

import pytest
from griptape_nodes.files.directory import DirectoryDestination
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy

from griptape_nodes_library_scikit_image.params import build_output_directory


def build(value: object) -> tuple[DirectoryDestination, mock.Mock]:
    node = mock.Mock()
    node.get_parameter_value.return_value = value
    param = mock.Mock()
    return build_output_directory(node, param, "output_dir"), param


class TestBuildOutputDirectory:
    def test_plain_name_goes_through_the_situation(self) -> None:
        destination, param = build("pieces")

        assert destination is param.build_directory.return_value

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_value_goes_through_the_situation(self, value: object) -> None:
        destination, param = build(value)

        assert destination is param.build_directory.return_value

    @pytest.mark.parametrize("name", ["~old_renders", "~tmp"])
    def test_name_starting_with_a_tilde_goes_through_the_situation(self, name: str) -> None:
        destination, param = build(name)

        assert destination is param.build_directory.return_value

    def test_absolute_path_is_used_as_given(self, tmp_path: pathlib.Path) -> None:
        destination, param = build(str(tmp_path / "pieces"))

        param.build_directory.assert_not_called()
        assert destination._directory._dir_path == str(tmp_path / "pieces")
        assert destination._existing_dir_policy == ExistingFilePolicy.OVERWRITE

    def test_home_path_is_expanded(self) -> None:
        destination, _ = build("~/pieces")

        assert destination._directory._dir_path == str(pathlib.Path("~/pieces").expanduser())

    def test_file_uri_is_used_as_given(self, tmp_path: pathlib.Path) -> None:
        destination, param = build((tmp_path / "pieces").as_uri())

        param.build_directory.assert_not_called()
        assert destination._directory._dir_path == str(tmp_path / "pieces")

    def test_web_address_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot save to"):
            build("https://example.com/out")
