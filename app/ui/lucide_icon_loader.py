"""Path and SVG-loading helpers for Lucide icon resources."""

import sys
from functools import lru_cache
from pathlib import Path


def resolve_lucide_icons_dir(
    *,
    module_file: str | Path | None = None,
    frozen: bool | None = None,
    meipass: str | Path | None = None,
) -> Path:
    """Resolve the Lucide icon directory for dev and frozen runtimes."""
    base_file = Path(module_file) if module_file is not None else Path(__file__)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    bundle_root = (
        Path(getattr(sys, "_MEIPASS"))
        if meipass is None and is_frozen
        else Path(meipass)
        if meipass is not None
        else None
    )
    if is_frozen and bundle_root is not None:
        return bundle_root / "resources" / "icons" / "lucide"
    return base_file.resolve().parent.parent.parent / "resources" / "icons" / "lucide"


@lru_cache(maxsize=128)
def read_lucide_svg(name: str, icons_dir: str | Path | None = None) -> str:
    """Read one SVG icon source by name from the Lucide resource directory."""
    base_dir = resolve_lucide_icons_dir() if icons_dir is None else Path(icons_dir)
    path = base_dir / f"{name}.svg"
    if not path.exists():
        raise FileNotFoundError(f"Lucide icon not found: {name} (looked in {path})")
    return path.read_text(encoding="utf-8")
