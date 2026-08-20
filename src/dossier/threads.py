"""The harness's thread archive, read over the seam rather than off its disk.

**NOTHING HERE IMPORTS qmcp.** What crosses is HTTP and a schema, the same trade
the delta and harness payloads already make. dossier knowing where the archive
keeps its files would be dossier owning half of somebody else's storage layout,
and the first format change would break a repository that never asked to be
involved.

**THE HOST IS LOOPBACK AND IS NOT CONFIGURABLE. THE PORT IS.** The archive is
somebody's conversations. Somebody running the harness on another port is
ordinary and supported; a client that could be pointed at another *machine* is
how "served to this machine only" stops being true, so nothing moves the host.
`handbook/async-contract.md` 4 is the standing rule.

WHEN THE HARNESS IS NOT RUNNING, SAY SO. The failure this is written against is
a panel that shows an empty table when the truth is that nobody answered.
`Archive.reachable` is False with a reason and the command that fixes it, and
every caller renders that rather than zero rows -- the same distinction the
harness payload makes between a count of zero and a count nobody took.

WHAT IT CANNOT DO. Write. There is no route to write and none is wanted: the
archive is built by the harness from files it reads, and a control panel that
could edit it would be a second author of a record whose whole value is being
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The harness's own default port, on loopback.
#
# THE PORT IS A SETTING AND THE HOST IS NOT, and the split is the whole control.
# Somebody running the harness on another port is ordinary; a client that could
# be pointed at another *machine* is how "served to this machine only" stops
# being true. `DOSSIER_HARNESS_PORT` moves the port; nothing moves the host.
HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def base_url() -> str:
    """Where the harness is, on this machine."""
    import os

    raw = os.environ.get("DOSSIER_HARNESS_PORT", "")
    try:
        port = int(raw) if raw else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    return f"http://{HOST}:{port}"


BASE = base_url()

# Short, because this runs inside a redraw. A panel that hangs for thirty
# seconds because a server is down is worse than one that says so in one.
TIMEOUT = 2.0


@dataclass
class Archive:
    """What the harness said, or why it did not.

    `reachable` and `indexed` are separate because they are different failures
    and want different sentences: the harness not running, and the harness
    running with nothing indexed yet.
    """

    reachable: bool = False
    indexed: bool = False
    reason: str | None = None
    fix: str | None = None
    generated_at: str | None = None
    totals: dict[str, Any] = field(default_factory=dict)
    threads: list[dict[str, Any]] = field(default_factory=list)

    @property
    def diverged(self) -> list[dict[str, Any]]:
        return [row for row in self.threads if row.get("diverged")]

    @property
    def note(self) -> str:
        """One line for a panel, whatever state this is in."""
        if not self.reachable:
            return f"{self.reason} {self.fix or ''}".strip()
        if not self.indexed:
            return f"{self.reason} {self.fix or ''}".strip()
        return (f"{self.totals.get('threads', len(self.threads))} thread(s), "
                f"indexed {self.generated_at}. Counts what was exported and "
                f"indexed, not what exists.")


def fetch(base: str | None = None, timeout: float = TIMEOUT) -> Archive:
    """Ask the harness what it has archived.

    Every failure is a state with a sentence, never an exception reaching a
    redraw and never an empty list standing in for an unanswered question.
    """
    import httpx

    base = base or base_url()
    try:
        with httpx.Client(base_url=base, timeout=timeout) as client:
            response = client.get("/v1/threads")
    except Exception as exc:                      # noqa: BLE001 - any transport
        return Archive(
            reachable=False,
            reason=f"The harness is not answering on {base} ({type(exc).__name__}).",
            fix="Start it: uv run python -m qmcp serve",
        )

    if response.status_code == 404:
        return Archive(
            reachable=True, indexed=False,
            reason="The harness is running and has no index.",
            fix="Build one: uv run qmcp threads index --write",
        )
    if response.status_code != 200:
        return Archive(
            reachable=True, indexed=False,
            reason=(f"The harness answered {response.status_code} for the "
                    f"archive."),
            fix="Check it: uv run python -m qmcp serve",
        )

    try:
        body = response.json()
    except ValueError:
        return Archive(
            reachable=True, indexed=False,
            reason="The harness answered with something that is not JSON.",
        )

    return Archive(
        reachable=True, indexed=True,
        generated_at=body.get("generated_at"),
        totals=body.get("totals") or {},
        threads=body.get("threads") or [],
    )


def deltas_for(source: str, identifier: str, base: str | None = None,
               timeout: float = TIMEOUT) -> list[dict[str, Any]] | None:
    """What one thread settled, as payloads this side already ingests.

    None when the harness could not answer -- which a caller must tell apart
    from a thread that settled nothing, because those are different facts about
    the conversation.
    """
    import httpx

    base = base or base_url()
    try:
        with httpx.Client(base_url=base, timeout=timeout) as client:
            response = client.get(f"/v1/threads/{source}/{identifier}/deltas")
    except Exception:                             # noqa: BLE001
        return None
    if response.status_code != 200:
        return None
    try:
        return (response.json() or {}).get("deltas") or []
    except ValueError:
        return None
