"""The development loop: three processes, and whether they are actually wired.

Iterating on dossier against a live harness means three servers on one
workstation, none of which may import another. They agree by convention —
a port number copied into two repositories, a database path taken from the
working directory — and a convention that nobody checks is a convention that
has already drifted. It has here: the panel looked on 8000 while the harness
served 3333, and the message said the archive was absent.

`diagnostics.py` holds the checks that read source and need nothing running.
This module holds the ones that need the processes, and it is separate for a
reason: the suite has an autouse fixture refusing any connection a test did
not arrange, and `tests_do_not_reach_the_network` exists to keep it that way.
Nothing here is imported by the checks there.

Two questions, and the second is the one that gets skipped:

- **Is something listening?** A connection refused is easy to read.
- **Is it the right something?** A 200 proves a server is there, not that it
  is yours. Each service is identified by its OpenAPI title, because all
  three are FastAPI and all three answer a health path the same way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dossier.threads import CODECARTO_PORT, DEFAULT_PORT, HOST, OWN_PORT

REAL_DATABASE = "dossier.db"
"""What the CLI reads with no `DOSSIER_DATABASE_URL` set, relative to the cwd.

Named because `tests/conftest.py` shells `dossier dev purge` against it before
and after every run. Iterating means running the suite often, so a loop
pointed at this file destroys the operator's data as a matter of routine.
"""


@dataclass(frozen=True)
class Service:
    """One process in the loop, and how to tell it apart from the others."""

    role: str
    """What it does here, rather than what it is called."""

    repo: str
    """The sibling clone it is started from."""

    env_var: str
    """The variable that moves it, so a second session can run its own."""

    default_port: int

    title: str
    """Its OpenAPI `info.title`. The discriminator: all three serve FastAPI
    and answer a health path identically, so reachability distinguishes
    nothing."""

    start: str
    """The command that starts it, printed when it is not running."""

    required: bool = True
    """False for a service the loop works without, reported and not failed on."""


HARNESS = Service(
    role="harness",
    repo="qmcp",
    env_var="DOSSIER_HARNESS_PORT",
    default_port=DEFAULT_PORT,
    title="QMCP Server",
    start="uv run qmcp serve",
)

SPEECH = Service(
    role="speech",
    repo="joe",
    env_var="JOE_PORT",
    default_port=8000,
    title="Joe API",
    start="uv run joe backend",
    required=False,
)

PANEL = Service(
    role="panel",
    repo="dossier",
    env_var="DOSSIER_PORT",
    default_port=OWN_PORT,
    title="Dossier API",
    start="uv run dossier serve",
    required=False,
)

LOOP = (HARNESS, SPEECH, PANEL)
"""The harness is required; the other two are not.

`dossier harness ingest|queue|answer` needs the harness and nothing else.
Speech is needed only to answer that queue by voice, and the panel only to
read dossier over HTTP rather than in the terminal. Saying which is which
keeps a doctor from reporting a working setup as broken.
"""


def port_for(service: Service) -> int:
    """The port this service is expected on, after its override."""
    raw = os.environ.get(service.env_var, "")
    try:
        return int(raw) if raw else service.default_port
    except ValueError:
        return service.default_port


def url_for(service: Service) -> str:
    return f"http://{HOST}:{port_for(service)}"


@dataclass
class Probe:
    """What was found at one service's address."""

    service: Service
    url: str
    listening: bool
    found_title: str | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Listening, and the thing that answered is the thing expected."""
        return self.listening and self.found_title == self.service.title

    @property
    def state(self) -> str:
        if self.ok:
            return "pass"
        if self.listening:
            # The dangerous case, and the reason this module exists: something
            # answered, so every reachability check is green, and it is not
            # the service the caller believes it is talking to.
            return "wrong"
        return "absent" if self.service.required else "off"


def probe(service: Service, timeout: float = 2.0) -> Probe:
    """Ask one address what it is. Never raises."""
    import httpx

    url = url_for(service)
    try:
        resp = httpx.get(f"{url}/openapi.json", timeout=timeout)
    except httpx.HTTPError as exc:
        return Probe(service, url, listening=False, detail=type(exc).__name__)

    if resp.status_code != 200:
        return Probe(service, url, listening=True, detail=f"HTTP {resp.status_code} from /openapi.json")

    try:
        title = resp.json().get("info", {}).get("title")
    except ValueError:
        return Probe(service, url, listening=True, detail="/openapi.json is not JSON")

    detail = "" if title == service.title else f"{title!r} is listening here, not {service.title!r}"
    return Probe(service, url, listening=True, found_title=title, detail=detail)


def survey(timeout: float = 2.0) -> list[Probe]:
    """Probe every service in the loop, in order."""
    return [probe(service, timeout) for service in LOOP]


@dataclass
class Isolation:
    """Whether the database in use is one the suite may destroy."""

    url: str | None
    isolated: bool
    rows: int | None
    detail: str


def isolation(root: Path | None = None) -> Isolation:
    """Is this loop pointed away from the database the suite purges?

    `pytest_configure` shells `dossier dev purge` against `dossier.db` before
    the run and `pytest_unconfigure` does it again after. Iterating means
    running the suite repeatedly, so this is not a warning about an unlikely
    accident — it is the normal path.
    """
    configured = os.environ.get("DOSSIER_DATABASE_URL", "")
    real = (root or Path.cwd()) / REAL_DATABASE

    if configured:
        points_at_real = real.name in configured and "memory" not in configured
        return Isolation(
            url=configured,
            isolated=not points_at_real,
            rows=None,
            detail=(
                f"DOSSIER_DATABASE_URL names {REAL_DATABASE}"
                if points_at_real
                else "DOSSIER_DATABASE_URL points away from the file the suite purges"
            ),
        )

    if not real.exists():
        return Isolation(None, True, 0, f"no {REAL_DATABASE} here yet; nothing to lose")

    return Isolation(
        url=None,
        isolated=False,
        rows=_row_count(real),
        detail=f"unset, so the CLI and the suite both use ./{REAL_DATABASE}",
    )


def _row_count(path: Path) -> int | None:
    """Rows in the projects table, or None if it cannot be read."""
    import sqlite3

    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            return conn.execute("SELECT count(*) FROM project").fetchone()[0]
    except sqlite3.Error:
        return None


def allocation() -> list[tuple[str, int, int, str]]:
    """The declared ports, what they resolve to now, and what moves them.

    Read from `dossier.threads`, which is where the allocation is written
    down, rather than repeated here. A second copy is a second thing to drift.
    """
    rows = [
        ("harness (qmcp)", DEFAULT_PORT, port_for(HARNESS), HARNESS.env_var),
        ("panel (dossier)", OWN_PORT, port_for(PANEL), PANEL.env_var),
        ("speech (joe)", SPEECH.default_port, port_for(SPEECH), SPEECH.env_var),
        ("maps (codecarto)", CODECARTO_PORT, CODECARTO_PORT, "CODECARTO_PORT"),
    ]
    return rows
