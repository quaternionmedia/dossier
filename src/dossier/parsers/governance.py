"""Readers for the corpus's two generated governance documents.

`governance-status.yaml` says where every project stands against the corpus.
`harness-status.json` says which pull request slots are held and what work is
in flight. They share a convention deliberately, so one parser shape reads
both.

**This module reads. It never writes back.** Both documents are generated in
the corpus by tools that read git and the host; a renderer that edits its own
input creates a second source of truth for the same fact, which is the seam
this design exists to prevent. If a view wants a fact the document lacks, that
is a change to the generator in the corpus -- reviewed once, and every reader
gets it -- never a computation here.

## Why this is a plain class rather than a `BaseParser`

`BaseParser` dispatches on file extension and returns `list[DocumentSection]`:
it is the contract for parsing a project's *documentation*. A governance
document is neither dispatched by extension nor expressible as document
sections, so subclassing it would mean implementing `supported_extensions`
and returning the wrong type. `GitHubParser` is the precedent followed here --
a plain class, imported directly by its caller, registered nowhere. The choice
is deliberate rather than incidental, because both precedents exist in this
package and picking by accident is how a codebase ends up with two.

## The unknown convention

Any field may be the mapping ``{"unknown": "<reason>"}``. It means the fact
could not be established, and says why. It is not zero, not empty, and not
compliant. It can replace a scalar (``open_prs``) or an entire subtree
(``repository``, ``adoption``), so every read goes through :func:`field`
rather than through ``dict.get``.

``null`` is not unknown. ``last_propagation: null`` means *never propagated*,
which is an established fact and renders differently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

__all__ = [
    "DocumentUnavailable",
    "Field",
    "GovernanceDocument",
    "GovernanceProject",
    "HarnessDocument",
    "HarnessRepository",
    "Thread",
    "field",
    "load_governance",
    "load_harness",
]


class DocumentUnavailable(Exception):
    """A document could not be read, with the reason a reader should show.

    Raised rather than returned as an empty document on purpose. An absent
    document and a document describing nothing are different states, and a
    caller that cannot tell them apart renders the first as an empty happy
    table -- which reads as "nothing is wrong" when the truth is "nobody
    knows".
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"{self.path}: {reason}")


@dataclass(frozen=True)
class Field:
    """One value from a document, and whether anybody could establish it.

    ``unknown`` holds the document's stated reason when the fact could not be
    established. ``value`` is meaningful only when ``unknown`` is ``None``; a
    ``None`` value with no reason is a real null in the document.
    """

    value: Any = None
    unknown: Optional[str] = None

    @property
    def is_unknown(self) -> bool:
        return self.unknown is not None

    @property
    def is_null(self) -> bool:
        """A stated null: established, and the answer is nothing."""
        return self.value is None and self.unknown is None

    def or_none(self) -> Any:
        """The value, or ``None`` if unknown. For storing in a value column."""
        return None if self.is_unknown else self.value


def field(node: Any, *path: str) -> Field:
    """Read ``path`` out of ``node``, honouring the unknown convention.

    Checks for an unknown mapping at **every** level, because the convention
    replaces whole subtrees as well as leaves: ``adoption`` itself can be
    unknown, in which case ``adoption.submodule.branch`` is unknown for that
    reason rather than missing.

    A path that simply is not present returns an empty ``Field`` -- absent and
    unknown are not the same thing, and only the document may declare the
    second.
    """
    current = node
    for key in path:
        unknown = _unknown_reason(current)
        if unknown is not None:
            return Field(unknown=unknown)
        if not isinstance(current, dict) or key not in current:
            return Field()
        current = current[key]
    unknown = _unknown_reason(current)
    if unknown is not None:
        return Field(unknown=unknown)
    return Field(value=current)


def _unknown_reason(node: Any) -> Optional[str]:
    """The reason, if ``node`` is an unknown mapping. Otherwise ``None``.

    The test is a single-key mapping, not merely the presence of an
    ``unknown`` key: a real object that happens to carry an ``unknown`` field
    alongside others is data, not a declaration.
    """
    if isinstance(node, dict) and set(node) == {"unknown"}:
        reason = node["unknown"]
        return reason if isinstance(reason, str) else str(reason)
    return None


def parse_timestamp(raw: Any) -> Optional[datetime]:
    """Parse a document timestamp, tolerating the trailing ``Z``.

    Returns ``None`` for anything unparseable rather than raising. A malformed
    timestamp should not stop a document loading -- it degrades one column,
    and the alternative is a reader that fails closed on the whole picture.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def age_hours(generated_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
    """Hours since the document was generated, or ``None`` if unknowable.

    Presentation, not a governance fact: the document carries `generated_at`
    precisely so a view can say how old it is. A dashboard that looks live and
    is three days old is worse than one that admits its age, because the first
    stops people checking.

    Both sides are normalised, not just one. Timestamps arrive tz-aware from a
    freshly parsed document and naive from SQLite, which has no tz-aware type,
    and coercing only the reference raises on the second case.
    """
    if generated_at is None:
        return None
    reference = now or datetime.now(timezone.utc)
    return (_aware(reference) - _aware(generated_at)).total_seconds() / 3600.0


def _aware(value: datetime) -> datetime:
    """Treat a naive timestamp as UTC. Every stored timestamp is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass
class GovernanceProject:
    """One project's row in `governance-status.yaml`."""

    name: str
    observed_at: Optional[datetime] = None
    branch_ref: Optional[str] = None
    branch_commit: Optional[str] = None
    behind_corpus: Field = dataclass_field(default_factory=Field)
    ahead_of_corpus: Field = dataclass_field(default_factory=Field)
    last_propagation: Field = dataclass_field(default_factory=Field)
    seed_drift: Field = dataclass_field(default_factory=Field)
    records_total: Optional[int] = None
    records_ratified: Optional[int] = None
    open_prs: Field = dataclass_field(default_factory=Field)

    @property
    def open_prs_count(self) -> Optional[int]:
        """How many, when the document could say. ``None`` when it could not."""
        if self.open_prs.is_unknown or self.open_prs.value is None:
            return None
        value = self.open_prs.value
        return len(value) if isinstance(value, (list, tuple)) else None


@dataclass
class GovernanceDocument:
    """`governance-status.yaml`, parsed."""

    path: Path
    schema: Optional[int]
    generated_at: Optional[datetime]
    corpus_commit: Optional[str]
    projects: list[GovernanceProject]

    def age_hours(self, now: Optional[datetime] = None) -> Optional[float]:
        return age_hours(self.generated_at, now)


@dataclass
class Thread:
    """One line of work in flight."""

    repository_name: str
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
    updated_at: Optional[datetime] = None
    idle_hours: Optional[float] = None
    stalled: bool = False


@dataclass
class HarnessRepository:
    """One repository's row in `harness-status.json`."""

    name: str
    slug: Optional[str] = None
    role: Optional[str] = None
    phase: Optional[str] = None
    phase_source: Optional[str] = None
    precondition: Field = dataclass_field(default_factory=Field)
    precondition_missing: list[str] = dataclass_field(default_factory=list)
    slot_state: Optional[str] = None
    slot_unknown: Optional[str] = None
    slot_open_prs: Optional[int] = None
    slot_violations: Optional[str] = None
    release_state: Optional[str] = None
    release_unknown: Optional[str] = None
    release_latest: Optional[str] = None
    release_annotated: Optional[bool] = None
    release_unreleased_commits: Optional[int] = None
    threads: list[Thread] = dataclass_field(default_factory=list)


@dataclass
class HarnessDocument:
    """`harness-status.json`, parsed."""

    path: Path
    schema: Optional[int]
    generated_at: Optional[datetime]
    staleness_budget_hours: Optional[float]
    local_layer_scope: Optional[str]
    repositories: list[HarnessRepository]

    def age_hours(self, now: Optional[datetime] = None) -> Optional[float]:
        return age_hours(self.generated_at, now)


def _read(path: Path, loader) -> Any:
    path = Path(path)
    if not path.exists():
        raise DocumentUnavailable(path, "the document is not at this path")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentUnavailable(path, f"could not be read: {exc}") from exc
    if not text.strip():
        raise DocumentUnavailable(path, "the document is empty")
    try:
        data = loader(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise DocumentUnavailable(path, f"could not be parsed: {exc}") from exc
    if not isinstance(data, dict):
        raise DocumentUnavailable(
            path, f"the document is a {type(data).__name__}, not a mapping"
        )
    return data


def load_governance(path: Path | str) -> GovernanceDocument:
    """Read `governance-status.yaml`.

    Raises :class:`DocumentUnavailable` when the document is absent,
    unreadable, empty, or not a mapping. It never returns a document with no
    projects to stand in for one of those.
    """
    path = Path(path)
    data = _read(path, yaml.safe_load)

    raw_projects = data.get("projects")
    if not isinstance(raw_projects, list):
        raise DocumentUnavailable(
            path,
            "no 'projects' list -- the document exists but does not have the "
            "shape this reader was built against",
        )

    projects = []
    for entry in raw_projects:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        projects.append(
            GovernanceProject(
                name=str(entry["name"]),
                observed_at=parse_timestamp(entry.get("observed_at")),
                branch_ref=field(entry, "branch", "ref").or_none(),
                branch_commit=field(entry, "branch", "commit").or_none(),
                behind_corpus=field(entry, "branch", "behind_corpus"),
                ahead_of_corpus=field(entry, "branch", "ahead_of_corpus"),
                last_propagation=field(entry, "branch", "last_propagation"),
                seed_drift=field(entry, "seed", "adr_template_vs_corpus"),
                records_total=field(entry, "records", "total").or_none(),
                records_ratified=field(entry, "records", "ratified").or_none(),
                open_prs=field(entry, "open_prs"),
            )
        )

    return GovernanceDocument(
        path=path,
        schema=data.get("schema"),
        generated_at=parse_timestamp(data.get("generated_at")),
        corpus_commit=field(data, "corpus", "commit").or_none(),
        projects=projects,
    )


def load_harness(path: Path | str) -> HarnessDocument:
    """Read `harness-status.json`.

    The document has two layers with different scopes. ``slots`` is read over
    the network and is true for everyone; the local layer is one machine's
    clones and is true only for whoever ran the collector. They are in one
    document because they are read together, and ``local_layer_scope`` carries
    the caveat -- a view that drops it has lost the only thing separating the
    two. It is surfaced here so a renderer can show it.
    """
    path = Path(path)
    data = _read(path, json.loads)

    raw_repos = data.get("repositories")
    if not isinstance(raw_repos, list):
        raise DocumentUnavailable(
            path,
            "no 'repositories' list -- the document exists but does not have "
            "the shape this reader was built against",
        )

    repositories = []
    for entry in raw_repos:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        name = str(entry["name"])

        slot_state, slot_unknown, slot_count, violations = _slots(entry)
        release = field(entry, "release")
        missing = field(entry, "governance", "missing")
        repositories.append(
            HarnessRepository(
                name=name,
                slug=entry.get("slug"),
                role=entry.get("role"),
                phase=entry.get("phase"),
                phase_source=entry.get("phase_source"),
                precondition=field(entry, "governance", "precondition"),
                precondition_missing=(
                    [str(m) for m in missing.value]
                    if isinstance(missing.value, list)
                    else []
                ),
                slot_state=slot_state,
                slot_unknown=slot_unknown,
                slot_open_prs=slot_count,
                slot_violations=violations,
                release_state=(
                    None if release.is_unknown else field(entry, "release", "state").or_none()
                ),
                release_unknown=release.unknown,
                release_latest=field(entry, "release", "latest").or_none(),
                release_annotated=field(entry, "release", "annotated").or_none(),
                release_unreleased_commits=field(
                    entry, "release", "unreleased_commits"
                ).or_none(),
                threads=_threads(name, entry.get("threads")),
            )
        )

    return HarnessDocument(
        path=path,
        schema=data.get("schema"),
        generated_at=parse_timestamp(data.get("generated_at")),
        staleness_budget_hours=field(data, "reading", "staleness_budget_hours").or_none(),
        local_layer_scope=field(data, "generator", "local_layer_scope").or_none(),
        repositories=repositories,
    )


def _slots(entry: dict) -> tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
    """Read the slot layer: state, unknown reason, open PR count, violations.

    The verdict is the document's ``compliant`` boolean, not something derived
    here from counting pull requests -- the rule has an automation exclusion
    and a per-base exemption, and re-implementing either would be a second
    definition of a governance rule that could disagree with the first.

    ``compliant`` missing or non-boolean yields ``None``, which renders as "no
    answer". It deliberately does not fall back to "ok": an earlier version of
    this function read a key that does not exist, found nothing, and reported
    every repository in the org as compliant -- including one that was over.
    """
    slots = field(entry, "slots")
    if slots.is_unknown:
        return None, slots.unknown, None, None

    open_prs = field(entry, "slots", "open_prs")
    if open_prs.is_unknown:
        return None, open_prs.unknown, None, None
    count = len(open_prs.value) if isinstance(open_prs.value, list) else None

    compliant = field(entry, "slots", "compliant")
    if compliant.is_unknown:
        return None, compliant.unknown, count, None
    if isinstance(compliant.value, bool):
        state = "ok" if compliant.value else "over"
    else:
        state = None

    raw_violations = field(entry, "slots", "violations").value
    numbers: list[str] = []
    if isinstance(raw_violations, list):
        for violation in raw_violations:
            if isinstance(violation, dict):
                for number in violation.get("numbers") or []:
                    numbers.append(f"#{number}")
    return state, None, count, ", ".join(numbers) or None


def _threads(repository_name: str, raw: Any) -> list[Thread]:
    if not isinstance(raw, list):
        return []
    threads = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        threads.append(
            Thread(
                repository_name=repository_name,
                name=str(entry["name"]),
                stage=entry.get("stage"),
                pr=entry.get("pr"),
                base=entry.get("base"),
                title=entry.get("title"),
                author=entry.get("author"),
                additions=field(entry, "delta", "additions").or_none(),
                deletions=field(entry, "delta", "deletions").or_none(),
                commits=field(entry, "delta", "commits").or_none(),
                changed_files=field(entry, "delta", "changed_files").or_none(),
                mergeable_state=field(entry, "delta", "mergeable_state").or_none(),
                updated_at=parse_timestamp(field(entry, "delta", "updated_at").or_none()),
                idle_hours=entry.get("idle_hours"),
                stalled=bool(entry.get("stalled", False)),
            )
        )
    return threads
