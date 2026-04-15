# -*- coding: utf-8 -*-
"""Design tokens — single source of truth for colors, dimensions, typography."""
from __future__ import annotations


class Theme:
    """All tokens are class attributes (strings) so .tokens() can collect them
    for QSS substitution. Numeric values are stored as strings without units —
    the QSS template adds `px`/`pt` where needed."""

    # ── Brand (lime palette, 11 steps) ────────────────────────────────
    primary_50  = "#F9FBE0"
    primary_100 = "#F0F4C2"
    primary_200 = "#E6ED9B"
    primary_300 = "#DCE773"
    primary_400 = "#C8D924"
    primary_500 = "#A6CA15"   # ← BRAND
    primary_600 = "#94B80D"   # hover
    primary_700 = "#7A9C0A"   # pressed; safe brand-as-text on white (5.2:1)
    primary_800 = "#5A7A05"
    primary_900 = "#3F5503"
    primary_950 = "#1F2B01"

    # ── Cool neutrals (slate scale) ───────────────────────────────────
    gray_50  = "#F8FAFC"
    gray_100 = "#F1F5F9"
    gray_200 = "#E2E8F0"
    gray_300 = "#CBD5E1"
    gray_400 = "#94A3B8"   # too dim for headers — use gray_600 instead
    gray_500 = "#64748B"
    gray_600 = "#475569"   # ← section headers (5.7:1 vs white)
    gray_700 = "#334155"
    gray_800 = "#1E293B"
    gray_900 = "#0F172A"   # body text; safe text-on-primary-button

    # ── Semantic ──────────────────────────────────────────────────────
    success    = "#10B981"
    success_bg = "#D1FAE5"
    error      = "#EF4444"
    error_bg   = "#FEE2E2"
    warning    = "#F59E0B"
    warning_bg = "#FEF3C7"
    info       = "#3B82F6"
    info_bg    = "#DBEAFE"

    # ── Surfaces (white with lime hint) ───────────────────────────────
    surface        = "#FFFFFF"
    surface_tinted = "#FCFEF6"   # page bg, ~1% lime mix
    surface_subtle = "#F8FBE8"   # input focus bg, ~3% lime
    sidebar_bg     = "#F4F8E1"   # subtle lime sidebar

    # ── Borders ───────────────────────────────────────────────────────
    border        = "#E2E8F0"
    border_strong = "#CBD5E1"
    border_focus  = "#A6CA15"

    # ── Dimensions (raw values; QSS adds px/pt) ──────────────────────
    radius_sm      = "3"
    radius         = "5"
    radius_md      = "7"
    radius_lg      = "10"
    control_height = "28"   # was 36 — Linear/Raycast style
    control_pad_v  = "4"
    control_pad_h  = "10"

    # ── Typography ────────────────────────────────────────────────────
    font_family        = "Segoe UI Variable, Segoe UI, sans-serif"
    font_mono          = "Cascadia Code, Consolas, Courier New, monospace"
    font_size_xs       = "8"
    font_size_sm       = "8.5"
    font_size_base     = "9"
    font_size_md       = "10"
    font_size_lg       = "12"
    font_weight_normal = "400"
    font_weight_medium = "500"
    font_weight_semi   = "600"
    font_weight_bold   = "700"

    @classmethod
    def tokens(cls) -> dict[str, str]:
        """Return a flat dict of every string class attribute (excludes private and methods)."""
        return {
            k: v
            for k, v in vars(cls).items()
            if not k.startswith("_") and isinstance(v, str)
        }
