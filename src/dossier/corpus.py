"""Invoking the corpus's own generators to refresh its documents.

## Why this is its own module

The corpus's convention is that **a renderer may not run a command**: a view
that can shell out becomes a second place a governance rule gets defined, and
two definitions drift. The corpus enforces it on its own two renderers by
asserting the word `subprocess` does not appear in their source.

That property is worth keeping here, so the read-and-render path --
`dossier.parsers.governance`, `dossier.models.governance`, and
`dossier.governance` -- runs no commands at all, and `tests/test_governance.py`
asserts it. Refreshing is a different act from rendering: it is the corpus
regenerating its own documents, on a human's say-so, and it belongs on the
other side of that line. Hence a separate module, imported only by the CLI.

## What refreshing does and does not do

It runs the corpus's generators, in the corpus checkout, and nothing else.
dossier computes no governance fact here -- the generators remain the single
definition of every figure in both documents, and dossier only asks them to
run. The commands are the ones the documents name for themselves:
`harness-status.json` carries `reading.refresh`, and `governance-status.yaml`
names its tool in `generator.tool`.

Two consequences a caller should expect:

* **It writes into the corpus checkout.** Both documents are committed files;
  refreshing modifies that repository's working tree, and the change is a
  human's to review and commit.
* **It reads the network.** The generators query the host for every repository
  in the org, so a refresh takes far longer than a load and fails without
  credentials. That is why it is opt-in rather than the default.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Governance first: the harness generator can read the governance document,
#: so refreshing in the other order would build the harness view on a stale
#: input and report it as current.
GENERATORS = (
    ("governance-status.yaml", "ci/governance_status.py", ("--write", "governance-status.yaml")),
    ("harness-status.json", "ci/harness_status.py", ("--no-local", "--write", "harness-status.json")),
)

#: The generators query every repository in the org over the network. This is
#: generous on purpose -- a refresh that is killed halfway leaves a document
#: nobody can date.
DEFAULT_TIMEOUT_SECONDS = 900


@dataclass
class RefreshOutcome:
    """What happened to one generator."""

    document: str
    script: str
    ran: bool
    ok: bool = False
    reason: Optional[str] = None
    output: str = ""

    @property
    def summary(self) -> str:
        if not self.ran:
            return f"skipped - {self.reason}"
        if self.ok:
            return "regenerated"
        return f"failed - {self.reason}"


def can_refresh(corpus_dir: Path | str) -> Optional[str]:
    """Why this checkout cannot be refreshed, or ``None`` if it can.

    Returns a reason rather than a boolean so a caller can print something
    actionable. The common case is a project's vendored corpus, which is
    pinned to a branch cut from `main` and carries no `ci/` at all -- absent
    by construction rather than broken.
    """
    root = Path(corpus_dir)
    if not root.exists():
        return f"{root} does not exist"
    if not (root / ".git").exists() and not (root / "ci").exists():
        return f"{root} does not look like a corpus checkout"
    missing = [script for _, script, _ in GENERATORS if not (root / script).exists()]
    if missing:
        return (
            f"{root} has no {', '.join(missing)} -- this checkout is on a branch "
            "without the generators, so there is nothing here to run"
        )
    return None


def refresh(
    corpus_dir: Path | str,
    offline: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[RefreshOutcome]:
    """Run the corpus's generators in ``corpus_dir``.

    Never raises for a generator that fails: each outcome carries its own
    result, because one document regenerating and the other failing is a real
    state a caller has to be able to report rather than a reason to abort.
    """
    root = Path(corpus_dir)
    blocked = can_refresh(root)
    if blocked:
        return [
            RefreshOutcome(document=document, script=script, ran=False, reason=blocked)
            for document, script, _ in GENERATORS
        ]

    outcomes = []
    for document, script, args in GENERATORS:
        command = [sys.executable, script, *args]
        if offline and script.endswith("governance_status.py"):
            # Only the governance generator has an offline mode. Passing it to
            # the other one would fail on an unrecognised argument, which
            # would read as the refresh being broken.
            command.append("--offline")
        try:
            finished = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            outcomes.append(
                RefreshOutcome(
                    document=document,
                    script=script,
                    ran=True,
                    ok=False,
                    reason=f"timed out after {timeout}s",
                )
            )
            continue
        except OSError as exc:
            outcomes.append(
                RefreshOutcome(
                    document=document, script=script, ran=True, ok=False, reason=str(exc)
                )
            )
            continue

        tail = (finished.stderr or finished.stdout or "").strip().splitlines()
        outcomes.append(
            RefreshOutcome(
                document=document,
                script=script,
                ran=True,
                ok=finished.returncode == 0,
                reason=None if finished.returncode == 0 else (
                    tail[-1] if tail else f"exit status {finished.returncode}"
                ),
                output="\n".join(tail[-3:]),
            )
        )
    return outcomes
