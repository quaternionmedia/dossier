"""The sidebar's work board: deltas, grouped by phase.

WHY THIS IS NOT THE PROJECT TREE WITH A FILTER. The sidebar's entity filter
matched project rows whose *names* were addresses -- `owner/repo/delta/ls` --
so selecting "Deltas" listed fake project rows rather than deltas. Those rows
were test residue, and `dossier/ingest.py` refuses to create more of them:
inventing a project from a delta lets a typo in another system populate this
one. A delta is a `ProjectDelta`, and this reads that table.

WHAT IT SHOWS. Open deltas first, grouped by phase in lifecycle order, each
under the project it belongs to. Closed phases are grouped last and collapsed,
because a board whose top half is finished work is a board nobody scrolls.

SELECTING A DELTA SELECTS ITS PROJECT. Every per-project tab reads
`selected_project`, so a board that set only the delta would leave the rest of
the screen describing whatever was selected before -- stale content that looks
current, which is worse than empty content.
"""

from __future__ import annotations

from typing import Any

from textual.widgets import Tree

from dossier.models.schemas import DeltaPhase, Project, ProjectDelta

# Lifecycle order, open phases first. `DeltaPhase` declares them in this order
# already; naming the closed ones here keeps "what is on deck" in one place.
CLOSED_PHASES = (DeltaPhase.COMPLETE, DeltaPhase.ABANDONED)


def phase_name(delta: Any) -> str:
    return getattr(delta.phase, "value", str(delta.phase))


def group_by_phase(deltas: list[Any]) -> list[tuple[str, list[Any]]]:
    """Deltas in lifecycle order, open phases first, empty phases dropped.

    A phase with nothing in it is a heading a reader has to skip past. The
    overview's `Deltas by phase` table is where a zero is a fact worth showing;
    a board is for what there is.
    """
    buckets: dict[str, list[Any]] = {}
    for delta in deltas:
        buckets.setdefault(phase_name(delta), []).append(delta)

    order = [p for p in DeltaPhase if p not in CLOSED_PHASES]
    order += [p for p in DeltaPhase if p in CLOSED_PHASES]
    return [(p.value, buckets[p.value]) for p in order if buckets.get(p.value)]


def label_for(delta: Any, project_name: str | None) -> str:
    """One line: what the work is, and the evidence it exists.

    The branch or pull request is the part a reader acts on -- it is what they
    check out or open -- so it is on the line rather than in a detail pane.
    """
    bits = [delta.title or delta.name]
    if project_name:
        bits.append(f"({project_name.split('/')[-1]})")
    if delta.pr_number:
        bits.append(f"#{delta.pr_number}")
    elif delta.branch_name:
        bits.append(delta.branch_name)
    return "  ".join(bits)


class DeltaBoard(Tree):
    """Deltas by phase. Reads on mount and on demand, never on a timer."""

    def __init__(self, session_factory, **kwargs) -> None:
        super().__init__("Deltas", **kwargs)
        self.session_factory = session_factory
        self.show_root = False

    def on_mount(self) -> None:
        self.refresh_board()

    def refresh_board(self) -> None:
        from sqlmodel import select

        self.clear()
        self.root.expand()

        with self.session_factory() as session:
            deltas = list(session.exec(
                select(ProjectDelta).order_by(ProjectDelta.updated_at.desc())
            ).all())
            names = {
                p.id: (p.full_name or p.name)
                for p in session.exec(select(Project)).all()
            }
            for delta in deltas:
                session.expunge(delta)

        for phase, rows in group_by_phase(deltas):
            branch = self.root.add(f"{phase}  ({len(rows)})", expand=phase not in
                                   {p.value for p in CLOSED_PHASES})
            for delta in rows:
                branch.add_leaf(
                    label_for(delta, names.get(delta.project_id)),
                    data={"type": "delta", "delta": delta,
                          "project_id": delta.project_id},
                )
