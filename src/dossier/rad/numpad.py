"""The nine cells, and how a key reaches one.

    7 8 9        up-left    up    up-right
    4 5 6   =    left     BACK    right
    1 2 3        down-left  down  down-right

WHY A NUMPAD. Eight items around a centre, laid out the way a numeric keypad
already is, so a direction and a digit name the same cell. A reader who knows
where `7` is on a keypad knows where it is on the screen, and the fastest path
to any item is one keystroke rather than a walk around a ring.

**The centre always backs out.** It is not an item and cannot hold one, in every
menu at every depth. A menu whose centre sometimes means "cancel" and sometimes
means "the fifth thing" is one a person cannot use without looking.

WHAT THIS MODULE IS. Placement and key interpretation, as data and pure
functions. It imports nothing -- not Textual, not the session -- so the layout
can be reasoned about, tested and rendered without an application.

THE DIAGONAL PROBLEM, AND WHY THERE ARE TWO ANSWERS. A terminal delivers one
key at a time; it cannot report "up and left held together". So a diagonal is
reachable two ways, and both are supported deliberately:

  * **Movement.** Each direction moves the cursor one cell, so up then left
    lands on 7 whatever the delay between them. Nothing depends on timing.
  * **Chord.** Two directions arriving within `CHORD_WINDOW` are read as the
    diagonal between them, which is what a fast typist means by pressing both.

The chord is a shortcut over the movement, never the only route: a slow press
still gets there, and the destination is the same either way.
"""

from __future__ import annotations

from dataclasses import dataclass

# The centre. Never an item; always "back out one level, or close".
BACK = 5

# Reading order for placing items: clockwise from the top, cardinals first so
# that a menu of four sits at up/right/down/left where a ring would have put
# them, and the diagonals fill in only when there are more than four.
PLACEMENT: tuple[int, ...] = (8, 6, 2, 4, 9, 3, 1, 7)

# Where each cell sits, as (column, row) with the origin at the top left.
POSITION: dict[int, tuple[int, int]] = {
    7: (0, 0), 8: (1, 0), 9: (2, 0),
    4: (0, 1), 5: (1, 1), 6: (2, 1),
    1: (0, 2), 2: (1, 2), 3: (2, 2),
}
CELL_AT: dict[tuple[int, int], int] = {xy: cell for cell, xy in POSITION.items()}

# One press of a direction, as a step on the grid.
STEP: dict[str, tuple[int, int]] = {
    "up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0),
}

# Every spelling of a direction this menu accepts. `wasd` sits under the left
# hand, the arrows under the right, and neither is the "real" one.
DIRECTION_KEYS: dict[str, str] = {
    "up": "up", "w": "up",
    "down": "down", "s": "down",
    "left": "left", "a": "left",
    "right": "right", "d": "right",
}

# Seconds within which two directions are read as one diagonal. Chosen to be
# longer than a deliberate double-tap is fast and shorter than two considered
# presses: it is a comfort, and missing it costs one extra keystroke rather
# than the wrong cell.
CHORD_WINDOW = 0.25

# The diagonal each pair of directions names. Order does not matter: up-then-left
# and left-then-up are the same corner.
DIAGONAL: dict[frozenset[str], int] = {
    frozenset(("up", "left")): 7,
    frozenset(("up", "right")): 9,
    frozenset(("down", "left")): 1,
    frozenset(("down", "right")): 3,
}


@dataclass(frozen=True)
class Placement:
    """Which cell holds which item, and which cells are empty."""

    by_cell: dict[int, int]      # numpad cell -> index into the item list
    by_index: dict[int, int]     # index into the item list -> numpad cell

    @property
    def cells(self) -> tuple[int, ...]:
        return tuple(sorted(self.by_cell))


def place(count: int) -> Placement:
    """Lay `count` items onto the grid, cardinals first.

    More than eight items cannot be laid out. That is a resolver design error
    in rad's sense -- restructure the menu -- and it raises rather than
    silently dropping the ninth, because a menu missing an item looks like a
    menu that never had it.
    """
    if count > len(PLACEMENT):
        raise ValueError(
            f"{count} items will not fit: the grid holds {len(PLACEMENT)} "
            f"around a centre that always backs out. Split the menu.")
    chosen = PLACEMENT[:count]
    return Placement(
        by_cell={cell: index for index, cell in enumerate(chosen)},
        by_index={index: cell for index, cell in enumerate(chosen)},
    )


def step(cell: int, direction: str) -> int:
    """The cell one press of `direction` away, staying inside the grid.

    Movement stops at the edge rather than wrapping. A ring wraps because it
    has no ends; a grid has corners, and a cursor that leaps from the left
    column to the right one is a cursor a reader has to watch rather than
    predict.
    """
    if direction not in STEP:
        return cell
    column, row = POSITION[cell]
    dx, dy = STEP[direction]
    moved = (min(max(column + dx, 0), 2), min(max(row + dy, 0), 2))
    return CELL_AT[moved]


def chord(first: str, second: str) -> int | None:
    """The diagonal two directions name together, or None if they do not."""
    return DIAGONAL.get(frozenset((first, second)))


def digit_of(key: str) -> int | None:
    """The cell a number key names, or None."""
    return int(key) if key in "123456789" and len(key) == 1 else None


def direction_of(key: str) -> str | None:
    """The direction a key names, arrows and `wasd` alike."""
    return DIRECTION_KEYS.get(key)


def step_to_item(cell: int, direction: str, placement: Placement,
                 allowed: set[int] | None = None) -> int:
    """The item nearest the pressed direction, or the current cell.

    Not a walk along the row or column. A menu of four sits at the cardinals,
    and walking left from `8` passes through the empty corner `7` and reaches
    the edge without ever turning down -- which left cell `4` unreachable by
    arrow keys entirely, in the most common menu size there is.

    So this scores every occupied cell by how well it lies in the pressed
    direction and picks the best, preferring the nearest when two score alike.
    Cells behind the cursor are never chosen: pressing left may not move you
    right, however close something is.

    The centre is never a candidate. It backs out, and it is reached by
    pressing `5` rather than by wandering into it.

    `allowed`, when given, is the only set of cells the cursor may land on --
    a host greys out what it cannot act on, and a cursor that steps onto a
    greyed cell reads as the arrow keys being broken. `None` means every
    occupied cell is a candidate, which is the case where nobody declared
    availability.
    """
    if direction not in STEP:
        return cell
    dx, dy = STEP[direction]
    column, row = POSITION[cell]

    best, best_score = cell, None
    for candidate in placement.by_cell:
        if candidate == cell or candidate == BACK:
            continue
        if allowed is not None and candidate not in allowed:
            continue
        cx, cy = POSITION[candidate]
        along = (cx - column) * dx + (cy - row) * dy
        if along <= 0:
            continue  # level with the cursor, or behind it
        across = abs((cx - column) * dy - (cy - row) * dx)
        # Along the axis first, then the smaller sideways drift.
        score = (along, -across)
        if best_score is None or score > best_score:
            best, best_score = candidate, score
    return best
