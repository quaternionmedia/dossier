"""Loading and reading the corpus's governance documents.

The application layer between :mod:`dossier.parsers.governance`, which reads
files, and the CLI and TUI, which display. It exists so those two cannot drift
into two different opinions about what "unknown" looks like.

## What a load does, and what it refuses to do

Each document owns its own columns and its own rows. A load applies only the
documents it could actually read:

* Governance loaded, harness absent -> governance columns refresh; harness
  columns and every thread are left exactly as they were.
* Harness loaded, governance absent -> the reverse.
* Neither loaded -> nothing is written at all.

This is the whole reason the load is not a `DELETE FROM` followed by an
insert. Wiping threads because `harness-status.json` could not be read would
render "nobody could measure this" as an empty table, and an empty table reads
as nothing in flight. A row is only removed when the document that owns it
loaded and no longer mentions it.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, delete, select

from dossier.models import GovernanceRepository, GovernanceThread
from dossier.parsers.governance import (
    DocumentUnavailable,
    GovernanceDocument,
    HarnessDocument,
    age_hours,
    load_governance,
    load_harness,
)

GOVERNANCE_FILENAME = "governance-status.yaml"
HARNESS_FILENAME = "harness-status.json"

#: Where the corpus is mounted in a project that has adopted it.
DEFAULT_CORPUS_DIR = Path("governance/qm")


def default_paths(corpus_dir: Path | str | None = None) -> tuple[Path, Path]:
    """The two document paths, given where the corpus is mounted.

    Both documents live at the corpus root. In a project that vendors the
    corpus that is `governance/qm`; pointing at a corpus checkout directly
    also works, which is how this is usable before a pin bump carries the
    documents into the submodule.
    """
    root = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS_DIR
    return root / GOVERNANCE_FILENAME, root / HARNESS_FILENAME


def has_documents(corpus_dir: Path | str) -> bool:
    """Whether either document is present at this root."""
    governance, harness = default_paths(corpus_dir)
    return governance.exists() or harness.exists()


def looks_like_corpus(corpus_dir: Path | str) -> bool:
    """Whether this directory is a corpus checkout, documents or not.

    Two markers rather than one, and both prose rather than generated, so a
    branch that predates `ci/` still identifies itself.
    """
    root = Path(corpus_dir)
    return (root / "PRINCIPLES.md").exists() and (root / "records").is_dir()


#: Where to look for the corpus, in order, when nobody said. Each entry is a
#: path and the sentence a caller should print if it wins -- resolution that
#: cannot explain itself is the kind of convenience that later gets blamed for
#: reading the wrong repository.
SEARCH_ORDER = (
    (Path("."), "the current directory is a corpus checkout"),
    (DEFAULT_CORPUS_DIR, "the corpus vendored at governance/qm"),
    (Path("..") / "qm", "a corpus checkout beside this one"),
)


def resolve_corpus_dir(explicit: Path | str | None = None) -> tuple[Path, str]:
    """Decide which corpus checkout to read, and say why.

    Returns the path and a short reason, always. A caller prints the reason:
    an implicit choice that stays silent is how a reader ends up looking at a
    different repository than the one they think they are looking at.

    A candidate carrying the documents wins over one that merely looks like a
    corpus, because reading is the point. Falling all the way through returns
    the first candidate anyway, so the caller reports "not found here" against
    a concrete path rather than against nothing.
    """
    if explicit is not None:
        return Path(explicit), "given with --corpus-dir"

    for candidate, reason in SEARCH_ORDER:
        if has_documents(candidate):
            return candidate, reason
    for candidate, reason in SEARCH_ORDER:
        if looks_like_corpus(candidate):
            return candidate, f"{reason}, though neither document is there yet"

    return SEARCH_ORDER[0][0], "nothing looked like a corpus, so: the current directory"


@dataclass
class SourceOutcome:
    """What happened to one document during a load."""

    path: Path
    loaded: bool
    reason: Optional[str] = None
    generated_at: Optional[datetime] = None
    rows: int = 0

    @property
    def summary(self) -> str:
        if self.loaded:
            return f"read {self.rows} row(s), generated {_stamp(self.generated_at)}"
        return f"unavailable - {self.reason}"


@dataclass
class LoadReport:
    """The outcome of a load, including the half that did not happen."""

    governance: SourceOutcome
    harness: SourceOutcome
    threads: int = 0
    removed: list[str] = dataclass_field(default_factory=list)

    @property
    def anything_loaded(self) -> bool:
        return self.governance.loaded or self.harness.loaded


def load_documents(
    session: Session,
    corpus_dir: Path | str | None = None,
    governance_path: Path | str | None = None,
    harness_path: Path | str | None = None,
) -> LoadReport:
    """Read both documents and merge them into the read model."""
    default_governance, default_harness = default_paths(corpus_dir)
    gov_path = Path(governance_path) if governance_path else default_governance
    har_path = Path(harness_path) if harness_path else default_harness

    governance: Optional[GovernanceDocument] = None
    harness: Optional[HarnessDocument] = None

    try:
        governance = load_governance(gov_path)
        gov_outcome = SourceOutcome(
            path=gov_path,
            loaded=True,
            generated_at=governance.generated_at,
            rows=len(governance.projects),
        )
    except DocumentUnavailable as exc:
        gov_outcome = SourceOutcome(path=gov_path, loaded=False, reason=exc.reason)

    try:
        harness = load_harness(har_path)
        har_outcome = SourceOutcome(
            path=har_path,
            loaded=True,
            generated_at=harness.generated_at,
            rows=len(harness.repositories),
        )
    except DocumentUnavailable as exc:
        har_outcome = SourceOutcome(path=har_path, loaded=False, reason=exc.reason)

    report = LoadReport(governance=gov_outcome, harness=har_outcome)
    if not report.anything_loaded:
        # Nothing is cleared. Whatever is stored stays, carrying its own
        # generated_at so the view can show how old it is -- which is more
        # honest than an empty table and more honest than pretending it is
        # current.
        return report

    existing = {row.name: row for row in session.exec(select(GovernanceRepository)).all()}

    if governance is not None:
        for project in governance.projects:
            row = existing.get(project.name)
            if row is None:
                row = GovernanceRepository(name=project.name)
                existing[project.name] = row
            _apply_governance(row, project, governance)
            session.add(row)

    if harness is not None:
        for repo in harness.repositories:
            row = existing.get(repo.name)
            if row is None:
                row = GovernanceRepository(name=repo.name)
                existing[repo.name] = row
            _apply_harness(row, repo, harness)
            session.add(row)

        # Threads are wholly owned by the harness document, so they are
        # replaced only when it loaded.
        session.exec(delete(GovernanceThread))
        for repo in harness.repositories:
            for thread in repo.threads:
                session.add(
                    GovernanceThread(
                        repository_name=thread.repository_name,
                        name=thread.name,
                        stage=thread.stage,
                        pr=thread.pr,
                        base=thread.base,
                        title=thread.title,
                        author=thread.author,
                        additions=thread.additions,
                        deletions=thread.deletions,
                        commits=thread.commits,
                        changed_files=thread.changed_files,
                        mergeable_state=thread.mergeable_state,
                        thread_updated_at=_naive(thread.updated_at),
                        idle_hours=thread.idle_hours,
                        stalled=thread.stalled,
                        source_generated_at=_naive(harness.generated_at),
                    )
                )
                report.threads += 1

    # A row disappears only when both documents loaded and neither mentions
    # it. With one document missing, a name it alone knows about is absent
    # rather than gone, and deleting it would report a repository as having
    # left the org because a file could not be opened.
    if governance is not None and harness is not None:
        named = {p.name for p in governance.projects} | {r.name for r in harness.repositories}
        for name, row in list(existing.items()):
            if name not in named:
                session.delete(row)
                report.removed.append(name)

    session.commit()
    return report


def _apply_governance(
    row: GovernanceRepository,
    project,
    document: GovernanceDocument,
) -> None:
    row.governance_generated_at = _naive(document.generated_at)
    row.governance_observed_at = _naive(project.observed_at)
    row.branch_ref = project.branch_ref
    row.branch_commit = project.branch_commit

    row.behind_corpus = project.behind_corpus.or_none()
    row.behind_corpus_unknown = project.behind_corpus.unknown
    row.ahead_of_corpus = project.ahead_of_corpus.or_none()
    row.ahead_of_corpus_unknown = project.ahead_of_corpus.unknown

    # `last_propagation: null` means never propagated. Both columns null is
    # exactly that, and it is a different row from one carrying a reason.
    row.last_propagation = _naive(_as_datetime(project.last_propagation.or_none()))
    row.last_propagation_unknown = project.last_propagation.unknown

    row.seed_drift = project.seed_drift.or_none()
    row.seed_drift_unknown = project.seed_drift.unknown
    row.records_total = project.records_total
    row.records_ratified = project.records_ratified
    row.open_prs_count = project.open_prs_count
    row.open_prs_unknown = project.open_prs.unknown


def _apply_harness(
    row: GovernanceRepository,
    repo,
    document: HarnessDocument,
) -> None:
    row.harness_generated_at = _naive(document.generated_at)
    row.harness_staleness_budget_hours = document.staleness_budget_hours
    row.slug = repo.slug
    row.role = repo.role
    row.phase = repo.phase
    row.phase_source = repo.phase_source
    row.precondition = repo.precondition.or_none()
    row.precondition_unknown = repo.precondition.unknown
    row.precondition_missing = ", ".join(repo.precondition_missing) or None
    row.slot_state = repo.slot_state
    row.slot_unknown = repo.slot_unknown
    row.slot_open_prs = repo.slot_open_prs
    row.slot_violations = repo.slot_violations


def _as_datetime(value) -> Optional[datetime]:
    from dossier.parsers.governance import parse_timestamp

    return parse_timestamp(value) if value is not None else None


def _naive(value: Optional[datetime]) -> Optional[datetime]:
    """Drop the timezone for SQLite storage, after normalising to UTC.

    Every timestamp in both documents is UTC, and SQLite has no tz-aware type.
    Converting first means a naive column is still comparable; storing the
    local wall clock would not be.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def repositories(session: Session) -> list[GovernanceRepository]:
    """Stored repository rows, corpus first and then alphabetical."""
    rows = list(session.exec(select(GovernanceRepository)).all())
    return sorted(rows, key=lambda r: (r.role != "corpus", r.name.lower()))


def threads(session: Session, stalled_first: bool = True) -> list[GovernanceThread]:
    """Stored threads, most idle first so the stalled ones surface."""
    rows = list(session.exec(select(GovernanceThread)).all())
    return sorted(
        rows,
        key=lambda t: (not (stalled_first and t.stalled), -(t.idle_hours or 0.0)),
    )


def document_age(session: Session) -> dict[str, Optional[float]]:
    """Hours since each document was generated, from what is stored.

    ``None`` means no row carries a timestamp for that document, which is what
    "never loaded" looks like from the read model.
    """
    rows = list(session.exec(select(GovernanceRepository)).all())
    governance = [r.governance_generated_at for r in rows if r.governance_generated_at]
    harness = [r.harness_generated_at for r in rows if r.harness_generated_at]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "governance": age_hours(max(governance), now) if governance else None,
        "harness": age_hours(max(harness), now) if harness else None,
    }


def _stamp(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d %H:%MZ") if value else "unknown"


# --- Joining governance rows to the projects dossier already knows ---------
#
# The two sides are stored independently, on purpose: `github sync` rebuilds the
# project tables and would take governance state with them. So the link is made
# at **read** time, here, and never stored as a foreign key.
#
# It is a match on names, which means it can be wrong, so each match carries how
# it was made. `slug` is the strong key -- `quaternionmedia/alfred` identifies
# one repository on one host. A bare name is a guess that happens to be safe
# inside a single org and would not be across two.

#: Match rules, strongest first. Each takes (governance row, project) and
#: returns True. The first to fire names the match.
_MATCH_RULES = (
    (
        "slug",
        lambda row, project: bool(row.slug)
        and row.slug in {project.full_name, project.get_full_name(), project.name},
    ),
    (
        "repo name",
        lambda row, project: bool(project.github_repo)
        and row.name == project.github_repo,
    ),
    ("name", lambda row, project: row.name == project.name),
    (
        "trailing name",
        lambda row, project: "/" in project.name
        and row.name == project.name.rsplit("/", 1)[-1],
    ),
)


def match_strength(row: GovernanceRepository, project) -> Optional[str]:
    """How this governance row matches this project, or ``None``.

    The returned word is shown to the reader. A match on `slug` is an identity;
    a match on a bare name is an inference, and saying which is the difference
    between a link and a guess presented as one.
    """
    for how, rule in _MATCH_RULES:
        try:
            if rule(row, project):
                return how
        except AttributeError:  # a partially-populated project row
            continue
    return None


def governance_for_project(session: Session, project) -> tuple[Optional[GovernanceRepository], Optional[str]]:
    """The governance row describing this project, and how it was matched."""
    if project is None:
        return None, None
    best: tuple[Optional[GovernanceRepository], Optional[str], int] = (None, None, len(_MATCH_RULES))
    for row in session.exec(select(GovernanceRepository)).all():
        how = match_strength(row, project)
        if how is None:
            continue
        rank = [name for name, _ in _MATCH_RULES].index(how)
        if rank < best[2]:
            best = (row, how, rank)
    return best[0], best[1]


def project_for_repository(session: Session, row: GovernanceRepository):
    """The project dossier holds for this governance row, and how it matched.

    The coverage direction: which repositories the corpus governs have actually
    been synced into this store. A repository with no project is not a problem
    -- it means nobody has looked at it here, which is worth being able to see.
    """
    from dossier.models import Project

    best = (None, None, len(_MATCH_RULES))
    for project in session.exec(select(Project)).all():
        how = match_strength(row, project)
        if how is None:
            continue
        rank = [name for name, _ in _MATCH_RULES].index(how)
        if rank < best[2]:
            best = (project, how, rank)
    return best[0], best[1]


def threads_for_project(session: Session, project) -> list[GovernanceThread]:
    """Threads in flight for this project, most idle first."""
    row, _ = governance_for_project(session, project)
    if row is None:
        return []
    return [t for t in threads(session) if t.repository_name == row.name]


def synced_pr_numbers(session: Session, project) -> set[int]:
    """Pull request numbers dossier has synced for this project.

    Lets a thread say whether the pull request it names is one this store knows
    about. A thread whose pull request is absent is not an error -- it means the
    project has not been synced since it opened.
    """
    from dossier.models import ProjectPullRequest

    if project is None or project.id is None:
        return set()
    rows = session.exec(
        select(ProjectPullRequest).where(ProjectPullRequest.project_id == project.id)
    ).all()
    return {r.pr_number for r in rows}


# --- Presentation, shared so the CLI and the TUI cannot disagree -----------
#
# Every one of these renders unknown as its own state. None of them renders it
# as blank, and none of them renders it as the healthy value. A project nobody
# could measure must never look like a project measured and found compliant.

UNKNOWN_TEXT = "unknown"


def show_pair(value, unknown: Optional[str], null_text: str = "-") -> str:
    """Render a value/unknown column pair.

    ``null_text`` is what a stated null means for this field, which is a fact
    and not an absence -- the caller supplies the word, because "never
    propagated" and "no releases" are different sentences.
    """
    if unknown:
        return UNKNOWN_TEXT
    if value is None:
        return null_text
    return str(value)


def coverage_text(project, matched_by: Optional[str]) -> str:
    """Whether this store holds the repository, and whether that was a guess.

    Deliberately not the project's name: the match means they are the same
    repository, so repeating the name says nothing the row does not. What is
    worth a column is that a weaker key than the slug was used, because a bare
    name is safe inside one org and would not be across two.
    """
    if project is None:
        return "not synced"
    if matched_by == "slug":
        return "synced"
    return f"synced ({matched_by})"


def drift_text(row: GovernanceRepository) -> str:
    """How far behind the corpus this project is, in words the document used."""
    if row.behind_corpus_unknown:
        return UNKNOWN_TEXT
    if row.behind_corpus is None:
        return "-"
    if row.behind_corpus == 0:
        return "current"
    return f"{row.behind_corpus} behind"


def health(row: GovernanceRepository) -> str:
    """One of ``unknown``, ``drift``, ``ok`` — for styling, not for deciding.

    Deliberately coarse and deliberately not stored. It is a rendering of
    facts the document already states, so it adds no governance meaning; a
    stored verdict column would become a second definition of drift.
    """
    if row.behind_corpus_unknown or row.precondition_unknown or row.slot_unknown:
        return UNKNOWN_TEXT
    if (row.behind_corpus or 0) > 0 or row.seed_drift == "drift" or row.slot_state == "over":
        return "drift"
    return "ok"


def summary_lines(row: Optional[GovernanceRepository], matched_by: Optional[str] = None) -> list[str]:
    """A project's governance state in a few lines, for a detail view.

    One implementation so the detail panel and any other reader cannot end up
    with two vocabularies for the same row. Returns plain strings; the caller
    decides on markup.
    """
    if row is None:
        return [
            "not in the corpus's governance documents",
            "either the corpus does not govern it, or nothing has been loaded",
        ]

    lines = [
        f"phase {row.phase or '-'} (claimed{', ' + row.phase_source if row.phase_source else ''})",
        f"corpus {drift_text(row)}",
        f"seed {show_pair(row.seed_drift, row.seed_drift_unknown)}",
        f"evidence {show_pair(row.precondition, row.precondition_unknown)}"
        + (f" - missing {row.precondition_missing}" if row.precondition_missing else ""),
        f"slot {show_pair(row.slot_state, row.slot_unknown)}"
        + (f" holds {row.slot_violations}" if row.slot_violations else ""),
    ]
    if row.records_total is not None:
        lines.append(f"records {row.records_total} ({row.records_ratified or 0} ratified)")
    if row.last_propagation_unknown:
        lines.append("last propagation unknown")
    elif row.last_propagation is None:
        lines.append("never propagated")
    else:
        lines.append(f"last propagation {row.last_propagation:%Y-%m-%d}")
    if matched_by and matched_by != "slug":
        lines.append(f"matched to this project by {matched_by}, not by slug")
    return lines
