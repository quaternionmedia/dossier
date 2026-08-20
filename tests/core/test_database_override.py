"""Which database this opens, and why one override was not enough.

`sqlite:///dossier.db` is relative to the working directory, so which database
you get depends on where you launched from -- `dossier/health.py` was written
because of a failure that came out of exactly that. There was no other way to
redirect it, so anything wanting a scratch database had to change directory,
and anything that forgot wrote into whichever `dossier.db` was underfoot.

A demo run from the repository root wrote into the operator's own data. That is
how this was found, and it is the reason `DOSSIER_DATABASE_URL` exists.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from dossier import health


def test_the_override_is_the_database_the_diagnostics_look_at(monkeypatch, tmp_path):
    """The engine honouring it and the migrations not would be worse than none.

    `db upgrade` resolves its target through `health.candidate_databases`, so an
    override that reached only the engine would migrate one database while
    every query ran against another -- and report success. That is the
    two-databases failure `health.py` exists for, reintroduced by its own fix.
    """
    target = tmp_path / "scratch.db"
    monkeypatch.setenv("DOSSIER_DATABASE_URL", f"sqlite:///{target}")
    assert health.candidate_databases() == [target]


def test_without_the_override_nothing_changes(monkeypatch, tmp_path):
    """The default is the working directory, and it stays that way."""
    monkeypatch.delenv("DOSSIER_DATABASE_URL", raising=False)
    found = health.candidate_databases(cwd=tmp_path)
    assert found[0] == tmp_path / "dossier.db"


def test_the_override_leaves_no_other_candidate(monkeypatch, tmp_path):
    """An operator who named a database meant that one.

    Mutation: append the override to the default list instead of replacing it,
    and this fails -- which is a diagnostic reporting on a database nobody
    asked about.
    """
    target = tmp_path / "scratch.db"
    monkeypatch.setenv("DOSSIER_DATABASE_URL", f"sqlite:///{target}")
    assert len(health.candidate_databases(cwd=tmp_path)) == 1


def test_a_url_this_cannot_resolve_raises_rather_than_falling_back(monkeypatch):
    """Falling back would send the caller's writes somewhere they did not ask.

    Mutation: return None on an unrecognised URL and this fails. Silently
    ignoring an override is the whole problem it was added to solve.
    """
    monkeypatch.setenv("DOSSIER_DATABASE_URL", "postgresql://elsewhere/dossier")
    with pytest.raises(ValueError) as raised:
        health.overridden_database()
    assert "sqlite" in str(raised.value)


def test_an_unset_override_is_none(monkeypatch):
    monkeypatch.delenv("DOSSIER_DATABASE_URL", raising=False)
    assert health.overridden_database() is None


def test_the_cli_reads_it_at_import(monkeypatch, tmp_path):
    """The module-level constant is what every command shares."""
    target = tmp_path / "cli.db"
    monkeypatch.setenv("DOSSIER_DATABASE_URL", f"sqlite:///{target}")
    from dossier import cli

    reloaded = importlib.reload(cli)
    try:
        assert reloaded.DATABASE_URL == f"sqlite:///{target}"
    finally:
        monkeypatch.delenv("DOSSIER_DATABASE_URL", raising=False)
        importlib.reload(cli)
