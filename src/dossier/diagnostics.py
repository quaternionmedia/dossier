"""The pair inspecting itself, for the defects a green suite does not see.

    dossier selfcheck

**EVERY CHECK HERE IS A DEFECT THAT ACTUALLY HAPPENED.** Not a category somebody
imagined: each one names the day's failure it was written from, and each one was
invisible to a full passing test run at the moment it was live.
`qmcp/selfcheck.py` says the gap out loud -- "whether a passing gate is
enforcing anything" -- and this is the other half of that sentence.

**INWARD, AND STATIC WHERE IT CAN BE.** These read this repository and its
sibling rather than the organisation's work. Most read source rather than
running the application, because a diagnostic that needs the application running
is one nobody runs when the application will not start.

**A CHECK THAT CANNOT RUN SAYS SO AND IS NOT A PASS.** `unknown` is a state
here as everywhere else in this corpus. A sibling clone that is absent, a file
that moved -- those produce `unknown`, which is not green, because a diagnostic
suite that quietly degrades to nothing is the exact thing it exists to catch.

WHAT THIS CANNOT DO. Find the class of defect nobody has hit yet. Every entry
below was added after something broke, and the honest reading of a green run is
"none of the seven things that went wrong before have gone wrong again".
"""

from __future__ import annotations

import ast
import collections
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Result:
    """What one check found, and what it was looking for."""

    name: str
    state: str
    detail: str
    found_because: str
    """The real failure this check exists because of. Not decoration: a check
    whose origin nobody can name is one nobody can judge the value of."""

    @property
    def ok(self) -> bool:
        return self.state == PASS


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if r.state == FAIL]

    @property
    def unknowns(self) -> list[Result]:
        return [r for r in self.results if r.state == UNKNOWN]

    @property
    def is_clean(self) -> bool:
        """Green only when everything ran and everything passed.

        An `unknown` is not a pass. A suite that went quiet because a path
        moved would otherwise report perfect health while checking nothing.
        """
        return bool(self.results) and not self.failures and not self.unknowns

    def summary(self) -> str:
        if not self.results:
            return "no checks ran at all, which is itself the finding"
        parts = [f"{len(self.results)} checks"]
        if self.failures:
            parts.append(f"{len(self.failures)} failed")
        if self.unknowns:
            parts.append(f"{len(self.unknowns)} could not run")
        if self.is_clean:
            parts.append("all clean")
        return ", ".join(parts)

    def render(self) -> str:
        lines = [self.summary(), ""]
        for result in self.results:
            mark = {PASS: "ok  ", FAIL: "FAIL", UNKNOWN: "??  "}[result.state]
            lines.append(f"{mark} {result.name}")
            lines.append(f"       {result.detail}")
            if result.state != PASS:
                lines.append(f"       exists because: {result.found_because}")
        return "\n".join(lines)


def here() -> Path:
    """This repository's root, from this file rather than the cwd."""
    return Path(__file__).resolve().parents[2]


def sibling(name: str) -> Path | None:
    """A clone beside this one, or None."""
    for parent in here().parents:
        candidate = parent / name
        if (candidate / ".git").exists():
            return candidate
    return None


# --- the checks ---------------------------------------------------------------


def buttons_are_handled_where_they_live() -> Result:
    """A `Button.Pressed` handler on a class that does not compose the button.

    Textual routes the message up the widget tree it was pressed in, so a
    handler on an unrelated screen is never on that path. The button looks
    wired to every text search and does nothing at all.
    """
    because = ("the Threads tab's Ingest button was composed by DossierApp and "
               "handled on ContentViewerScreen, a modal document viewer. A "
               "person typed the path to an export, pressed it, and nothing "
               "happened. A grep for the decorator found one for every button")
    source = here() / "src" / "dossier" / "tui" / "app.py"
    if not source.is_file():
        return Result("button-wiring", UNKNOWN, f"{source} is not there", because)

    composed, handled, generic = _survey_buttons(source)
    orphans = []
    for owner, ids in composed.items():
        if owner in generic:
            continue
        for button in sorted(ids - handled[owner]):
            elsewhere = sorted(c for c, s in handled.items() if button in s)
            orphans.append(f"#{button} composed by {owner}, handled by "
                           f"{elsewhere or 'nobody'}")
    total = sum(len(ids) for ids in composed.values())
    if orphans:
        return Result("button-wiring", FAIL, "; ".join(orphans), because)
    return Result("button-wiring", PASS,
                  f"{total} buttons, each handled by the class composing it",
                  because)


def composed_tabs_have_loaders() -> Result:
    """A tab that is drawn and never filled.

    The facet exists, the columns exist, the overview draws its own section
    from the same data -- and the tab stays empty because nothing routes to a
    loader for it.
    """
    because = ("the Threads tab had no entry in `_load_tab_data`, so ingesting "
               "an export reported 203 threads onto an empty table. Later the "
               "Sweep tab drew blank for a different reason in the same "
               "function: a gate that returned early when no project was "
               "selected, for a tab that is not about a project")
    source = here() / "src" / "dossier" / "tui" / "app.py"
    if not source.is_file():
        return Result("tab-loaders", UNKNOWN, f"{source} is not there", because)

    text = source.read_text(encoding="utf-8")
    composed = set(re.findall(r'TabPane\([^)]*id="(tab-[a-z-]+)"', text))
    routed = set(re.findall(r'"(tab-[a-z-]+)":\s*self\._load', text))
    # A facet tab is filled by the facet renderer rather than a named loader.
    try:
        from dossier.facets import BY_TAB

        routed |= set(BY_TAB)
    except Exception:                             # noqa: BLE001
        pass

    # AND A TAB THAT YIELDS A PANEL FILLS ITSELF. `OverviewPanel` reads in
    # `compose`, `ProjectDetailPanel` on a reactive; neither wants a loader and
    # neither is missing one. The first run of this check reported both as
    # unfilled, which is the false positive that teaches a reader to stop
    # believing the diagnostic -- worse than the defect it was hunting.
    routed |= set(re.findall(
        r'TabPane\([^)]*id="(tab-[a-z-]+)"\)\s*:\s+yield \w+Panel\(',
        text))

    missing = sorted(composed - routed)
    if missing:
        return Result("tab-loaders", FAIL,
                      f"composed but nothing fills them: {', '.join(missing)}",
                      because)
    return Result("tab-loaders", PASS,
                  f"{len(composed)} tabs, each with something that fills it",
                  because)


def the_seam_agrees_about_the_port() -> Result:
    """Two repositories that cannot import each other, holding one number."""
    because = ("dossier looked for the harness on 8000 and qmcp served on "
               "3333. The panel reported the thread archive absent while the "
               "harness was answering with 203 threads -- a message accurate "
               "about the address it tried and useless about the problem")
    harness = sibling("qmcp")
    if harness is None:
        return Result("seam-port", UNKNOWN,
                      "qmcp is not beside this clone", because)
    config = harness / "qmcp" / "config.py"
    if not config.is_file():
        return Result("seam-port", UNKNOWN, f"{config} is not there", because)

    found = re.search(r"^\s*port\s*:\s*int\s*=\s*(\d+)",
                      config.read_text(encoding="utf-8"), re.MULTILINE)
    if not found:
        return Result("seam-port", UNKNOWN,
                      "qmcp declares no `port: int = ...`", because)

    from dossier.threads import DEFAULT_PORT

    served = int(found.group(1))
    if DEFAULT_PORT != served:
        return Result("seam-port", FAIL,
                      f"panel looks on {DEFAULT_PORT}, harness serves {served}",
                      because)
    return Result("seam-port", PASS, f"both say {served}", because)


def the_seam_agrees_about_work_shapes() -> Result:
    """A vocabulary copied across a seam, checked rather than assumed."""
    because = ("`mechanical`, `judgement`, `human`, `unknown` decide which "
               "worker runs a share of a sweep. They are written out in both "
               "repositories because neither may import the other, and a "
               "silent disagreement would route work to nothing")
    harness = sibling("qmcp")
    if harness is None:
        return Result("seam-shapes", UNKNOWN,
                      "qmcp is not beside this clone", because)
    theirs = harness / "qmcp" / "sweep.py"
    if not theirs.is_file():
        return Result("seam-shapes", UNKNOWN, f"{theirs} is not there", because)

    text = theirs.read_text(encoding="utf-8")
    import dossier.sweep as ours

    disagree = []
    for name in ("MECHANICAL", "JUDGEMENT", "HUMAN", "UNKNOWN"):
        found = re.search(rf'^{name} = "([^"]+)"', text, re.MULTILINE)
        mine = getattr(ours, name, None)
        if found is None:
            disagree.append(f"{name} not declared in qmcp")
        elif found.group(1) != mine:
            disagree.append(f"{name}: qmcp {found.group(1)!r} vs {mine!r}")
    if disagree:
        return Result("seam-shapes", FAIL, "; ".join(disagree), because)
    return Result("seam-shapes", PASS, "four shapes, spelled the same on both "
                                       "sides", because)


def tests_do_not_reach_the_network() -> Result:
    """A suite whose result depends on what happens to be listening."""
    because = ("the suite reached the harness for real. With one running it "
               "saw 203 threads and two tests failed; with none it waited out "
               "a 2.25s connect timeout per call and passed. Half the runtime "
               "was that timeout, and the green run was measuring the machine")
    conftest = here() / "tests" / "conftest.py"
    if not conftest.is_file():
        return Result("no-ambient-network", UNKNOWN,
                      f"{conftest} is not there", because)
    # THE NAMED FIXTURE, AUTOUSE, FROM THE SYNTAX TREE. A first version asked
    # whether `autouse=True` appeared anywhere in the file. It does -- twice --
    # so taking `autouse` off the network fixture left the check green, and the
    # mutation that proved it was the mutation that found it.
    tree = ast.parse(conftest.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "no_ambient_network":
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            for keyword in decorator.keywords:
                if (keyword.arg == "autouse"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True):
                    return Result(
                        "no-ambient-network", PASS,
                        "an autouse fixture refuses any connection a test did "
                        "not arrange", because)
        return Result("no-ambient-network", FAIL,
                      "the network fixture exists but is not autouse, so it "
                      "only applies where somebody remembered to ask",
                      because)
    return Result("no-ambient-network", FAIL,
                  "no `no_ambient_network` fixture at all", because)


def tests_do_not_leak_module_state() -> Result:
    """A test that replaces a module attribute and never restores it."""
    because = ("ingest tests assigned `dossier.threads.request_import` "
               "directly. Under a fixed order they ran first and nothing "
               "noticed; the first randomised run failed three unrelated "
               "tests in another file. Earlier, an `importlib.reload` of "
               "`dossier.cli` broke sixty-three")
    tests = here() / "tests"
    if not tests.is_dir():
        return Result("no-leaked-state", UNKNOWN, "no tests directory", because)

    # CALIBRATED TO THE MECHANISM THAT ACTUALLY LEAKED, WHICH IS NARROWER THAN
    # "TOUCHES A MODULE". The first version flagged every `importlib.reload`
    # and reported seven findings, four of them in files that reload inside a
    # `finally` and have been green through four randomised full runs. A check
    # tuned tighter than its evidence is one people learn to wave through.
    #
    # What leaked was a module attribute assigned and never put back. The
    # restored-reload hazard is real and different -- reload re-executes into
    # the same module object, so a `from x import y` elsewhere keeps the old
    # binding -- and it is recorded as known-imperfect in the corpus's
    # open-work rather than reported here every run.
    leaks = []
    for path in sorted(tests.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        restores = "finally:" in text and "importlib.reload" in text
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(r"^\w+_module\.\w+\s*=\s*[^=]", stripped):
                leaks.append(f"{path.name}:{number} assigns and never restores")
            elif "importlib.reload(" in stripped and not restores:
                leaks.append(f"{path.name}:{number} reloads with no finally")
    if leaks:
        return Result("no-leaked-state", FAIL,
                      f"{len(leaks)} module mutation(s) outliving their test: "
                      + "; ".join(leaks[:3]), because)
    return Result("no-leaked-state", PASS,
                  "no test replaces module state without putting it back",
                  because)


def documented_routes_resolve() -> Result:
    """A published command number that opens something else, or nothing."""
    because = ("`docs/rad-commands.md` publishes a number per command, and the "
               "number is the keystrokes. A wedge added, removed or reordered "
               "renumbers everything after it -- which is why an unavailable "
               "command is greyed rather than dropped")
    sheet = here() / "docs" / "rad-commands.md"
    if not sheet.is_file():
        return Result("documented-routes", UNKNOWN,
                      f"{sheet} is not there", because)

    from dossier.rad.index import index

    published = set(re.findall(r"^\| `([0-9.]+)` \|", sheet.read_text(
        encoding="utf-8"), re.MULTILINE))
    live = {command.number for command in index()}
    missing = sorted(live - published)
    stale = sorted(published - live)
    if missing or stale:
        return Result("documented-routes", FAIL,
                      f"not on the sheet: {missing}; on the sheet and gone: "
                      f"{stale}", because)
    return Result("documented-routes", PASS,
                  f"{len(live)} commands, each on the sheet", because)


def wired_actions_exist_in_the_menu() -> Result:
    """An action the application dispatches that no wedge can produce."""
    because = ("`view.harness` sat in RAD_VIEWS with no wedge naming it, so "
               "nothing could ever commit it. Dead dispatch makes a wiring "
               "count look wider than the menu")
    try:
        from dossier.rad.index import index
        from dossier.tui.app import DossierApp
    except Exception as exc:                      # noqa: BLE001
        return Result("wired-actions", UNKNOWN, f"{type(exc).__name__}", because)

    named = {c.action for c in index() if c.action}
    dangling = sorted(set(DossierApp.RAD_HANDLED) - named)
    if dangling:
        return Result("wired-actions", FAIL,
                      f"dispatched but in no wedge: {dangling}", because)
    return Result("wired-actions", PASS,
                  f"{len(DossierApp.RAD_HANDLED)} handled actions, each named "
                  f"by a wedge", because)


def the_database_being_read_is_the_one_with_the_data() -> Result:
    """The live database, against every other one this installation might open.

    **THE ONLY CHECK HERE THAT LOOKS AT RUNTIME STATE RATHER THAN SOURCE.** The
    other eight read files in the repository and would give the same answer on
    any machine. This one cannot: it is about which database *this process*
    resolved, which is a property of the working directory and nothing else.

    A DEFECT NEEDS SOMEBODY TO BE WRONG, AND HERE NOTHING IS. `sqlite:///dossier.db`
    is relative, sqlite creates what is missing, and every panel then truthfully
    reports what it read. The failure is that an empty database and a quiet
    week render identically, which is the thing this corpus keeps saying is not
    allowed: unknown is a value, never zero.
    """
    because = ("a command run from the wrong directory created an empty "
               "`dossier.db` beside it and every view read zero. Nothing was "
               "broken and nothing said so -- the panel reported the counts of "
               "a database created seconds earlier by the act of reading it")
    try:
        from dossier.health import candidate_databases
        from dossier.sources import open_database
    except Exception as error:                     # noqa: BLE001
        return Result("live-database", UNKNOWN, f"cannot ask: {error}", because)

    live = open_database()
    if live is None:
        return Result("live-database", UNKNOWN,
                      "this installation is not on sqlite", because)

    populated = [(path, rows) for path, rows in
                 ((p, _rows_in(p)) for p in candidate_databases())
                 if rows > 0]
    live_rows = _rows_in(live)

    if live_rows > 0:
        return Result("live-database", PASS,
                      f"reading {live.name} with {live_rows} project row(s)",
                      because)
    if populated:
        where = ", ".join(str(path) for path, _ in populated)
        return Result("live-database", FAIL,
                      f"reading an empty {live} while a populated database "
                      f"exists at {where}", because)
    # **NOT "nothing has been ingested".** `candidate_databases` searches the
    # working directory and the home directory, so from anywhere else a
    # populated database is not absent -- it is out of view. Saying the first
    # would be this check committing the error it was written to catch, and it
    # did say exactly that until somebody ran it from the wrong directory.
    searched = ", ".join(str(p) for p in candidate_databases()) or "nothing"
    return Result("live-database", UNKNOWN,
                  f"{live} is empty, and the only databases visible from this "
                  f"working directory ({searched}) are empty too. This does "
                  f"not mean nothing is ingested -- a populated database "
                  f"outside this directory would not be seen from here",
                  because)


def _rows_in(path: Path) -> int:
    """Projects in a database, or 0 for one that cannot be read.

    **DOES NOT CREATE.** `sqlite3.connect` makes a file, which is the failure
    this check exists for -- a check that produced the defect while looking for
    it would report every candidate present and every one empty.
    """
    import sqlite3

    if not path.is_file():
        return 0
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            return db.execute("select count(*) from project").fetchone()[0]
    except Exception:                              # noqa: BLE001
        return 0


CHECKS: tuple[Callable[[], Result], ...] = (
    buttons_are_handled_where_they_live,
    composed_tabs_have_loaders,
    the_seam_agrees_about_the_port,
    the_seam_agrees_about_work_shapes,
    tests_do_not_reach_the_network,
    tests_do_not_leak_module_state,
    documented_routes_resolve,
    wired_actions_exist_in_the_menu,
    the_database_being_read_is_the_one_with_the_data,
)


def run(checks: tuple[Callable[[], Result], ...] = CHECKS) -> Report:
    """Every check, each surviving its neighbours' failures.

    A check that raised would otherwise take the diagnostic with it, and the
    remaining seven are exactly what somebody needs when one is broken.
    """
    found = Report()
    for check in checks:
        try:
            found.results.append(check())
        except Exception as exc:                  # noqa: BLE001
            found.results.append(Result(
                getattr(check, "__name__", "?"), UNKNOWN,
                f"the check itself raised: {type(exc).__name__}: {exc}",
                "a diagnostic that dies on its own bug reports nothing"))
    return found


# --- reading source -----------------------------------------------------------


def _survey_buttons(source: Path):
    """(composed, handled, generic) by class name, from the AST.

    From the syntax tree rather than a text search, because that is the
    difference this check exists to make: a grep finds the decorator anywhere
    in the file and cannot tell which class it is on.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    composed = collections.defaultdict(set)
    handled = collections.defaultdict(set)
    generic = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                continue
            for sub in ast.walk(child):
                if (isinstance(sub, ast.Call)
                        and getattr(sub.func, "id", "") == "Button"):
                    for keyword in sub.keywords:
                        if (keyword.arg == "id"
                                and isinstance(keyword.value, ast.Constant)):
                            composed[node.name].add(keyword.value.value)
                if isinstance(sub, ast.FunctionDef):
                    if sub.name == "on_button_pressed":
                        generic.add(node.name)
                    for decorator in sub.decorator_list:
                        if (isinstance(decorator, ast.Call)
                                and getattr(decorator.func, "id", "") == "on"
                                and len(decorator.args) >= 2
                                and isinstance(decorator.args[1], ast.Constant)):
                            handled[node.name].add(
                                decorator.args[1].value.lstrip("#"))
    return composed, handled, generic
