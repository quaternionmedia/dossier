"""rad in a terminal: the session contract, dossier's palette, and the ring.

The seam. `session.py` imports nothing from Textual, so extracting this package
to something both dossier and qmcp depend on is a move rather than a rewrite --
which is the mitigation for building it here instead of in `rad` itself.
"""

from dossier.rad.palette import resolve
from dossier.rad.session import (
    DURABLE_VERBS,
    Intent,
    Meter,
    RadSession,
    RingView,
    Wedge,
    budget_for,
)

__all__ = [
    "DURABLE_VERBS", "Intent", "Meter", "RadSession", "RingView", "Wedge",
    "budget_for", "resolve",
]
