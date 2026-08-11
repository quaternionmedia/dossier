"""Storage for the corpus's generated governance documents.

These tables hold what `governance-status.yaml` and `harness-status.json`
report. Three properties of this module are load-bearing, and each exists
because getting it wrong produces a table that looks right and is not.

**Nothing here is keyed to `project.id`.** `dossier github sync` empties and
rebuilds `project`, `project_branch`, `project_pull_request`,
`document_section`, `project_issue`, `project_contributor`,
`project_language`, `project_dependency` and `project_release` on every run.
Governance state hung off any of those disappears at the next sync, silently.
The link here is the repository *name*, as the corpus names it, which also
lets a repository the operator has never synced still appear — the corpus's
list of repositories is not dossier's list of projects, and pretending
otherwise would hide exactly the projects nobody is looking at.

**Every field that the documents may report as unknown is stored as a pair:**
a nullable value column and a `*_unknown` reason column. The convention in
both documents is `{"unknown": "<reason>"}`, which is a value meaning the fact
could not be established, and says why. It is not zero, not empty, and not
compliant. Collapsing it into a null would render a repository nobody could
measure identically to a healthy one.

So a pair reads:

| value | unknown | means |
|---|---|---|
| set | `None` | the measured fact |
| `None` | set | nobody could measure it, for the stated reason |
| `None` | `None` | a real null in the document — `last_propagation: null` means *never propagated*, which is established, not missing |

**This is a read model.** Nothing writes back to the documents; they are
generated in the corpus, and a renderer that edits its own input creates a
second source of truth for the same fact.

A row is assembled from both documents, which fail independently, so a load
refreshes only the columns whose document it could read and leaves the rest
untouched. That is why each source carries its own `generated_at` column here
rather than sharing one: the view has to be able to say "governance data is
four hours old and the harness document has never been read", and a single
provenance column cannot express it.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from .schemas import utcnow


class GovernanceRepository(SQLModel, table=True):
    """One repository, as the corpus's generated documents describe it."""

    __tablename__ = "governance_repository"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    slug: Optional[str] = None
    role: Optional[str] = None

    # Document provenance, kept per source rather than merged into one column.
    # A row is assembled from two documents that can fail independently, and
    # "the harness document was never read" has to stay distinguishable from
    # "the harness document says there is nothing here". One shared column
    # would collapse them, and the second reads as healthy.
    #
    # Age is computed at render time from these; a stored age is wrong the
    # moment it is written.
    governance_generated_at: Optional[datetime] = None
    harness_generated_at: Optional[datetime] = None
    governance_observed_at: Optional[datetime] = None

    # Only `harness-status.json` states its own budget. The governance
    # document does not carry one, so it is null here rather than filled from
    # the handbook page that states it -- encoding that number in dossier
    # would be a second definition of a governance rule, and the view shows
    # age without a verdict instead. Filing it belongs with the generator.
    harness_staleness_budget_hours: Optional[float] = None

    loaded_at: datetime = Field(default_factory=utcnow)

    # Where the project branch stands against the corpus.
    branch_ref: Optional[str] = None
    branch_commit: Optional[str] = None
    behind_corpus: Optional[int] = None
    behind_corpus_unknown: Optional[str] = None
    ahead_of_corpus: Optional[int] = None
    ahead_of_corpus_unknown: Optional[str] = None
    last_propagation: Optional[datetime] = None
    last_propagation_unknown: Optional[str] = None

    # Verbatim from the document. "drift" and "match" are the generator's
    # words; this column does not re-spell them, because a renderer that
    # renames a governance value has defined a second vocabulary for it.
    seed_drift: Optional[str] = None
    seed_drift_unknown: Optional[str] = None

    records_total: Optional[int] = None
    records_ratified: Optional[int] = None

    open_prs_count: Optional[int] = None
    open_prs_unknown: Optional[str] = None

    # A claim, never evidence: phase comes from a human's entry in the
    # corpus's roster and is never derived from artifacts. Rendering it beside
    # the evidence columns is the point -- the gap between them is the signal.
    phase: Optional[str] = None
    phase_source: Optional[str] = None

    # Evidence: what has landed on the project's default branch.
    precondition: Optional[str] = None
    precondition_unknown: Optional[str] = None
    precondition_missing: Optional[str] = None  # comma-joined, verbatim

    # What a v tag asserts, beside what the default branch carries. `main` is
    # readiness; a tag is governance passed. The gap between them is the fact
    # worth storing, and `unreleased` is not `current` -- both have nothing
    # outstanding and they mean opposite things.
    release_state: Optional[str] = None
    release_unknown: Optional[str] = None
    release_latest: Optional[str] = None
    release_annotated: Optional[bool] = None
    release_unreleased_commits: Optional[int] = None

    slot_state: Optional[str] = None
    slot_unknown: Optional[str] = None
    slot_open_prs: Optional[int] = None
    slot_violations: Optional[str] = None  # which PRs put it over, verbatim


class GovernanceThread(SQLModel, table=True):
    """One line of work in flight, as `harness-status.json` reports it.

    A thread is an observed state, not progress. `stage` is one of the
    generator's four words and nothing here estimates completion: the corpus
    has no definition of done a tool could read, and a percentage would be the
    most confidently wrong thing this view could show.
    """

    __tablename__ = "governance_thread"

    id: Optional[int] = Field(default=None, primary_key=True)
    repository_name: str = Field(index=True)
    name: str
    stage: Optional[str] = None
    pr: Optional[int] = None
    base: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None

    additions: Optional[int] = None
    deletions: Optional[int] = None
    commits: Optional[int] = None
    changed_files: Optional[int] = None
    mergeable_state: Optional[str] = None
    thread_updated_at: Optional[datetime] = None

    idle_hours: Optional[float] = None
    stalled: bool = False

    source_generated_at: Optional[datetime] = None
    loaded_at: datetime = Field(default_factory=utcnow)
