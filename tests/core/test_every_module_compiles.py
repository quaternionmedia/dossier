"""Every module in this package parses, and none indents with tabs.

**PROPAGATED FROM `qm`**, where it was written after a syntax check was being
typed by hand after every edit — `handbook/test-posture.md` in the governance
corpus. It arrives here because the failure it catches happened here: an escaped
`\\n` written through a shell became a real newline inside a string literal, and
the module stopped parsing. Each time it was found by running the check
manually, and a check performed from memory is performed when somebody
remembers.

**ONE CASE PER PROPERTY, NOT ONE PER FILE.** This began parameterised over every
module — 103 ids for a floor check that has never legitimately failed. A sweep
should name every offender in one message; parameterised, three broken files are
three separate failures a reader collects one at a time. What is lost is the
filename in the test *id*, and it is in the failure message instead with the
line number, which is where it is more useful.

WHAT THIS DOES NOT CHECK. That a module works, that its imports resolve, or that
it does what its name says. Those are the other tests here. This is the floor,
and it is the floor because everything above it needs the file to parse first.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "dossier"


def modules() -> list[Path]:
    """Every module in the package, sorted so failures list in one order."""
    return sorted(
        path for path in PACKAGE.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_there_are_modules_to_check():
    """A glob that matched nothing would make every check below vacuous, and a
    vacuous check reports green.

    Mutation: point `modules()` at an empty directory and this fails.
    """
    assert len(modules()) > 10, f"only {len(modules())} module(s) under {PACKAGE}"


def test_every_module_parses():
    """Mutation: introduce a syntax error anywhere in the package and this
    fails, naming the file and the line."""
    broken = []
    for module in modules():
        try:
            compile(module.read_text(encoding="utf-8"), str(module), "exec")
        except SyntaxError as error:
            broken.append(
                f"{module.relative_to(PACKAGE).as_posix()}:{error.lineno}: "
                f"{error.msg}")

    assert not broken, "these do not parse:\n  " + "\n  ".join(broken)


def test_no_module_indents_with_tabs():
    """Tabs mixed with spaces parse in some files and raise `TabError` in
    others depending on what is above them — so the failure appears in a file
    nobody just edited.

    Mutation: put a tab at the start of an indented line and this fails.
    """
    offenders = []
    for module in modules():
        lines = [
            number
            for number, line in enumerate(
                module.read_text(encoding="utf-8").splitlines(), start=1)
            if line[: len(line) - len(line.lstrip())].count("\t")
        ]
        if lines:
            offenders.append(
                f"{module.relative_to(PACKAGE).as_posix()}: line(s) {lines[:5]}")

    assert not offenders, ("these indent with tabs:\n  "
                           + "\n  ".join(offenders))
