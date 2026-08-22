"""Colour tokens, from rad where rad is present and from here where it is not.

**THIS EXISTS SO THAT `rad IS OPTIONAL` IS A FACT RATHER THAN A CLAIM.** It was
a claim: three panels imported `dossier.rad.tokens` at module level, so a panel
could not be drawn at all without rad installed, and the whole application
failed to import. The menu was already optional -- `action_rad_menu` imports it
inside the function -- and the *palette* was not, which nobody had noticed
because both live under `rad/`.

**TWO DIFFERENT THINGS SHARE THAT DIRECTORY.** rad's menu is a mechanism: a way
of choosing, which this organisation uses by choice and could work without. rad's
tokens are a *vocabulary*: names for the roles a colour plays, which everything
drawing anything needs. Making the first optional and the second required is not
inconsistent -- it is the distinction that was already true and unstated.

**AND THE CONTRACT IS NOT WEAKENED BY THE FALLBACK.** The trio uses rad,
documents it, and integrates it; `docs/rad-commands.md` is generated from the
live menu and the diagnostics check the routes resolve. The fallback is what
somebody else gets when they install this without rad, and what proves the
dependency is a choice. A choice nobody could decline would not be one.

WHAT THE FALLBACK IS NOT. A second palette anybody should tune. It is the
smallest set of roles that lets a panel draw, in one neutral ramp, and it is
deliberately plainer than rad's -- a fallback that looked designed would invite
somebody to prefer it, and then there would be two palettes to keep in step.
"""

from __future__ import annotations

from typing import Any

DEFAULT_THEME = "radical"

# Every role `dossier` asks for, and nothing else. Kept minimal on purpose: a
# role added here that rad does not have would be a colour this application
# invented, and the two would drift.
_FALLBACK_ROLES = {
    "hub_label": "#9aa0a6",
    "hub_stroke": "#6db2ff",
    "wedge_label": "#9aa0a6",
    "wedge_label_selected": "#f0f0f0",
    "wedge_label_unavailable": "#6b6b6b",
    "focus_ring": "#6db2ff",
    "submenu_mark": "#5ac8b0",
    "hint": "#9aa0a6",
    "cost": "#e0c069",
    "panel_bg": "#1a1a1a",
    "panel_border": "#6db2ff",
}


class _Roles:
    """The fallback, shaped like rad's `Roles` so callers cannot tell."""

    def __init__(self, values: dict[str, str]) -> None:
        for name, value in values.items():
            setattr(self, name, value)


def rad_is_present() -> bool:
    """Whether rad's own tokens are importable.

    Asked rather than assumed, and reported by `dossier.diagnostics` -- an
    installation running on the fallback should be able to find that out
    without reading a stack trace.
    """
    try:
        import dossier.rad.tokens  # noqa: F401
    except Exception:                              # noqa: BLE001
        return False
    return True


def roles(theme: str = DEFAULT_THEME) -> Any:
    """Role tokens: rad's when it is here, the fallback when it is not.

    An unknown theme falls back to the default rather than raising, which is
    rad's own behaviour -- a panel should not fail to draw because somebody
    typed a theme name wrong.
    """
    try:
        from dossier.rad.tokens import roles as rad_roles

        return rad_roles(theme)
    except Exception:                              # noqa: BLE001
        return _Roles(_FALLBACK_ROLES)


def themes() -> tuple[str, ...]:
    """Every theme available. One, when rad is absent."""
    try:
        from dossier.rad.tokens import themes as rad_themes

        return tuple(rad_themes())
    except Exception:                              # noqa: BLE001
        return (DEFAULT_THEME,)
