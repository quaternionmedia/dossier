"""The questions waiting on a person, live, and answering one.

    dossier harness queue              what is waiting, from the harness itself
    dossier harness answer <id> <what> --as <who>

**THIS CLOSES A LOOP THAT WAS OPEN BY DESIGN.** `qmcp.governed` ends at the
human-in-the-loop queue and deliberately does not pass it: a model's draft
arrives there and stops. Until now nothing on this side could read that queue
live or answer it, so the only way through was `qmcp human respond` in the
harness's own terminal. dossier is the human surface; this is where the queue
is answered.

**ANSWERING IS AN ATTESTED ACT, AND THE SHAPE HERE FOLLOWS FROM THAT.**
`governance/qm/ci/attested-registry.yaml` names answering a question in this
queue as one of the acts reserved for a person. Three consequences, each of
which is a refusal rather than a convenience:

- **`answered_by` is required.** An answer with nobody's name on it is not
  attested, and defaulting it to a machine account or an environment variable
  would produce exactly the artifact the registry exists to prevent -- a
  decision that cannot be told apart from one somebody made.
- **One question at a time.** There is no `--all`. A batch answer is a single
  act asserting many judgements, and the registry reserves the judgements
  rather than the keystroke.
- **Nothing here answers on a timeout, a default, or a retry.**

**THE HARNESS'S REFUSALS ARRIVE IN ITS OWN WORDS.** It refuses an answer four
ways -- the request is unknown, it has already been answered, it has expired,
or the response is not one of the options offered. Each is a different fact and
this reports which, rather than collapsing them into "could not answer".

**A LIMIT IS STATED, NEVER SILENT.** The harness pages this endpoint, and a
reading that showed the first page as though it were the queue is the failure
this estate found in the payload path today: fifteen waiting arrived as ten and
nothing said so. `Reading.more` carries what was not shown.

WHAT THIS CANNOT DO. Tell you whether an answer was *right*. Reach a harness
that is not running -- that is the ordinary case, reported with the command
that starts it rather than as a traceback. Or spend anything: reading a queue
and posting an answer are free, and no path here calls a paid service.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from dossier.threads import base_url

# How many rows one reading asks for. The harness allows more; this is what a
# person can act on in one sitting, and anything beyond it is reported as
# `more` rather than quietly dropped.
PAGE = 50

TIMEOUT = 10.0


@dataclass(frozen=True)
class Ask:
    """One question the harness is holding for a person."""

    id: str
    prompt: str
    request_type: str = "approval"
    status: str = "pending"
    options: tuple[str, ...] = ()
    created_at: str = ""
    expires_at: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_a_draft(self) -> bool:
        """Whether a model produced what is being judged.

        `qmcp.governed` says so outright in the context rather than leaving it
        to be inferred from the prompt, and this reads what it says.
        """
        return bool(self.context.get("this_is_a_draft"))

    @property
    def state(self) -> str:
        """What the governed run did, when a governed run produced this."""
        return str(self.context.get("state", "")) or ""


@dataclass(frozen=True)
class Reading:
    """What the harness is holding, or why it could not be asked."""

    asks: tuple[Ask, ...] = ()
    shown: int = 0
    total: int = 0
    where: str = ""
    problem: str = ""
    remedy: str = ""

    @property
    def reachable(self) -> bool:
        return not self.problem

    @property
    def more(self) -> int:
        """How many the harness holds beyond this page. **Never negative.**"""
        return max(0, self.total - self.shown)


@dataclass(frozen=True)
class Answered:
    """One answer, or the harness's reason for refusing it."""

    request_id: str
    accepted: bool
    detail: str = ""
    answered_by: str = ""
    response: str = ""


def _get(url: str) -> tuple[dict[str, Any] | None, str, str]:
    """Fetch one document, or say why not. **Never raises.**"""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as answer:
            return json.loads(answer.read()), "", ""
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = str(json.loads(error.read()).get("detail", ""))
        except Exception:                              # noqa: BLE001
            pass
        return None, f"the harness answered {error.code}" + (
            f": {detail}" if detail else ""), ""
    except Exception:                                  # noqa: BLE001
        return None, f"nothing is answering at {url.split('/v1')[0]}", (
            "`uv run qmcp serve` starts it")


def waiting(base: str | None = None, limit: int = PAGE) -> Reading:
    """Every question the harness is holding for a person, oldest first.

    Read from the harness rather than from a payload file: a file is a snapshot
    somebody exported, and a queue is a thing that changes while you look at it.
    """
    root = (base or base_url()).rstrip("/")
    where = f"{root}/v1/human/requests?status=pending&limit={limit}"

    document, problem, remedy = _get(where)
    if document is None:
        return Reading(where=where, problem=problem, remedy=remedy)

    rows = document.get("requests") or []
    asks = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            # A row that cannot be named cannot be answered, and inventing an
            # identity for it is worse than dropping it.
            continue
        asks.append(Ask(
            id=str(row["id"]),
            prompt=str(row.get("prompt", "")),
            request_type=str(row.get("request_type", "approval")),
            status=str(row.get("status", "pending")),
            options=tuple(str(o) for o in (row.get("options") or [])),
            created_at=str(row.get("created_at", "")),
            expires_at=str(row.get("expires_at") or ""),
            context=row.get("context") or {},
        ))

    # `count` is what this page holds. Where the harness reports no separate
    # total, the page length is all that can be claimed -- and claiming it as
    # the queue's size would be the substitution this estate keeps finding.
    total = document.get("total")
    return Reading(asks=tuple(asks), shown=len(asks),
                   total=int(total) if isinstance(total, int) else len(asks),
                   where=where)


def answer(request_id: str, response: str, by: str,
           base: str | None = None) -> Answered:
    """Answer one question, as a named person.

    `by` is required and is not defaulted anywhere. Answering is an act
    `ci/attested-registry.yaml` reserves for a person, and an answer that
    cannot say who made it is indistinguishable from one a machine made.

    The harness's refusals are carried through as it worded them: an unknown
    request, one already answered, one expired, and a response outside the
    options offered are four different facts.
    """
    if not by.strip():
        raise ValueError(
            "an answer needs a person's name. Answering a question in this "
            "queue is an attested act, and one with nobody's name on it "
            "asserts nothing.")

    root = (base or base_url()).rstrip("/")
    where = f"{root}/v1/human/responses"
    payload = json.dumps({
        "request_id": request_id,
        "response": response,
        "responded_by": by.strip(),
    }).encode("utf-8")

    request = urllib.request.Request(
        where, data=payload, method="POST",
        headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as reply:
            reply.read()
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = str(json.loads(error.read()).get("detail", ""))
        except Exception:                              # noqa: BLE001
            pass
        return Answered(request_id=request_id, accepted=False,
                        answered_by=by, response=response,
                        detail=detail or f"the harness answered {error.code}")
    except Exception as error:                         # noqa: BLE001
        return Answered(request_id=request_id, accepted=False,
                        answered_by=by, response=response,
                        detail=f"nothing is answering at {root}")

    return Answered(request_id=request_id, accepted=True,
                    answered_by=by, response=response)


def render(reading: Reading) -> str:
    """The queue, for the person who is going to answer it."""
    if not reading.reachable:
        lines = [f"  {reading.problem}"]
        if reading.remedy:
            lines.append(f"  {reading.remedy}")
        return "\n".join(lines)

    if not reading.asks:
        return "  Nothing is waiting on a person."

    lines = []
    for ask in reading.asks:
        mark = "  [draft]" if ask.is_a_draft else ""
        lines.append(f"  {ask.id}{mark}")
        lines.append(f"      {ask.prompt}")
        if ask.options:
            lines.append(f"      answer with: {', '.join(ask.options)}")
        if ask.state:
            lines.append(f"      the run that produced it: {ask.state}")
        lines.append("")

    lines.append(f"  {reading.shown} waiting.")
    if reading.more:
        lines.append(f"  {reading.more} more the harness holds and this page "
                     f"did not ask for.")
    lines.append("  Answering is a person's:")
    lines.append("    uv run dossier harness answer <id> <answer> --as <you>")
    return "\n".join(lines)
