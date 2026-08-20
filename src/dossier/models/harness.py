"""What the harness has run, as the control panel reads it.

THE SEAM IS A SCHEMA, NOT AN IMPORT. qmcp emits `qmcp dashboard --json`: a
payload carrying totals, counts by tool and status, and the most recent
invocations, each one addressed as `owner/repo/invocation/<id>`. Nothing here
imports qmcp and nothing there imports dossier -- coupling them would mean
neither ships without the other, which is the opposite of a pair.

THREE TABLES, BECAUSE THEY ARE THREE DIFFERENT CLAIMS.

  * `HarnessSnapshot` holds the figures the harness reported *about itself* at
    one moment: how many invocations it has run, how many failed, how many
    human requests are outstanding. These are the harness's own counts over its
    whole history, and dossier cannot recompute them from the rows below
    because the payload carries only the recent ones.
  * `HarnessInvocation` holds the rows themselves, keyed by address, so an
    invocation seen twice updates rather than duplicating.

  * `HarnessAsk` holds the human-in-the-loop queue, keyed by address. The
    snapshot's `human_requests` says *how many* are outstanding; this says
    *which*, with the prompt and the options, so a person reading the control
    panel can see the question rather than a number. Until this existed the
    count was all that crossed, and a count is not something anybody can answer.

Storing the totals and calling them derived would be a second, wrong figure;
storing only the rows would silently shrink every count to the size of the
excerpt. The snapshot's age is what tells a reader whether either is current.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HarnessSnapshot(SQLModel, table=True):
    """One reading of a harness's own totals."""

    __tablename__ = "harness_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)

    # `owner/repo` of the harness, not of a repository dossier synced. The two
    # can be the same string and mean different things, so this is stored
    # rather than joined to `project`.
    project: str = Field(index=True)
    schema_version: int = 1

    # Verbatim from the payload. A renderer that recomputed these would be
    # answering a different question from the one the harness answered.
    invocations: int = 0
    failures: int = 0
    human_requests: int = 0
    human_responses: int = 0

    # Where the harness read them from, kept because two harnesses on one
    # machine are ordinary and the totals are meaningless without knowing which
    # database produced them.
    database: Optional[str] = None

    loaded_at: datetime = Field(default_factory=utcnow)


class HarnessInvocation(SQLModel, table=True):
    """One tool invocation the harness ran."""

    __tablename__ = "harness_invocation"

    id: Optional[int] = Field(default=None, primary_key=True)

    # The join. `owner/repo/invocation/<id>` is the same string on both sides,
    # which is what lets the two views be asked the same question.
    address: str = Field(index=True, unique=True)
    project: str = Field(index=True)

    tool_name: Optional[str] = None
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    # The harness's own timestamp, as a string, because the payload carries it
    # as one and parsing it here would invent a precision the payload does not
    # promise.
    ran_at: Optional[str] = None

    loaded_at: datetime = Field(default_factory=utcnow)


class HarnessAsk(SQLModel, table=True):
    """One question the harness put to a person.

    Answered rows are kept rather than deleted: what was asked and what was
    said is the audit trail, and a queue that forgets its answers cannot show
    anybody why something was decided.

    NOTHING HERE ANSWERS ANYTHING. This is the control panel's copy of a queue
    the harness owns. Writing an answer into this table would make two systems
    believe they hold the same authority over one row -- the answer goes back
    across the seam as a payload, exactly as the question came.
    """

    __tablename__ = "harness_ask"

    id: Optional[int] = Field(default=None, primary_key=True)

    # The join. `owner/repo/ask/<id>` is the same string on both sides.
    address: str = Field(index=True, unique=True)
    project: str = Field(index=True)

    request_id: str = Field(index=True)
    request_type: Optional[str] = None
    prompt: Optional[str] = None

    # Stored as the payload sent them, newline-joined. A list column would be
    # a second encoding to keep in step for a field nothing queries.
    options: Optional[str] = None

    status: Optional[str] = None
    asked_at: Optional[str] = None

    # None while outstanding. The presence of an answer is what `outstanding`
    # means here -- not the status string, which is the harness's own word and
    # can lag.
    answered_with: Optional[str] = None
    answered_by: Optional[str] = None
    answered_at: Optional[str] = None

    loaded_at: datetime = Field(default_factory=utcnow)

    @property
    def outstanding(self) -> bool:
        return self.answered_with is None
