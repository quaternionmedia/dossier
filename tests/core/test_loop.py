"""The three-process development loop, and the question reachability cannot answer.

`dossier.loop` exists because a 200 proves a server is listening and nothing
about which server it is. All three processes in this loop serve FastAPI and
answer a health path identically, so the only thing that tells them apart is
what they call themselves.

Nothing here opens a socket: `httpx.get` is replaced. The suite has an autouse
fixture refusing any connection a test did not arrange, and a check whose
whole subject is talking to servers is exactly the one that should not be the
exception.
"""

from __future__ import annotations

import httpx
import pytest

from dossier import loop
from dossier.loop import HARNESS, PANEL, SPEECH, Service


class _Answer:
    """A stand-in response carrying one OpenAPI title."""

    def __init__(self, title: str | None, status: int = 200, json_ok: bool = True):
        self.status_code = status
        self._title = title
        self._json_ok = json_ok

    def json(self):
        if not self._json_ok:
            raise ValueError("not json")
        return {"info": {"title": self._title}} if self._title else {}


def _answers(monkeypatch, response):
    """Make every probe get `response`, or raise it if it is an exception."""

    def fake_get(url, timeout=None):
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(httpx, "get", fake_get)


# ─── ports ────────────────────────────────────────────────────────────────────

def test_a_service_sits_on_its_declared_port_by_default(monkeypatch):
    monkeypatch.delenv(HARNESS.env_var, raising=False)

    assert loop.port_for(HARNESS) == 3141


def test_an_env_var_moves_one_service_and_not_the_others(monkeypatch):
    """Two sessions on one workstation is the normal case here."""
    monkeypatch.setenv(HARNESS.env_var, "31410")
    monkeypatch.delenv(PANEL.env_var, raising=False)

    assert loop.port_for(HARNESS) == 31410
    assert loop.port_for(PANEL) == 1618


def test_an_unparseable_port_falls_back_rather_than_crashing(monkeypatch):
    monkeypatch.setenv(HARNESS.env_var, "not-a-number")

    assert loop.port_for(HARNESS) == 3141


def test_the_allocation_is_read_from_where_it_is_declared():
    """`dossier.threads` owns these numbers; a second copy is a second drift."""
    from dossier import threads

    rows = dict((name, declared) for name, declared, _, _ in loop.allocation())

    assert rows["harness (qmcp)"] == threads.DEFAULT_PORT
    assert rows["panel (dossier)"] == threads.OWN_PORT
    assert rows["maps (codecarto)"] == threads.CODECARTO_PORT


# ─── identity ─────────────────────────────────────────────────────────────────

def test_the_right_service_answering_is_a_pass(monkeypatch):
    _answers(monkeypatch, _Answer(HARNESS.title))

    probe = loop.probe(HARNESS)

    assert probe.ok
    assert probe.state == "pass"


def test_the_wrong_service_answering_is_not_a_pass(monkeypatch):
    """The whole reason this module exists.

    Something is listening on the harness's port, so every reachability check
    is green — and it is the speech engine. dossier looked on 8000 while the
    harness served 3333 and reported the archive absent, which was accurate
    about the address it tried and useless about the problem.
    """
    _answers(monkeypatch, _Answer(SPEECH.title))

    probe = loop.probe(HARNESS)

    assert probe.listening is True
    assert probe.ok is False
    assert probe.state == "wrong"
    assert SPEECH.title in probe.detail and HARNESS.title in probe.detail


def test_nothing_listening_on_a_required_service_is_absent(monkeypatch):
    _answers(monkeypatch, httpx.ConnectError("refused"))

    probe = loop.probe(HARNESS)

    assert probe.listening is False
    assert probe.state == "absent"


def test_nothing_listening_on_an_optional_service_is_only_off(monkeypatch):
    """A loop with no speech engine still reads the harness queue."""
    _answers(monkeypatch, httpx.ConnectError("refused"))

    assert loop.probe(SPEECH).state == "off"
    assert loop.probe(PANEL).state == "off"


def test_a_non_200_from_the_identity_path_is_not_a_pass(monkeypatch):
    _answers(monkeypatch, _Answer(None, status=404))

    probe = loop.probe(HARNESS)

    assert probe.ok is False
    assert "404" in probe.detail


def test_something_that_is_not_json_is_not_a_pass(monkeypatch):
    """A proxy or a captive portal answers 200 with HTML."""
    _answers(monkeypatch, _Answer(None, json_ok=False))

    probe = loop.probe(HARNESS)

    assert probe.ok is False
    assert "not JSON" in probe.detail


def test_every_service_in_the_loop_has_a_distinct_title():
    """Titles are the discriminator, so two the same would identify nothing."""
    titles = [s.title for s in loop.LOOP]

    assert len(set(titles)) == len(titles), titles


def test_only_the_harness_is_required():
    required = {s.role for s in loop.LOOP if s.required}

    assert required == {"harness"}


# ─── database isolation ───────────────────────────────────────────────────────

def test_an_unset_database_url_is_not_isolated(monkeypatch, tmp_path):
    """The suite purges the file the CLI falls back to, so this is the hazard."""
    monkeypatch.delenv("DOSSIER_DATABASE_URL", raising=False)
    (tmp_path / loop.REAL_DATABASE).write_bytes(b"")

    result = loop.isolation(root=tmp_path)

    assert result.isolated is False
    assert loop.REAL_DATABASE in result.detail


def test_a_database_url_pointing_elsewhere_is_isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DOSSIER_DATABASE_URL", "sqlite:///scratch/dev.db")
    (tmp_path / loop.REAL_DATABASE).write_bytes(b"")

    assert loop.isolation(root=tmp_path).isolated is True


def test_a_database_url_naming_the_real_file_is_not_isolated(monkeypatch, tmp_path):
    """Setting the variable is not the same as pointing it somewhere safe."""
    monkeypatch.setenv("DOSSIER_DATABASE_URL", f"sqlite:///{loop.REAL_DATABASE}")
    (tmp_path / loop.REAL_DATABASE).write_bytes(b"")

    result = loop.isolation(root=tmp_path)

    assert result.isolated is False
    assert loop.REAL_DATABASE in result.detail


def test_an_in_memory_url_is_isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DOSSIER_DATABASE_URL", "sqlite:///:memory:")

    assert loop.isolation(root=tmp_path).isolated is True


def test_no_database_on_disk_yet_is_nothing_to_lose(monkeypatch, tmp_path):
    monkeypatch.delenv("DOSSIER_DATABASE_URL", raising=False)

    result = loop.isolation(root=tmp_path)

    assert result.isolated is True
    assert result.rows == 0


@pytest.mark.parametrize("service", [HARNESS, SPEECH, PANEL])
def test_every_service_says_how_to_start_it(service: Service):
    """A doctor that says something is missing and not how to get it is a nag."""
    assert service.start
    assert service.repo
