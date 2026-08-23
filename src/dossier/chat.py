"""One archived conversation, drawn to be read.

**A TRANSCRIPT IS NOT A TABLE.** Every other view in this panel is rows and
columns, because every other view is comparing things. A conversation is one
thing, read top to bottom, and the questions a reader brings to it are *who said
this* and *where does this turn end* — neither of which a table answers.

**IT IS DRAWN, NOT STORED.** The archive carries conversation titles, session
identifiers and repository names the organisation has decided must never be
published. Nothing here writes a transcript to a file, returns a path, or builds
a document any gate would read: turns arrive from the harness, become lines, and
are dropped when the screen closes. A function here that took an output path
would be a decision about publication wearing the clothes of a convenience.

**WHAT IT CANNOT DO.** Tell you whether the archive is complete — `partial` says
the export was truncated, and that is the harness's claim rather than this
module's finding. Or render anything but text: an image or a tool call in a turn
arrives as whatever text the exporter left, and is shown rather than
interpreted, because inventing a rendering for something nobody has looked at is
how a viewer starts lying about its source.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any

# Who is speaking, in one column, so the eye finds the turn boundaries without
# reading. Not the raw role: exporters disagree about capitalisation and about
# whether the machine is `assistant` or `model`, and a viewer that showed both
# would look like two different speakers.
SPEAKERS: dict[str, str] = {
    "user": "you",
    "human": "you",
    "assistant": "it",
    "model": "it",
    "system": "system",
    "tool": "tool",
}

UNKNOWN_SPEAKER = "?"

# A turn with no text at all. Drawn rather than skipped: a turn that exists and
# said nothing is a fact about the export, and dropping it would silently
# renumber everything after it.
EMPTY = "(no text in the export)"


@dataclass
class Drawn:
    """Lines to show, and what this rendering could not carry."""

    lines: list[str] = field(default_factory=list)
    channels_dropped: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(self.lines)


def speaker(role: str) -> str:
    """The one-word speaker for a role, or `?`.

    Unknown is a value: an exporter's new role reads as `?` rather than being
    quietly filed under the machine, which would put words in its mouth.
    """
    return SPEAKERS.get((role or "").strip().lower(), UNKNOWN_SPEAKER)


def draw(conversation: Any, width: int = 76) -> Drawn:
    """The conversation as lines.

    Takes the `Conversation` the harness served. An unreachable one draws its
    problem and its remedy and no turns at all — an empty transcript would state
    that the conversation was empty, which is a different claim.
    """
    if not getattr(conversation, "reachable", False):
        lines = [getattr(conversation, "problem", "") or "the harness did not answer"]
        remedy = getattr(conversation, "remedy", "")
        if remedy:
            lines.append(f"  {remedy}")
        lines.append(f"  tried {getattr(conversation, 'where', '')}")
        lines.append("  Nothing was drawn. An empty transcript would look like "
                     "an answer.")
        return Drawn(lines, ["every turn"])

    header = [
        conversation.title or "(untitled)",
        f"  {conversation.source}/{conversation.identifier}",
    ]
    if conversation.started_at:
        header.append(f"  started {conversation.started_at}")
    if conversation.partial:
        # The harness's claim, repeated as the harness's claim. A reader
        # comparing turn counts with the index needs to know the export was cut
        # rather than discover it by the two disagreeing.
        header.append("  PARTIAL -- the export was truncated, so turns are "
                      "missing from this conversation")
    header.append("")

    body: list[str] = []
    for number, turn in enumerate(conversation.turns, start=1):
        who = speaker(str(turn.get("role") or ""))
        at = str(turn.get("at") or "")
        stamp = f"  {at}" if at else ""
        body.append(f"{number:>3}  {who}{stamp}")
        text = str(turn.get("text") or "").strip()
        if not text:
            body.append(f"     {EMPTY}")
        else:
            for paragraph in text.split("\n"):
                if not paragraph.strip():
                    body.append("")
                    continue
                for line in textwrap.wrap(paragraph, width=max(20, width - 5)) or [""]:
                    body.append(f"     {line}")
        body.append("")

    if not conversation.turns:
        body.append("This conversation has no turns in the archive.")
        body.append("That is what the export holds, not an error here.")

    dropped = ["attachments", "tool calls", "formatting"]
    return Drawn(header + body, dropped)
