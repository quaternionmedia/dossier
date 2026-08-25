"""One narrative as one animated picture, a frame per step.

**WHY A GIF AND NOT THE SVG TEXTUAL ALREADY EMITS.** A still shows a state; a
narrative is a sequence, and six stills of six steps ask a reader to hold the
order in their head. A GIF renders everywhere with no doubt about it -- no
sanitiser, no `<img>` animation question, no dependence on how a host serves
SVG.

**THE FRAMES ARE RENDERED HERE, NOT RASTERISED FROM THE SVG.** Rasterising
would need cairo, which does not install on every machine this is generated
from -- established rather than assumed: `cairosvg` cannot find
`libcairo-2.dll` on Windows, and `reportlab`'s `renderPM` wants the same
library through `rlPyCairo`. So the SVG that `App.export_screenshot()` produces
is parsed for its cells and drawn with Pillow instead. `export_screenshot` is
public API; nothing here reaches into Textual's compositor.

**THE FONT IS VENDORED, AND THAT IS THE POINT.** Rendering with whatever
monospace font the generating machine happens to have makes the committed
artifact depend on who ran it -- a Linux CI run and this Windows one would
produce visibly different files, and the diff would be noise nobody can read.
`docs/fonts/DejaVuSansMono*.ttf` travels with the repository, `LICENSE_DEJAVU`
sits beside it, and `REUSE.toml` declares both.

**EVERY METRIC IS READ FROM THE DOCUMENT, NOT ASSUMED.** An earlier version
carried a cell size of 8x18 written into this file. The real grid is 12.2 wide
at a 20px face, so text drawn at the font's natural advance drifted across a
line and long runs landed on top of each other. Cell width, line height and
font size come out of the SVG now, and each glyph is placed on its own cell
rather than flowed -- a terminal is a grid, and drawing it as flowed text is
the bug that produced.

WHAT THIS DOES NOT DRAW. The window chrome Rich puts around a screenshot -- the
title bar and its three dots. A frame of decoration repeated forty times is
forty frames of decoration.

WHAT IT CANNOT SEE. Whether the frames tell the story. It composes what it is
given, in the order it is given, and a narrative whose steps are in the wrong
order renders cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Where the vendored faces live, relative to the repository root.
FONTS = Path("docs/fonts")
REGULAR = "DejaVuSansMono.ttf"
BOLD = "DejaVuSansMono-Bold.ttf"

# How long one step is held, in milliseconds. **Leisurely on purpose**: a
# reader is reading the screen, not watching an animation, and a frame that
# turns over before a line can be read is a frame that was not shown.
HOLD_MS = 4000

# What the metrics fall back to when a document does not state them. Only
# reached by a malformed screenshot; a real one carries all three.
FALLBACK_CELL_W = 12.2
FALLBACK_LINE_H = 24.4
FALLBACK_FONT_PX = 20.0

STYLE = re.compile(r"\.terminal-\d+-(r\d+) \{([^}]*)\}")
FILL = re.compile(r"fill:\s*(#[0-9a-fA-F]{6})")
BOLD_RULE = re.compile(r"font-weight:\s*bold")
FONT_SIZE = re.compile(r"font-size:\s*([\d.]+)px")

# **ATTRIBUTES ARE READ BY NAME, NOT BY POSITION.** An earlier pattern matched
# `x y width height` in that order with an optional trailing `fill`, and Rich
# writes cell backgrounds as `fill x y width height shape-rendering` -- so 632
# of 673 rects matched nothing and every cell background was dropped. The
# picture still rendered, which is why it had to be counted rather than looked
# at.
RECT = re.compile(r"<rect ([^>]*)/>")
ATTR = re.compile(r'([a-z-]+)="([^"]*)"')
TEXT = re.compile(
    r'<text class="terminal-\d+-(r\d+)"[^>]*x="([\d.]+)" y="([\d.]+)"[^>]*>'
    r'([^<]*)</text>')

NAMED = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}
NUMERIC = re.compile(r"&#(\d+);")


@dataclass(frozen=True)
class Style:
    """One `rN` class: a colour, and whether it is bold."""

    fill: str = "#c5c8c6"
    bold: bool = False


@dataclass
class Screen:
    """One captured screen, as much of it as a raster needs."""

    width: float
    height: float
    cell_w: float = FALLBACK_CELL_W
    line_h: float = FALLBACK_LINE_H
    font_px: float = FALLBACK_FONT_PX
    rects: list[tuple[float, float, float, float, str]] = field(
        default_factory=list)
    runs: list[tuple[float, float, str, Style]] = field(default_factory=list)
    background: str = "#0c0c0c"


def unescape(text: str) -> str:
    """XML entities, named and numeric.

    **The numeric ones were the omission that showed.** Rich writes every
    non-breaking space as `&#160;`, so a version handling only named entities
    drew the literal characters `&#160;` across every panel of the picture.
    """
    for entity, char in NAMED.items():
        text = text.replace(entity, char)
    return NUMERIC.sub(lambda match: chr(int(match.group(1))), text)


def styles_of(svg: str) -> dict[str, Style]:
    """Every `rN` class the document declares."""
    found: dict[str, Style] = {}
    for name, body in STYLE.findall(svg):
        colour = FILL.search(body)
        found[name] = Style(fill=colour.group(1) if colour else "#c5c8c6",
                            bold=bool(BOLD_RULE.search(body)))
    return found


def _step(values: Iterable[float]) -> float | None:
    """The smallest positive gap between sorted values, or None.

    That is the cell size: every glyph sits on a multiple of it, so the
    smallest distance between two of them is one cell.
    """
    ordered = sorted(set(values))
    gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b > a]
    return min(gaps) if gaps else None


def parse(svg: str) -> Screen:
    """One screenshot's cells and its grid. **Public API in, plain data out.**"""
    known = styles_of(svg)

    rects = []
    for body in RECT.findall(svg):
        attrs = dict(ATTR.findall(body))
        try:
            rects.append((float(attrs["x"]), float(attrs["y"]),
                          float(attrs["width"]), float(attrs["height"]),
                          attrs.get("fill", "")))
        except (KeyError, ValueError):
            continue

    screen = Screen(
        width=max((x + w for x, _, w, _, _ in rects), default=800.0),
        height=max((y + h for _, y, _, h, _ in rects), default=600.0))
    if rects:
        screen.background = rects[0][4] or screen.background
        rects = rects[1:]
    screen.rects = [r for r in rects if r[4]]

    placed = TEXT.findall(svg)
    for name, x, y, content in placed:
        text = unescape(content)
        if text.strip():
            screen.runs.append((float(x), float(y), text,
                                known.get(name, Style())))

    screen.cell_w = _step(float(x) for _, x, _, _ in placed) or FALLBACK_CELL_W
    screen.line_h = _step(float(y) for _, _, y, _ in placed) or FALLBACK_LINE_H
    size = FONT_SIZE.search(svg)
    screen.font_px = float(size.group(1)) if size else FALLBACK_FONT_PX
    return screen


def render(svg: str, scale: float = 1.0, root: Path | None = None):
    """One screen as a Pillow image.

    **Each glyph is placed on its own cell.** Drawing a run as flowed text lets
    the face's advance disagree with the terminal's cell, and the error
    accumulates: over one line it is a character of drift, and long runs land
    on top of each other.
    """
    from PIL import Image, ImageDraw, ImageFont

    where = (root or Path(".")) / FONTS
    screen = parse(svg)
    size = max(6, int(round(screen.font_px * scale)))
    regular = ImageFont.truetype(str(where / REGULAR), size)
    bold = ImageFont.truetype(str(where / BOLD), size)

    canvas = Image.new("RGB",
                       (int(screen.width * scale), int(screen.height * scale)),
                       screen.background)
    draw = ImageDraw.Draw(canvas)

    for x, y, w, h, fill in screen.rects:
        draw.rectangle([x * scale, y * scale,
                        (x + w) * scale, (y + h) * scale], fill=fill)

    for x, y, text, style in screen.runs:
        face = bold if style.bold else regular
        for index, char in enumerate(text):
            if not char.strip():
                continue
            # Rich's `y` is the baseline, so it is named rather than the
            # offset being guessed at.
            draw.text(((x + index * screen.cell_w) * scale, y * scale),
                      char, font=face, fill=style.fill, anchor="ls")
    return canvas


@dataclass
class Frame:
    """One step of a narrative."""

    svg: str
    hold_ms: int = HOLD_MS
    note: str = ""
    """What this step is, for whoever regenerates it. Not drawn."""


def write_gif(frames: Iterable[Frame], path: Path, scale: float = 1.0,
              root: Path | None = None) -> Path:
    """One narrative as one file.

    **Every frame is held for its own duration**, so a step that asks a reader
    to decide something can sit longer than one that scrolls a list.
    """
    from PIL import Image

    Image.init()
    shots = list(frames)
    if not shots:
        raise ValueError("a narrative with no steps is not a narrative")

    images = [render(frame.svg, scale=scale, root=root) for frame in shots]

    # **ONE PALETTE FOR THE WHOLE FILE.** A GIF carries a single palette;
    # quantising each frame against its own makes the colours shift between
    # frames and the picture flickers. The frames are quantised against a
    # palette built from all of them together.
    widest = max(image.width for image in images)
    tallest = max(image.height for image in images)
    padded = []
    for image in images:
        if image.size != (widest, tallest):
            canvas = Image.new("RGB", (widest, tallest), image.getpixel((0, 0)))
            canvas.paste(image, (0, 0))
            image = canvas
        padded.append(image)

    joined = Image.new("RGB", (widest, tallest * len(padded)))
    for index, image in enumerate(padded):
        joined.paste(image, (0, index * tallest))
    palette = joined.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    converted = [image.quantize(palette=palette, dither=Image.Dither.NONE)
                 for image in padded]

    path.parent.mkdir(parents=True, exist_ok=True)
    converted[0].save(
        path, save_all=True, append_images=converted[1:],
        duration=[frame.hold_ms for frame in shots], loop=0, optimize=True)
    return path
