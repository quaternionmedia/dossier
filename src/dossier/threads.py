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
# WHERE THE HARNESS ANSWERS: PI. Three services, three constants somebody can
# recall without looking -- 3141 the harness, 1618 this panel when it serves,
# 2718 the code maps. The joke port `1337` was already in use on the machine
# this was chosen on, which is the argument against the port everybody thinks
# of first.
#
# **THIS IS STILL A SECOND COPY OF SOMEBODY ELSE'S CONSTANT.** `qmcp/config.py`
# holds `port: int = 3141` and the two repositories cannot import each other.
# `tests/e2e/test_seam_port.py` reads qmcp's own source and fails when they
# disagree, which is the only thing that keeps a copied number true -- it is
# what caught 8000 against 3333.
#
# Override with `DOSSIER_HARNESS_PORT`, or `--harness-port` where a command
# takes it. Changing this alone moves the panel and not the harness.
DEFAULT_PORT = 3141

# This panel's own port, for when it serves rather than reads. Reserved here so
# the three are declared in one place a reader can find, and so nothing later
# picks it by accident. Override with `DOSSIER_PORT`.
OWN_PORT = 1618

# The code maps, which are optional and not this repository's to start.
# Declared so the allocation is written down once rather than rediscovered.
# Override with `CODECARTO_PORT`.
CODECARTO_PORT = 2718


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


def request_reindex(base: str | None = None,
                    timeout: float = 120.0) -> dict[str, Any]:
    """Ask the harness to rebuild its index from what it already holds.

    **NOT AN IMPORT, AND THAT IS THE WHOLE POINT.** Refreshing through
    `/v1/threads/import` would need a path to an export somebody may no longer
    have, and would re-unpack megabytes to answer a question about what is
    already unpacked. This asks for the reading, not the ingest.

    A long timeout: re-indexing reads every session on the machine. The two
    seconds the listing uses would turn a working refresh into a panel that
    said it failed.

    Every failure is a returned state with a sentence. Nothing raises into a
    key handler.
    """
    import httpx

    base = base or base_url()
    try:
        with httpx.Client(base_url=base, timeout=timeout) as client:
            response = client.post("/v1/threads/reindex", json={})
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False,
                "reason": f"The harness is not answering on {base} "
                          f"({type(exc).__name__}).",
                "fix": "Start it: uv run python -m qmcp serve"}

    if response.status_code == 404:
        return {"ok": False,
                "reason": "This harness has no reindex route.",
                "fix": "It predates the route; update it, or use Ingest."}
    if response.status_code != 200:
        return {"ok": False,
                "reason": f"The harness refused: {response.status_code}"}
    try:
        body = response.json()
    except ValueError:
        return {"ok": False,
                "reason": "The harness answered with something that is not JSON."}
    return {"ok": True, **body}


def summarise_reindex(result: dict[str, Any]) -> str:
    """One line for a notification, whatever happened."""
    if not result.get("ok"):
        return f"{result.get('reason', 'Reindex failed.')} {result.get('fix', '')}".strip()
    indexed = result.get("indexed") or {}
    threads = indexed.get("threads")
    diverged = indexed.get("diverged", 0)
    # `unknown` rather than 0: a harness that did not say how many it holds has
    # not told us it holds none.
    return (f"Reindexed. Archive holds "
            f"{'unknown' if threads is None else threads} thread(s), "
            f"{diverged} disagreeing.")


# --- the harness's topology, which this window draws ---------------------------
#
# **`dossier.topology` COULD DRAW AND NOTHING FETCHED FOR IT.** The renderer
# existed, was tested, and was reachable from no command and no tab -- the same
# shape found in the other front end on the same day: a renderer nothing routes
# to reads exactly like a finished feature. These two functions are the route.


@dataclass
class Topology:
    """A topology as the harness served it, or why it did not."""

    reachable: bool
    where: str
    payload: dict[str, Any] = field(default_factory=dict)
    encoding: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""
    surveyed: int = 0
    problem: str = ""
    remedy: str = ""


def topology(kind: str = "delegation", subject: str = "", level: int = 2,
             base: str | None = None, timeout: float = 10.0) -> Topology:
    """One topology from the harness.

    A subject wins over a kind: asking what the archive says about one project
    is the more specific request, and sending both would leave the harness to
    guess which was meant.

    Never raises. A harness that is not running is the ordinary case -- it is a
    separate process on a separate port -- and the caller has a sentence to
    print rather than a traceback to show.
    """
    import json
    import urllib.error
    import urllib.request

    root = (base or base_url()).rstrip("/")
    # **THE SAME VIEWS THE WEB WINDOW OFFERS.** `level` is the resolution the
    # harness draws at, and it was fixed here while the other window let a
    # reader choose -- so the two windows could not be pointed at the same view.
    # A reading is only comparable if both sides can be asked the same question.
    path = (f"/v1/topology/relations/{subject}" if subject
            else f"/v1/topology/shape/{kind}?level={level}")
    where = f"{root}{path}"

    try:
        with urllib.request.urlopen(where, timeout=timeout) as answer:
            document = json.loads(answer.read())
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = str(json.loads(error.read()).get("detail", ""))
        except Exception:                          # noqa: BLE001
            pass
        return Topology(False, where,
                        problem=f"the harness answered {error.code}"
                                + (f": {detail}" if detail else ""),
                        remedy=("`uv run qmcp threads index --write` builds an "
                                "archive" if error.code == 404 else ""))
    except Exception as error:                     # noqa: BLE001
        return Topology(False, where,
                        problem=f"nothing is answering at {root}",
                        remedy="`uv run qm dashboard --start harness`")

    return Topology(
        True, where,
        payload=document.get("payload", {}),
        encoding=document.get("encoding", []),
        source=str(document.get("source", "")),
        surveyed=int(document.get("surveyed") or 0),
    )


def topologies(base: str | None = None, timeout: float = 10.0) -> list[str]:
    """Every topology the harness offers, or an empty list if it cannot say."""
    import json
    import urllib.request

    root = (base or base_url()).rstrip("/")
    try:
        with urllib.request.urlopen(f"{root}/v1/topology", timeout=timeout) as a:
            document = json.loads(a.read())
    except Exception:                              # noqa: BLE001
        return []
    return [str(t.get("topology", "")) for t in document.get("topologies", [])]


@dataclass
class Conversation:
    """One archived conversation as the harness served it, or why it did not.

    **THE INDEX SAYS WHAT A THREAD IS; THIS SAYS WHAT IT SAID.** The two are
    different documents on purpose — `/v1/threads` carries an addressable row
    per thread and no text at all, because four hundred transcripts is not a
    listing. The turns are fetched only when somebody asks to read one.

    **THIS IS PERSONAL MATERIAL AND IT DOES NOT GET WRITTEN DOWN.** The archive
    carries conversation titles, session identifiers and repository names that
    the organisation has decided must never be published. Nothing here caches a
    transcript to disk, and nothing renders one into a document a gate would
    check — it is fetched, drawn on a screen, and dropped. Anything that wants
    to change that is a decision, not a convenience.
    """

    reachable: bool
    where: str
    source: str = ""
    identifier: str = ""
    title: str = ""
    started_at: str = ""
    url: str = ""
    partial: bool = False
    turns: list[dict[str, Any]] = field(default_factory=list)
    problem: str = ""
    remedy: str = ""


def conversation(source: str, identifier: str, base: str | None = None,
                 timeout: float = 10.0) -> Conversation:
    """One thread's turns, from the harness that owns the archive.

    Never raises, for the same reason `topology` does not: the harness is a
    separate process on a separate port and is very often not running, and the
    caller wants a sentence to print rather than a traceback to show.
    """
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    root = (base or base_url()).rstrip("/")
    # Quoted: an identifier is somebody else's, and archive identifiers have
    # carried slashes and spaces. An unquoted one silently addresses a
    # different route and the 404 blames the archive.
    where = (f"{root}/v1/threads/{urllib.parse.quote(source, safe='')}"
             f"/{urllib.parse.quote(identifier, safe='')}")

    try:
        with urllib.request.urlopen(where, timeout=timeout) as answer:
            document = json.loads(answer.read())
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = str(json.loads(error.read()).get("detail", ""))
        except Exception:                          # noqa: BLE001
            pass
        return Conversation(
            False, where, source=source, identifier=identifier,
            problem=f"the harness answered {error.code}"
                    + (f": {detail}" if detail else ""),
            remedy=("`uv run qmcp threads index --write` builds an archive"
                    if error.code == 404 else ""))
    except Exception:                              # noqa: BLE001
        return Conversation(
            False, where, source=source, identifier=identifier,
            problem=f"nothing is answering at {root}",
            remedy="`uv run qm dashboard --start harness`")

    return Conversation(
        True, where,
        source=str(document.get("source") or source),
        identifier=str(document.get("id") or identifier),
        title=str(document.get("title") or ""),
        started_at=str(document.get("started_at") or ""),
        url=str(document.get("url") or ""),
        partial=bool(document.get("partial")),
        turns=list(document.get("turns") or []),
    )


def locate(delta_name: str, base: str | None = None,
           timeout: float = TIMEOUT) -> tuple[str, str] | None:
    """The (source, identifier) behind a delta name shown in the archive table.

    **THE TABLE SHOWS AN ADDRESS AND THE ROUTE NEEDS TWO FIELDS.** The archive
    row carries `source` and `id`; the table renders the delta name the harness
    built from them. Rebuilding the pair by splitting that name would be a
    second copy of somebody else's naming rule, and the two would agree right up
    until the day the prefix changed — which is the reason `_delta_name` in
    `facets.py` does not derive the address either.

    So it is looked up rather than parsed. Returns None when the archive is not
    reachable or holds no such row, which the caller must tell apart from a
    thread that is there and empty.
    """
    found = fetch(base=base, timeout=timeout)
    if not found.reachable:
        return None
    for row in found.threads:
        if row.get("address") == delta_name and row.get("source") and row.get("id"):
            return str(row["source"]), str(row["id"])
    return None
