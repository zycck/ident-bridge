"""Tests for extracted Lucide icon path and loading helpers."""

from pathlib import Path

import pytest

from app.ui.shared.icons.lucide_icon_loader import read_lucide_svg, resolve_lucide_icons_dir


def test_resolve_lucide_icons_dir_uses_repo_resources_in_dev_mode() -> None:
    result = resolve_lucide_icons_dir(
        module_file="/tmp/project/app/ui/shared/icons/lucide_icon_loader.py",
        frozen=False,
    )
    assert result.as_posix().endswith("/tmp/project/resources/icons/lucide")


def test_resolve_lucide_icons_dir_uses_meipass_when_frozen() -> None:
    result = resolve_lucide_icons_dir(
        module_file="/tmp/project/app/ui/shared/icons/lucide_icon_loader.py",
        frozen=True,
        meipass="/tmp/bundle",
    )
    assert result == Path("/tmp/bundle/resources/icons/lucide")


def test_read_lucide_svg_loads_from_provided_dir(tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()
    (icons_dir / "play.svg").write_text('<svg stroke="currentColor"></svg>', encoding="utf-8")

    assert read_lucide_svg("play", icons_dir) == '<svg stroke="currentColor"></svg>'


def test_read_lucide_svg_missing_icon_raises_helpful_error(tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="Lucide icon not found: missing"):
        read_lucide_svg("missing", icons_dir)
