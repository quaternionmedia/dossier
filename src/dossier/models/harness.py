"""What the harness has run, as the control panel reads it.

THE SEAM IS A SCHEMA, NOT AN IMPORT. qmcp emits `qmcp dashboard --json`: a
payload carrying totals, counts by tool and status, and the most recent
invocations, each one addressed as `owner/repo/invocation/<id>`. Nothing here
imports qmcp and nothing there imports dossier -- coupling them would mean
neither ships without the other, which is the opposite of a pair.

TWO TABLES, BECAUSE THEY ARE TWO DIFFERENT CLAIMS.

  * `HarnessSnapshot` holds the figures the harness reported *about itself* at
    one moment: how many invocations it has run, how many failed, how many
    human requests are outstanding. These are the harness's own counts over its
    whole history, and dossier cannot recompute them from the rows below
    because the payload carries only the recent ones.
  * `HarnessInvocation` holds the rows themselves, keyed by address, so an
    invocation seen twice updates rather than duplicating.

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
