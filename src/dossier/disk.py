"""Running the corpus's disk tooling, and the recipes for reaching for it.

## Why this is its own module

The same reason `dossier/corpus.py` is one: **a renderer may not run a
command**. Refreshing and measuring are acts, not views, and they belong on the
other side of that line from anything that reads or presents. This module is
imported only by the CLI, and `tests/test_disk.py` asserts the word
`subprocess` appears nowhere in the presentation path.

## What this does not do, which is most of the point

**dossier computes no disk fact here.** It does not walk a directory, sum a
cache, or decide what a safe threshold is. Every figure comes from
`ci/disk_status.py` in the corpus, and every deletion is decided by
`ci/disk-policy.yaml` there. A number this view wants and the document lacks is
a change to the corpus generator, reviewed once, so every reader gets it -- not
a computation here, which would be a second definition of a rule the corpus
already owns.

That is the whole hygiene claim of this module, and it is testable rather than
aspirational: there is no measurement code below to drift.

## Three differences from the governance refresh, all of them deliberate

`corpus.py` regenerates two documents *into the corpus checkout*, because both
are committed files. The disk document is the opposite on every axis:

* **It is never committed, anywhere.** Free space, cache sizes and paths under
  a home directory are one machine at one moment. The corpus generator refuses
  to write inside the corpus; this module refuses to write inside *any* git
  repository, because dossier is a repository too and the rule that protects
  one should not stop at the boundary between them.
* **It reads no network.** A refresh here is a filesystem walk, so it is fast,
  works offline, and is safe to run on a whim.
* **Deleting is a separate command with a separate gate.** `reclaim` is a dry
  run unless `apply=True` is passed explicitly, and nothing in dossier's
  configuration can change that default.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: The corpus scripts this module drives. Named rather than discovered so that
#: a checkout missing one is reported as missing that file, by name, instead of
#: failing later with whatever the shell says about an absent path.
TOOLS = {
    "status": "ci/disk_status.py",
    "dashboard": "ci/disk_dashboard.py",
    "reclaim": "ci/disk_reclaim.py",
}

#: The policy is the reviewed artifact, and a checkout without it can measure
#: nothing meaningful even if the scripts are present.
POLICY = "ci/disk-policy.yaml"

#: A filesystem walk over a few large caches, not a network call. Generous
#: enough for a cold cache on a spinning disk; short enough that a wedged run
#: does not look like a slow one.
DEFAULT_TIMEOUT_SECONDS = 600

#: Where the document lives: dossier's own machine-scoped directory, which
#: already holds config.json and is in no repository. Not a temp path -- the
#: point of writing it at all is that a later command can read the same one.
DOCUMENT_NAME = "disk-status.json"


def document_path() -> Path:
    """The machine-scoped path the document is written to and read from."""
    return Path.home() / ".dossier" / DOCUMENT_NAME


def inside_a_repository(path: Path) -> Optional[Path]:
    """The repository root this path would land in, or ``None``.

    Generalised from the corpus generator's own `inside_corpus`, which knows
    about one repository. dossier is a second one, and a path under either is
    equally wrong: the document describes a machine, so committing it anywhere
    publishes one person's Tuesday as a fact every later reader inherits.
    """
    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def can_measure(corpus_dir: Path | str) -> Optional[str]:
    """Why this checkout cannot measure, or ``None`` if it can.

    A reason rather than a boolean, so the caller can print something
    actionable. The common case is a project's vendored corpus: it is pinned to
    a branch cut from `main`, carries no `ci/` at all, and is therefore empty by
    construction rather than broken. Saying which of those two it is, is the
    difference between a reader fixing their command and a reader filing a bug.
    """
    root = Path(corpus_dir)
    if not root.exists():
        return f"{root} does not exist"
    if not (root / ".git").exists() and not (root / "ci").exists():
        return f"{root} does not look like a corpus checkout"
    missing = [name for name in (*TOOLS.values(), POLICY) if not (root / name).exists()]
    if missing:
        return (
            f"{root} has no {', '.join(missing)} -- this checkout is on a branch "
            "without the disk tooling, so there is nothing here to run"
        )
    return None


@dataclass
class ToolOutcome:
    """What happened when one corpus script ran.

    Carries the exit status rather than collapsing it to a boolean, because
    `disk_status.py --check` uses 2 for critical and 1 for low: a caller that
    only knew "failed" would report a full disk and a warm one identically.
    """

    tool: str
    argv: Sequence[str] = field(default_factory=tuple)
    ran: bool = False
    status: Optional[int] = None
    stdout: str = ""
    reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.ran and self.status == 0

    @property
    def summary(self) -> str:
        if not self.ran:
            return f"skipped - {self.reason}"
        if self.status == 0:
            return "ok"
        return f"exit {self.status}" + (f" - {self.reason}" if self.reason else "")


def _run(
    corpus_dir: Path | str,
    script: str,
    args: Sequence[str],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ToolOutcome:
    """One corpus script, in its own checkout. Never raises.

    Run with ``cwd`` set to the corpus so the scripts' own relative defaults --
    `ci/disk-policy.yaml` above all -- resolve the way they do when a person
    runs them there by hand. Two invocation paths that resolve defaults
    differently is a bug report nobody can reproduce.
    """
    root = Path(corpus_dir)
    argv = [sys.executable, script, *args]
    try:
        finished = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ToolOutcome(
            tool=script, argv=argv, ran=True, status=None,
            reason=f"timed out after {timeout}s",
        )
    except OSError as exc:
        return ToolOutcome(tool=script, argv=argv, ran=True, status=None, reason=str(exc))

    tail = (finished.stderr or "").strip().splitlines()
    return ToolOutcome(
        tool=script,
        argv=argv,
        ran=True,
        status=finished.returncode,
        stdout=(finished.stdout or "").rstrip(),
        reason=(tail[-1] if tail and finished.returncode != 0 else None),
    )


def check(corpus_dir: Path | str) -> ToolOutcome:
    """Ask the corpus whether any volume is under its floor.

    Writes nothing. This is the cheap call -- the one worth putting in front of
    a build -- and its exit status is the corpus's, unmodified: 2 critical,
    1 low or unreadable, 0 fine.
    """
    return _run(corpus_dir, TOOLS["status"], ["--check"])


def measure(
    corpus_dir: Path | str,
    document: Optional[Path] = None,
    search_roots: Sequence[Path] = (),
) -> ToolOutcome:
    """Write a fresh disk document to the machine-scoped path.

    Refuses before running, not after: the generator walks a hundred gigabytes
    of cache, and discovering the destination was rejected at the end wastes
    exactly the minutes that made somebody reach for the tool.
    """
    target = Path(document) if document is not None else document_path()
    repository = inside_a_repository(target)
    if repository is not None:
        return ToolOutcome(
            tool=TOOLS["status"],
            ran=False,
            reason=(
                f"{target} is inside the repository at {repository}. Every fact "
                "in this document is one machine at one moment, so it is not "
                "written anywhere git would pick it up"
            ),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    args = ["--write", str(target)]
    for root in search_roots:
        args += ["--search-root", str(root)]
    return _run(corpus_dir, TOOLS["status"], args)


def render(
    corpus_dir: Path | str,
    document: Optional[Path] = None,
    fmt: str = "md",
    out: Optional[Path] = None,
) -> ToolOutcome:
    """Render an existing document. Reads it, never regenerates it."""
    target = Path(document) if document is not None else document_path()
    if not target.exists():
        return ToolOutcome(
            tool=TOOLS["dashboard"],
            ran=False,
            reason=f"no document at {target} -- measure first",
        )
    args = [str(target), "--format", fmt]
    if out is not None:
        args += ["--out", str(out)]
    return _run(corpus_dir, TOOLS["dashboard"], args)


def reclaim(
    corpus_dir: Path | str,
    allow: str = "refetched",
    apply: bool = False,
    targets: Sequence[str] = (),
    until_free: Optional[float] = None,
    search_roots: Sequence[Path] = (),
) -> ToolOutcome:
    """Free space, through the corpus's reclaimer.

    ``apply`` defaults to False here as well as in the corpus tool. Both
    defaults are load-bearing and the duplication is deliberate: a wrapper that
    defaulted the other way would make the safe-looking command the dangerous
    one, and the operator would have no way to tell from the command line they
    typed. `tests/test_disk.py` asserts the default on both sides.
    """
    args = ["--allow", allow]
    if apply:
        args.append("--apply")
    for name in targets:
        args += ["--target", name]
    if until_free is not None:
        args += ["--until-free", str(until_free)]
    for root in search_roots:
        args += ["--search-root", str(root)]
    return _run(corpus_dir, TOOLS["reclaim"], args)


def parse_plan(text: str) -> tuple[Optional[int], Optional[int]]:
    """(bytes, paths) from the reclaimer's own summary line.

    Read from its output rather than recomputed, so this number is exactly the
    one the reclaimer stands behind. A total assembled here would be a second
    definition of what the run did, and the two would part company the first
    time the policy grew an entry this parser did not expect.

    The line is `Removed 22 paths, 104.5GB (104500000000 bytes)`. The exact
    count is preferred over the rounded one wherever it is present: a 5KB
    sweep rounds to `0.0GB`, and storing that as what the run removed would
    record a zero for a run that removed something. Older output without the
    parenthetical still parses, at GB precision.
    """
    import re

    match = re.search(
        r"(?:Would remove|Removed)\s+(\d+)\s+paths?,\s+([0-9.]+)GB"
        r"(?:\s+\((\d+)\s+bytes\))?",
        text,
    )
    if not match:
        return None, None
    exact = match.group(3)
    size = int(exact) if exact is not None else int(float(match.group(2)) * 10**9)
    return size, int(match.group(1))


def reclaim_and_record(
    session,
    corpus_dir: Path | str,
    allow: str = "refetched",
    apply: bool = False,
    targets: Sequence[str] = (),
    until_free: Optional[float] = None,
    search_roots: Sequence[Path] = (),
    keep: Optional[int] = None,
):
    """Read, reclaim, read again, and store the run as the pair it sits between.

    The orchestration lives here rather than in `disk_store` because it runs
    commands, and it is called from the CLI and from an explicit keypress in
    the TUI -- never from a render. A view that measured on its way to drawing
    would take a reading nobody asked for, and would do it every repaint.

    Two readings bracket the run, and the second is taken **even when the run
    fails**. A reclaim that errored halfway has still removed something, and a
    record with no second reading would report that as nothing.

    Returns (the stored DiskReclaim, the ToolOutcome).
    """
    from . import disk_store

    machine = disk_store.this_machine()
    retention = keep if keep is not None else disk_store.DEFAULT_KEEP

    def read_now():
        """Measure, then store. Both, in that order, and never just the second.

        Loading without measuring would bracket the run with whatever document
        happened to be lying around -- possibly hours old -- and every change
        since would be attributed to this run. `freed` has to be the difference
        the run made, which means both readings are taken for it.
        """
        taken = measure(corpus_dir, search_roots=search_roots)
        if not taken.ok:
            return disk_store.LoadOutcome(
                False, document_path(), f"the reading failed: {taken.summary}"
            )
        return disk_store.load_document(session, machine=machine, keep=retention)

    record = disk_store.DiskReclaim(
        machine=machine,
        allow=allow,
        targets=",".join(targets) or None,
        applied=apply,
        outcome="planned",
    )

    before = read_now()
    record.before_snapshot_id = before.snapshot_id
    if not before.loaded:
        # No first reading means no way to say what the run changed. It still
        # runs -- freeing space is the point and the operator asked -- but the
        # record says outright that the effect was not measured, rather than
        # storing a zero nobody established.
        record.freed_unknown = f"no reading before the run: {before.reason}"

    outcome = reclaim(
        corpus_dir,
        allow=allow,
        apply=apply,
        targets=targets,
        until_free=until_free,
        search_roots=search_roots,
    )
    record.exit_status = outcome.status
    record.output = (outcome.stdout or "")[-4000:]
    record.claimed_bytes, record.claimed_paths = parse_plan(outcome.stdout or "")

    if not outcome.ok:
        record.outcome = "failed"
        record.reason = outcome.summary

    if apply:
        after = read_now()
        record.after_snapshot_id = after.snapshot_id
        if not after.loaded:
            record.freed_unknown = f"no reading after the run: {after.reason}"
        elif before.loaded:
            record.freed_bytes = disk_store.freed_between(
                session, before.snapshot_id, after.snapshot_id
            )
            if record.freed_bytes is None:
                record.freed_unknown = (
                    "the volume holding this stack could not be read in both "
                    "snapshots, so what came back was not measured"
                )
        if outcome.ok:
            record.outcome = "applied"
    elif outcome.ok:
        record.outcome = "planned"

    from .models import utcnow

    record.finished_at = utcnow()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record, outcome


# --- the cookbook, which is one source and two surfaces --------------------
#
# Recipes are data. `dossier disk cookbook` prints them at the terminal, where
# the work happens, and the same tuple generates `docs/disk.md`, which is
# committed. A test regenerates the page and compares it to the committed copy,
# so the two cannot drift -- the failure this guards against is a docs page
# that describes last month's flags confidently.


@dataclass(frozen=True)
class Recipe:
    """One thing a person actually wants to do, and the line that does it."""

    task: str
    command: str
    when: str
    note: Optional[str] = None


COOKBOOK: tuple[Recipe, ...] = (
    Recipe(
        task="Am I about to run out?",
        command="dossier disk check",
        when="Before a build, a container pull, or anything that writes a lot. "
        "It writes no document and takes about a second.",
        note="Exits 2 when a volume is critical and 1 when one is low or "
        "unreadable, so it works in front of `&&` or as a scheduled task.",
    ),
    Recipe(
        task="What is actually eating the disk?",
        command="dossier disk status",
        when="Once check says something. Measures every target in the corpus "
        "policy and prints the agent view, largest first.",
        note="The document lands in ~/.dossier/disk-status.json -- outside "
        "every repository, because it describes this machine and no other.",
    ),
    Recipe(
        task="See it as a page rather than a table",
        command="dossier disk status --html",
        when="When you want to hand somebody the picture, or read the "
        "thresholds and tiers with their explanations attached.",
    ),
    Recipe(
        task="What grew since last time?",
        command="dossier disk delta",
        when="The question a single reading cannot answer, and the one that "
        "matters when the problem keeps coming back.",
        note="Only prints a number where subtracting was honest. A target "
        "nobody could measure at one end, or one that is in only one of the "
        "two readings, gets a word -- unknown, new, gone -- because the "
        "arithmetic would otherwise invent a change nobody observed.",
    ),
    Recipe(
        task="Keep a history rather than a reading",
        command="dossier disk load",
        when="Measures, then stores the result as a snapshot. Run it whenever "
        "you would have run `status`; the deltas come for free.",
        note="Appends rather than replaces, which is the difference between "
        "this and `governance load`. Old snapshots are pruned per machine, so "
        "a second machine sharing a store cannot evict this one's history.",
    ),
    Recipe(
        task="See all of it in the dashboard",
        command="dossier disk dashboard",
        when="Measure, store and open the TUI on the Disk tab, in one "
        "command. --no-load opens on what is already stored.",
        note="The tab is machine-wide, so it renders with no project "
        "selected. Volume change is FREE space: a negative number is the disk "
        "filling up.",
    ),
    Recipe(
        task="Free the space that costs nothing",
        command="dossier disk reclaim",
        when="Always run this first. It is a dry run: it prints what it would "
        "remove and removes nothing.",
        note="Add --apply when the plan looks right. The default tier is "
        "`refetched` -- caches the owning tool downloads again by itself.",
    ),
    Recipe(
        task="Reclaim from the dashboard, and watch it come back",
        command="dossier disk dashboard   then  x  then  X",
        when="On the Disk tab. `x` plans and removes nothing; `X` carries out "
        "the plan and re-measures, so the table redraws with what returned.",
        note="Two keys, not one with a confirmation dialog -- a dialog is one "
        "stray Enter from deleting a hundred gigabytes, and it is the part "
        "people learn to dismiss. `X` refuses without a plan from this "
        "session, and the dashboard reclaims at the refetched tier only. "
        "Widening belongs where somebody types the word.",
    ),
    Recipe(
        task="What did I actually get back?",
        command="dossier disk reclaims",
        when="After any reclaim. Every run is stored as the pair of readings "
        "it sits between, so what it did is measured rather than claimed.",
        note="Two columns that are not the same number: `claimed` is what the "
        "reclaimer removed, `freed` is what the volume gave back. They "
        "diverge when something else was writing, or when the space was "
        "freed inside a container disk that does not shrink -- Docker's "
        "prune is exactly this, and the gap is the whole point of storing "
        "both.",
    ),
    Recipe(
        task="What did the whole cleanup session free?",
        command="dossier disk reclaims --compose",
        when="After several runs. Chains them into one delta over the whole "
        "span.",
        note="Composed from the outermost readings, never by adding the runs "
        "up: an unknown is not zero, and a sum would launder a run nobody "
        "measured into a confident total. If the runs do not meet end to end "
        "it says so -- the figures stay right, but the span then holds "
        "changes no run caused.",
    ),
    Recipe(
        task="Free one specific thing",
        command="dossier disk reclaim --target nvidia-ota-artifacts --apply",
        when="When one target dominates and you would rather not touch the "
        "rest. Target names come from `dossier disk status`.",
        note="An unknown name is an error rather than a silent no-op, because "
        "a typo that quietly does nothing reads as a clean machine.",
    ),
    Recipe(
        task="I need N gigabytes before a build",
        command="dossier disk reclaim --until-free 60 --apply",
        when="When there is a number you have to hit. Stops as soon as the "
        "volume is at or above it rather than clearing everything.",
    ),
    Recipe(
        task="Go past the free tier",
        command="dossier disk reclaim --allow rebuilt --apply",
        when="When the cheap tier was not enough. Adds browser binaries, "
        "node_modules and virtual environments.",
        note="Costs an explicit `uv sync` / `npm ci` / `playwright install` in "
        "each project afterwards. Do not reach for it before going offline. "
        "The tiers are a ratchet: this permits `refetched` too, and there is "
        "no way to permit an expensive tier while excluding a cheap one.",
    ),
    Recipe(
        task="Add something the policy does not know about",
        command="$EDITOR <corpus>/ci/disk-policy.yaml",
        when="When you catch yourself deleting something by hand twice.",
        note="Every target carries what it costs to get the bytes back, and an "
        "entry without that classification is refused rather than assumed. It "
        "is a reviewed change in the corpus, so the next person inherits the "
        "reasoning instead of rediscovering it.",
    ),
    Recipe(
        task="It says the checkout has no disk tooling",
        command="dossier disk status --corpus-dir ../qm",
        when="When the vendored governance/qm is the checkout that was found.",
        note="Expected, not broken. A project's vendored corpus is pinned to a "
        "branch cut from the corpus's main, and the tooling is not on main "
        "yet, so that path is empty by construction. Point at a corpus "
        "checkout that carries ci/. The default starts working on its own once "
        "the corpus change lands and this project's pin is bumped past it.",
    ),
    Recipe(
        task="db upgrade says the table already exists",
        command="dossier db stamp head",
        when="After pulling the disk tables for the first time, on a store "
        "that any dossier command has already touched.",
        note="Expected. Every command calls init_db, which runs create_all "
        "and builds missing tables before your subcommand runs -- so the "
        "tables exist by the time you could migrate. Stamping records the "
        "revision without re-running DDL that has already been applied. Same "
        "wrinkle, and the same fix, as the governance tables in 005.",
    ),
    Recipe(
        task="A Windows console raises UnicodeEncodeError",
        command='$env:PYTHONIOENCODING = "utf-8"',
        when="Once per shell, before any of the above. The corpus tooling "
        "writes em dashes and this group passes its output through.",
        note="Same prep as the governance commands, and for the same reason -- "
        "docs/governance.md carries the long version. A cp1252 console raises "
        "rather than mangling, so the failure is loud and looks like a bug in "
        "the tool.",
    ),
    Recipe(
        task="Docker's target says unknown",
        command="docker system df",
        when="When the daemon is stopped. An unmeasurable target is reported "
        "as unknown with its reason, never as empty.",
        note="Pruning frees space inside the VHDX; it does not shrink the file, "
        "which only grows. Compacting it needs Docker stopped and is "
        "deliberately not automated.",
    ),
)


def cookbook_markdown() -> str:
    """The committed docs page, generated from COOKBOOK.

    Regenerated and compared in the test suite, so this function and
    `docs/disk.md` cannot disagree. Editing the page by hand is therefore a
    failing test rather than a silent divergence -- which is the only reason
    the page can be trusted after a flag changes.
    """
    lines = [
        "<!-- Generated from dossier.disk.COOKBOOK by "
        "`dossier disk cookbook --write docs/disk.md`.",
        "     Edit the recipes there, not this page: tests/test_disk.py "
        "regenerates it and",
        "     compares, so a hand edit here fails the suite. -->",
        "",
        "# Disk — a cookbook",
        "",
        "Recipes for keeping this workstation off the floor. Every command "
        "below runs the",
        "corpus's own disk tooling; dossier measures nothing and decides "
        "nothing here.",
        "",
        "The same recipes are available where the work happens:",
        "",
        "```sh",
        "dossier disk cookbook",
        "```",
        "",
        "## How the pieces fit",
        "",
        "| Artifact | Lives in | Holds |",
        "|---|---|---|",
        "| `ci/disk-policy.yaml` | the corpus, committed | every place the "
        "tooling may free space, and what it costs to get each one back |",
        "| `ci/disk_status.py` | the corpus | measures the policy against this "
        "host; deletes nothing |",
        "| `ci/disk_dashboard.py` | the corpus | renders the document; runs no "
        "commands |",
        "| `ci/disk_reclaim.py` | the corpus | acts, and only on what the "
        "policy names |",
        "| `~/.dossier/disk-status.json` | this machine, never committed | the "
        "measurement, with its own age and reading instructions inside it |",
        "| `disk_snapshot` / `disk_volume` / `disk_target` | dossier's store, "
        "migration `006_disk` | one row per reading, appended, so there is "
        "something to compare against |",
        "| `disk_reclaim` | dossier's store, migration `007_reclaim` | one row "
        "per run, holding the two readings it sits between |",
        "",
        "**A reclaim is a delta.** It is a reading, an action, and another "
        "reading — so what",
        "it did is the same shape as any change that merely happened, carries "
        "the same",
        "refusals, and composes with the rest. There is no second vocabulary "
        "for “what the",
        "cleanup achieved”, because a second vocabulary would need its own "
        "unknown handling",
        "and would get it wrong somewhere.",
        "",
        "The tables are **append-only**, which is the one place this domain "
        "departs from",
        "governance. A governance load replaces what it read, because the only "
        "interesting",
        "governance fact is the current one. The question worth asking of a "
        "disk is what",
        "*grew*, and no single reading can answer it.",
        "",
        "Each snapshot carries the machine it describes. A store is a file "
        "somebody can",
        "copy, which is a weaker boundary than the repository the generator "
        "refuses to",
        "write into, so the scope travels in the row — and a delta across two "
        "machines is",
        "refused rather than averaged into a trend that happened on neither.",
        "",
        "**Safety is the cost of recovery, not a guess at risk.** Three tiers: "
        "`refetched`",
        "(the owning tool downloads it again, unprompted), `rebuilt` (a "
        "command you run),",
        "`destructive` (nothing comes back). They are a ratchet — permitting "
        "one permits",
        "every cheaper one — so no invocation empties the recycle bin while "
        "sparing a",
        "download cache.",
        "",
        "## Recipes",
        "",
    ]
    for recipe in COOKBOOK:
        lines.append(f"### {recipe.task}")
        lines.append("")
        lines.append("```sh")
        lines.append(recipe.command)
        lines.append("```")
        lines.append("")
        lines.append(recipe.when)
        if recipe.note:
            lines.append("")
            lines.append(f"> {recipe.note}")
        lines.append("")
    lines.append("## What binds anything added here")
    lines.append("")
    lines.append(
        "- **dossier computes no disk fact.** A figure this view wants and the "
        "document lacks is a change to the corpus generator, reviewed once, so "
        "every reader gets it."
    )
    lines.append(
        "- **The document is never committed, in either repository.** It "
        "describes one machine at one moment, and `dossier disk status` "
        "refuses a destination inside any git repository rather than trusting "
        "anyone to remember."
    )
    lines.append(
        "- **A dry run is the default on both sides of the boundary.** Neither "
        "the corpus reclaimer nor this wrapper can be configured to delete by "
        "default."
    )
    return "\n".join(lines) + "\n"
