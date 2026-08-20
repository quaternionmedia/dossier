"""rad's colour tokens, in two tiers, for a terminal.

`rad/adr/DRAFT-rad-theme-tokens.md` §1: **nothing paints outside the token
layer.** No literal appears in a component, in code, or in an intent — code that
needs a colour reads a token. The split is what makes theming tractable:

    palette tokens   named for what they *are*  -- ink, surface, accent, signal
    role tokens      named for what they *do*   -- wedge_label, hub_stroke,
                                                   focus_ring, and defined in
                                                   terms of palette tokens

**Components reference role tokens only.** A theme redefines the palette and
inherits every role; a theme that must break a role redefines that role, which
makes the exception visible in the diff. `ring.py` therefore asks for roles and
never for a palette entry, and never for a hex.

THE VALUES ARE RAD'S, NOT CHOSEN HERE. The four palettes below are read from
`rad/index.html` — `radical` (the default), `dark`, `light`, `contrast`. Two of
radical's decisions are load-bearing rather than decorative and are preserved:
the ground is a soft deep indigo rather than black, because saturated neon on
`#000` vibrates; and the accent is the only strong hue in ordinary use.

WHAT THIS CANNOT DO. Guarantee a terminal renders them. A 16-colour terminal
will approximate, and one with a light profile will show the dark themes on its
own ground — `contrast` exists for both cases. It also cannot honour
`prefers-color-scheme`: a terminal does not report one, so the default is
`radical` rather than sniffed.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THEME = "radical"

# --- palette tiers, verbatim from rad ---------------------------------------

PALETTES: dict[str, dict[str, str]] = {
    # The house mood: neon accents on a soft deep-indigo ground.
    "radical": {
        "bg": "#14111f", "surface": "#1d1930",
        "ink": "#f4eeff", "ink_dim": "#bdb2d9", "ink_faint": "#6f6689",
        "accent": "#5cf0ff", "signal": "#ff7aa8",
        "calm": "#4ae3d0", "gold": "#ffc861",
    },
    # The same family pulled back for long sessions.
    "dark": {
        "bg": "#0d0f16", "surface": "#161a24",
        "ink": "#eaeef7", "ink_dim": "#a3adc2", "ink_faint": "#5e6675",
        "accent": "#56d8ff", "signal": "#ff7d94",
        "calm": "#4fd8c4", "gold": "#f0c35c",
    },
    "light": {
        "bg": "#f6f4fb", "surface": "#ffffff",
        "ink": "#16131f", "ink_dim": "#514a63", "ink_faint": "#8f8a9e",
        "accent": "#0060a8", "signal": "#b01248",
        "calm": "#0d6b64", "gold": "#74540a",
    },
    # Every pair at >= 7:1, and no decorative transparency.
    "contrast": {
        "bg": "#000000", "surface": "#000000",
        "ink": "#ffffff", "ink_dim": "#f0f0f0", "ink_faint": "#f0f0f0",
        "accent": "#ffffff", "signal": "#ffffff",
        "calm": "#ffffff", "gold": "#ffffff",
    },
}


@dataclass(frozen=True)
class Roles:
    """What a component is allowed to ask for."""

    hub_label: str
    hub_stroke: str
    wedge_label: str
    wedge_label_selected: str
    wedge_label_unavailable: str
    """A wedge in the menu that this host cannot act on.

    A COLOUR LIKE EVERY OTHER ROLE. The first attempt made this a style string
    -- `dim #bdb2d9` -- so that one token could carry both the colour and the
    dimming. Two guards said no, and between them they said why: one asserts
    every role resolves to a colour, and the other extracts `[bold? #hex]` from
    the rendered markup and checks it against the role layer. A style string
    failed the first and *slipped past* the second, which is the worse half --
    a colour reaching the screen that the guard could no longer see. So the
    dimming moved into the palette as `ink_faint`, where a theme can set it.

    `contrast` sets it equal to `ink_dim`: >= 7:1 is that theme's whole point
    and a fainter ink would break it. The dotted border is what says
    "unavailable" there, and it is what says it on a sixteen-colour terminal
    too -- which is why the state was never left to colour in the first place.
    """
    focus_ring: str
    submenu_mark: str
    hint: str
    cost: str
    panel_bg: str
    panel_border: str


def roles(theme: str = DEFAULT_THEME) -> Roles:
    """Role tokens for a theme, defined in terms of its palette.

    Every role resolves through the palette, so a new theme is a palette and
    nothing else — which is the property that makes the four themes one
    contract rather than four stylesheets.
    """
    p = PALETTES.get(theme) or PALETTES[DEFAULT_THEME]
    return Roles(
        hub_label=p["ink_dim"],
        hub_stroke=p["accent"],
        wedge_label=p["ink_dim"],
        wedge_label_selected=p["ink"],
        wedge_label_unavailable=p["ink_faint"],
        focus_ring=p["accent"],
        submenu_mark=p["calm"],
        hint=p["ink_dim"],
        cost=p["gold"],
        # The pop-over's own ground. It cannot be transparent: the ring floats
        # over a dashboard, and text over text is unreadable however pretty the
        # colours are. `surface` is the palette entry that exists for exactly
        # this -- something raised off the background.
        panel_bg=p["surface"],
        panel_border=p["accent"],
    )


def themes() -> tuple[str, ...]:
    return tuple(PALETTES)
