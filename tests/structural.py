"""Assert what a module does, by parsing it rather than by scanning its text.

These repositories carry long explanatory docstrings that necessarily name the
thing they forbid — a module that must never shell out says so, in prose, using
the word `subprocess`. A text scan therefore fails on the explanation. Worse,
it is inert in the direction that matters: delete the paragraph, add the call,
and the scan goes green.

Three of these were found in one session:

* ``assert "disk_usage" not in source`` matched the docstring saying the
  renderer must never call it
* ``assert "threshold" not in source`` matched prose about thresholds
* ``assert "subprocess" not in source`` matched the sentence explaining why the
  renderer may not run a command

So the guards live here, once, and answer structural questions:

    assert not imports_of(module) & {"subprocess", "shutil"}
    assert "rmtree" not in calls_of(module)

The corpus does the same where it matters — its
``test_evidence_cannot_read_the_claim_it_is_evidence_for`` asserts on
``inspect.signature`` for exactly this reason.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _tree(module) -> ast.Module:
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))


def imports_of(module) -> set[str]:
    """Top-level package names this module imports, however it imports them.

    Catches `import subprocess`, `import subprocess as sp`, and
    `from subprocess import run` alike, because all three are the same fact.
    """
    found: set[str] = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def calls_of(module) -> set[str]:
    """Names this module calls, by attribute or bare name.

    `shutil.rmtree(...)` contributes `rmtree`; `rmtree(...)` contributes the
    same, so a guard does not have to know which import style was used.
    """
    return {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(_tree(module))
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }


#: Importing any of these is how a module gains the ability to run a command.
#: `os` is deliberately absent: path handling imports it legitimately, and the
#: os-based ways of running something are caught by COMMAND_CALLS instead.
COMMAND_IMPORTS = {"subprocess"}

#: Calls that run a command whatever was imported to reach them.
COMMAND_CALLS = {
    "system",
    "popen",
    "Popen",
    "check_call",
    "check_output",
    "execv",
    "execvp",
    "execvpe",
    "spawnv",
}


def runs_commands(module) -> set[str]:
    """What lets this module run a command, or an empty set.

    Returns the offending names rather than a boolean so a failure says which
    one it found.
    """
    return (imports_of(module) & COMMAND_IMPORTS) | (calls_of(module) & COMMAND_CALLS)


def repo_root() -> Path:
    """The repository root, found rather than counted to.

    Tests reached it as `Path(__file__).parent.parent` -- a count of the
    directories between a test file and the root. Organising the suite into
    categories moved every test one level deeper and broke tests that had
    nothing to do with the change. Anchoring on a file that exists only at the
    root makes the depth irrelevant.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("no pyproject.toml above the test suite")
