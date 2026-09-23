"""coderkrow dark — Textual theme built from the brand tokens.

Source of truth: `.ai/rules/brand/RULES.md` §2 (dark variant values).
Brand accents (`--ck-teal*`, `--ck-cyan`) keep the same hue in every theme;
only bg/surface/ink/muted change per variant.
"""

from __future__ import annotations

from textual.theme import Theme

# Brand tokens (dark variant)
INK = "#e8e6df"  # warm off-white — primary text (--ck-ink, dark)
BG = "#111110"  # near-black — app background (--ck-bg, dark)
SURFACE = "#1a1a18"  # panels, inputs, modals (--ck-surface, dark)
MUTED = "#888780"  # secondary text, captions (--ck-muted, dark)
TEAL = "#1a595a"  # brand accent (--ck-teal)
TEAL_MID = "#2e7f80"  # interactive elements, hover (--ck-teal-mid)
TEAL_LIGHT = "#3bb8ba"  # badges, highlights, inline accents (--ck-teal-light)
CYAN = "#00d1d4"  # signal only: active/on states, focus (--ck-cyan)
DANGER = "#c83c3c"  # destructive/error (brand.html "don't" red)
WARNING = "#fabd2f"  # functional warning amber — no brand token exists
PANEL = "#1a1f1d"  # permitted derivation: --ck-teal at 8% over surface

CODERKROW_DARK = Theme(
    name="coderkrow dark",
    primary=TEAL_MID,  # buttons, cursor fills, interactive chrome
    secondary=TEAL_LIGHT,  # badges, highlights, inline accents
    accent=CYAN,  # focus borders, footer keys, active states
    foreground=INK,
    background=BG,
    surface=SURFACE,
    panel=PANEL,
    error=DANGER,
    warning=WARNING,
    success=TEAL_LIGHT,
    dark=True,
    variables={
        "text": INK,
        "text-muted": MUTED,
    },
)

__all__ = [
    "CODERKROW_DARK",
    "BG",
    "SURFACE",
    "INK",
    "MUTED",
    "TEAL",
    "TEAL_MID",
    "TEAL_LIGHT",
    "CYAN",
    "DANGER",
    "WARNING",
]
