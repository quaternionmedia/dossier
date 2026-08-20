"""The panel and the harness agree about where the harness is.

A CONSTANT COPIED ACROSS A SEAM STAYS TRUE ONLY IF SOMETHING CHECKS IT.
`dossier.threads.DEFAULT_PORT` and `qmcp/config.py`'s `port` are the same
number written in two repositories that cannot import each other. They were
8000 and 3333 for long enough that the panel's settings screen reported the
thread archive absent while the harness was serving two hundred threads --
a message accurate about the address it tried and useless about the problem.

Skipped with a reason where the sibling clone is not present, because the
alternative is a test that passes by doing nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dossier.threads import DEFAULT_PORT


def qmcp_config() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "qmcp" / "qmcp" / "config.py"
        if candidate.is_file():
            return candidate
    return None


def test_the_panel_defaults_to_the_port_the_harness_serves():
    """THE ONE THAT MATTERS.

    Read out of qmcp's source rather than restated here, so this cannot be the
    third copy of the same number.

    Mutation: change either side and this fails.
    """
    config = qmcp_config()
    if config is None:
        pytest.skip("qmcp is not beside this clone, so its port cannot be read")

    text = config.read_text(encoding="utf-8")
    found = re.search(r"^\s*port\s*:\s*int\s*=\s*(\d+)", text, re.MULTILINE)
    assert found, f"no `port: int = ...` in {config}; the check needs updating"

    served = int(found.group(1))
    assert DEFAULT_PORT == served, (
        f"the panel looks on {DEFAULT_PORT} and the harness serves on {served}. "
        f"One of {config} and dossier/threads.py is wrong.")


def test_the_port_can_still_be_overridden():
    """The default is a convenience. An operator running the harness elsewhere
    says so, and nothing here should have made that harder."""
    import os

    from dossier.threads import base_url

    previous = os.environ.get("DOSSIER_HARNESS_PORT")
    try:
        os.environ["DOSSIER_HARNESS_PORT"] = "9999"
        assert base_url().endswith(":9999")
    finally:
        if previous is None:
            os.environ.pop("DOSSIER_HARNESS_PORT", None)
        else:
            os.environ["DOSSIER_HARNESS_PORT"] = previous


def test_a_nonsense_override_falls_back_rather_than_raising():
    """A typo in an environment variable should not crash a dashboard."""
    import os

    from dossier.threads import base_url

    previous = os.environ.get("DOSSIER_HARNESS_PORT")
    try:
        os.environ["DOSSIER_HARNESS_PORT"] = "not-a-port"
        assert base_url().endswith(f":{DEFAULT_PORT}")
    finally:
        if previous is None:
            os.environ.pop("DOSSIER_HARNESS_PORT", None)
        else:
            os.environ["DOSSIER_HARNESS_PORT"] = previous
