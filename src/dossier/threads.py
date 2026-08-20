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

WHAT IT CANNOT DO. Author. It never writes a thread row, a digest or a history
entry -- the archive stays one record with one author, and a panel editing it
would be a second. **Asking the harness to import an export is not that.** The
harness does the writing, from a file the operator points at, and this only
asks. The distinction is between authoring a record and calling the thing that
owns it.
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
# THE PORT THE HARNESS ACTUALLY SERVES ON, and it is a second copy of a
# constant this repository does not own -- `qmcp/config.py` has `port: int =
# 3333`. It cannot be imported: the two are separate repositories with no
# dependency between them, and giving the panel one would put the harness's
# code in the panel's install for the sake of an integer.
#
# It was 8000, and nothing noticed. The panel reported "the harness is not
# answering on http://127.0.0.1:8000" while the harness was serving 203 threads
# on 3333, and the message was accurate about the address it tried and useless
# about the problem. `tests/e2e/test_seam_port.py` reads qmcp's own config when
# the sibling clone is present and fails when these two disagree, which is the
# only way a copied constant stays true.
DEFAULT_PORT = 3333


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


def request_import(path: str, source: str | None = None,
                   base: str | None = None,
                   timeout: float = 120.0) -> dict[str, Any]:
    """Ask the harness to unpack an export and re-index.

    **THIS DOES NOT WRITE THE ARCHIVE.** It asks the harness to, which is the
    harness doing its own job. The panel never authors a thread row.

    A long timeout, because unpacking a real export is tens of megabytes and
    re-indexing reads every session afterwards. The two-second timeout the
    listing uses would turn a working import into a panel that said it failed.

    Every failure is a returned state with a sentence. Nothing raises into a
    button handler.
    """
    import httpx

    base = base or base_url()
    try:
        with httpx.Client(base_url=base, timeout=timeout) as client:
            response = client.post("/v1/threads/import",
                                   json={"path": path, "source": source})
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False,
                "reason": f"The harness is not answering on {base} "
                          f"({type(exc).__name__}).",
                "fix": "Start it: uv run python -m qmcp serve"}

    if response.status_code != 200:
        detail = ""
        try:
            detail = (response.json() or {}).get("detail", "")
        except ValueError:
            detail = response.text[:200]
        return {"ok": False,
                "reason": f"The harness refused: {detail or response.status_code}"}

    try:
        body = response.json()
    except ValueError:
        return {"ok": False,
                "reason": "The harness answered with something that is not JSON."}
    return {"ok": True, **body}


def summarise_import(result: dict[str, Any]) -> str:
    """One line for a notification, whatever happened."""
    if not result.get("ok"):
        return f"{result.get('reason', 'Import failed.')} {result.get('fix', '')}".strip()

    indexed = result.get("indexed") or {}
    parts = [f"{result.get('written', 0)} new"]
    if result.get("replaced"):
        parts.append(f"{result['replaced']} replaced")
    if result.get("identical"):
        parts.append(f"{result['identical']} unchanged")
    if result.get("unreadable"):
        parts.append(f"{len(result['unreadable'])} unreadable")
    if result.get("positional"):
        parts.append(f"{result['positional']} named by position")

    return (f"{', '.join(parts)}. Archive now {indexed.get('threads', '?')} "
            f"thread(s), {indexed.get('diverged', 0)} disagreeing.")
