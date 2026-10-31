"""`dossier serve` and `dossier docs serve` start where the loop looks for them.

`dossier dev doctor` looks for the panel on `OWN_PORT`, or wherever
`DOSSIER_PORT` moves it, and suggests `uv run dossier serve` when nothing
answers there. The command it suggests has to start on that same port.

Nothing here binds a port: `uvicorn.run` and the mkdocs call are replaced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import uvicorn
from click.testing import CliRunner

from dossier import cli as cli_module, loop
from dossier.cli import DOCS_PORT, cli
from dossier.loop import PANEL
from dossier.threads import HOST, OWN_PORT

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def served(monkeypatch):
    """What `uvicorn.run` was asked to bind."""
    calls: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(kw, app=app))
    return calls


def test_serve_starts_on_the_panels_port(monkeypatch, served):
    monkeypatch.delenv(PANEL.env_var, raising=False)

    result = CliRunner().invoke(cli, ["serve"])

    assert result.exit_code == 0, result.output
    assert served["port"] == OWN_PORT == loop.port_for(PANEL) == 1618
    assert served["host"] == HOST


def test_dossier_port_moves_serve_and_the_doctor_together(monkeypatch, served):
    """Mutation: `envvar` dropped from `--port` -- serve stayed on 1618."""
    monkeypatch.setenv(PANEL.env_var, "16180")

    result = CliRunner().invoke(cli, ["serve"])

    assert result.exit_code == 0, result.output
    assert served["port"] == loop.port_for(PANEL) == 16180


def test_a_port_on_the_command_line_wins(monkeypatch, served):
    monkeypatch.setenv(PANEL.env_var, "16180")

    CliRunner().invoke(cli, ["serve", "--port", "16181"])

    assert served["port"] == 16181


def test_the_docs_preview_sits_beside_the_panel(monkeypatch):
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(cli_module, "_mkdocs", lambda *args: seen.append(args) or 0)

    result = CliRunner().invoke(cli, ["docs", "serve"])

    assert result.exit_code == 0, result.output
    assert seen == [("serve", "--dev-addr", f"{HOST}:{DOCS_PORT}")]
    assert DOCS_PORT == OWN_PORT + 1


def test_mkdocs_alone_serves_where_dossier_docs_serve_does():
    """A bare `mkdocs serve` reads `dev_addr`; without it, mkdocs takes 8000."""
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    found = re.search(r"^dev_addr:\s*(\S+)\s*$", text, re.MULTILINE)

    assert found, "mkdocs.yml has no dev_addr"
    assert found.group(1) == f"{HOST}:{DOCS_PORT}"


def test_no_server_defaults_to_8000():
    """8000 is the port anything grabs; qm's allocation exists to avoid it."""
    source = (ROOT / "src" / "dossier" / "cli.py").read_text(encoding="utf-8")

    assert not re.search(r"default\s*=\s*8000\b", source)
