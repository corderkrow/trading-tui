"""coderkrow dark — Textual theme built from the brand tokens.

Source of truth: `.ai/rules/brand/RULES.md` §2 (dark variant values).
Brand accents (`--ck-teal*`, `--ck-cyan`) keep the same hue in every theme;
only bg/surface/ink/muted change per variant.
"""

from __future__ import annotations

from textual.theme import Theme

# Brand tokens (dark variant) — desk v2: same teal/cyan hues, lower chroma,
# lifted ground. Tuned for long sessions (halation + contrast fatigue).
INK = "#d8d6cf"  # warm off-white — primary text (--ck-ink, dark)
BG = "#191a18"  # lifted graphite — app background (--ck-bg, dark)
SURFACE = "#212220"  # panels, inputs, modals (--ck-surface, dark)
MUTED = "#8b8a83"  # secondary text, captions (--ck-muted, dark)
TEAL = "#1a595a"  # brand accent (--ck-teal) — hue unchanged
TEAL_MID = "#3f9a99"  # interactive elements, hover (--ck-teal-mid)
TEAL_LIGHT = "#57bcbb"  # badges, highlights, inline accents (--ck-teal-light)
CYAN = "#5fc9c7"  # signal only: active/on states, focus (--ck-cyan)
DANGER = "#e0918a"  # destructive/down — AA on dark (was #c83c3c, 3.75:1)
SUCCESS = "#6fbf8b"  # up/success — luminance-matched to DANGER
WARNING = "#d9a441"  # functional warning amber — no brand token exists
PANEL = "#1e2321"  # permitted derivation: --ck-teal at 8% over surface

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
    success=SUCCESS,
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
    "SUCCESS",
    "WARNING",
]
