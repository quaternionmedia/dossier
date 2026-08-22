"""Every module in this package parses, and none indents with tabs.

**PROPAGATED FROM `qm`**, where it was written after a syntax check was being
typed by hand after every edit — `handbook/test-posture.md` in the governance
corpus. It arrives here because the failure it catches happened here four times
in one session: an escaped `\n` written through a shell became a real newline
inside a string literal, and the module stopped parsing.

Each time it was found by running the check manually. A check performed from
memory is performed when somebody remembers, and the person most likely to
forget is the one who has just made a large edit.

WHAT THIS DOES NOT CHECK. That a module works, that its imports resolve, or that
it does what its name says. Those are the other tests here. This is the floor,
and it is the floor because everything above it needs the file to parse first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "dossier"


def modules() -> list[Path]:
    """Every module in the package, sorted so failures name the same file."""
    return sorted(
        path for path in PACKAGE.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_there_are_modules_to_check():
    """A glob that matched nothing would make every case below vanish, and a
    file with no cases passes silently.

    Mutation: point `modules()` at an empty directory and this fails.
    """
    assert len(modules()) > 10, f"only {len(modules())} module(s) under {PACKAGE}"


@pytest.mark.parametrize("module", modules(),
                         ids=lambda p: p.relative_to(PACKAGE).as_posix())
def test_the_module_parses(module: Path):
    """Mutation: introduce a syntax error anywhere in the package and this
    fails, naming the file and the line."""
    try:
        compile(module.read_text(encoding="utf-8"), str(module), "exec")
    except SyntaxError as error:
        pytest.fail(f"{module.relative_to(PACKAGE).as_posix()} does not parse: "
                    f"line {error.lineno}, {error.msg}")


@pytest.mark.parametrize("module", modules(),
                         ids=lambda p: p.relative_to(PACKAGE).as_posix())
def test_the_module_has_no_stray_tabs_in_indentation(module: Path):
    """Tabs mixed with spaces parse in some files and raise `TabError` in
    others, depending on what is above them — so the failure appears in a file
    nobody just edited.

    Mutation: put a tab at the start of an indented line and this fails.
    """
    offenders = [
        number
        for number, line in enumerate(
            module.read_text(encoding="utf-8").splitlines(), start=1)
        if line[: len(line) - len(line.lstrip())].count("\t")
    ]
    assert not offenders, (
        f"{module.relative_to(PACKAGE).as_posix()} indents with tabs on "
        f"line(s) {offenders[:5]}")
