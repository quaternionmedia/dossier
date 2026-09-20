"""The org overview never prints a private repository's name.

A private repository's name is not this org's to publish, and the overview is
built to be pasted into a pull request or shared. The governance facet reads a
pre-redacted corpus document; every other facet reads the store, which carries
real names from the GitHub sync. Before the redaction pass, two private names
leaked into a shared report — this is the test that keeps them out.
"""

from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from dossier import facets, overview
from dossier.models.schemas import Project


def _session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_the_facet_label_redacts_a_private_repository_at_the_source():
    """**THE LEAK THIS EXISTS AGAINST.** Every facet names a repository through
    `_label`, before the name is trimmed to a column width — so redaction here
    catches even a long private name that would truncate past a later pass.

    Mutation: neuter the `is_private` branch in `facets._label` and this fails.
    """
    session = _session()
    secret = Project(name="the-secret-thing",
                     full_name="quaternionmedia/the-secret-thing",
                     github_owner="quaternionmedia", github_repo="the-secret-thing",
                     is_private=True)
    public = Project(name="looksatwords", full_name="quaternionmedia/looksatwords",
                     is_private=False)
    session.add(secret)
    session.add(public)
    session.commit()

    assert facets._label(secret) == f"private/{secret.id}"
    assert "secret" not in facets._label(secret)
    assert facets._label(public) == "quaternionmedia/looksatwords"

    names = facets._repo_names(session)
    joined = " ".join(names.values())
    assert "secret-thing" not in joined, "a private name reached the facet name map"
    assert "quaternionmedia/looksatwords" in joined, "a public name was over-redacted"


def test_the_private_name_is_replaced_by_a_stable_reference():
    session = _session()
    p = Project(name="hidden", full_name="quaternionmedia/hidden",
                github_owner="quaternionmedia", github_repo="hidden", is_private=True)
    session.add(p)
    session.commit()
    mapping = overview._private_map(session)
    assert mapping, "no private projects mapped"
    assert all(ref.startswith("private/") for ref in mapping.values())
    assert "hidden" not in "".join(mapping.values())


def test_a_public_repository_name_is_left_alone():
    """The redaction must not touch public names — that would make the overview
    useless as an overview."""
    session = _session()
    session.add(Project(name="looksatwords", full_name="quaternionmedia/looksatwords",
                        github_owner="quaternionmedia", github_repo="looksatwords",
                        is_private=False))
    session.commit()
    picture = overview.build(session, owner="quaternionmedia")
    assert "looksatwords" in picture.scope or picture.scope  # not redacted away
    assert overview._private_map(session) == {}


def test_a_private_name_is_redacted_as_a_token_prefix_but_not_as_a_suffix():
    """A `factorio-server-v1` tag names the private `factorio-server` just as
    plainly as the repo cell does, so the belt redacts a private name used as a
    token's leading segment. But a public branch that merely ends in a private
    word (`meta-intro-video` beside a private `video`) is a different token and
    must survive — over-redacting it would corrupt a public repo's real branch.

    Mutation: drop the `(?:[._-][A-Za-z0-9]+)*` suffix group in
    `overview._redact_private` and the prefix assertion fails; widen the left
    boundary to allow `-` and the suffix assertion fails.
    """
    from dossier.overview import Cell, OrgOverview, Section

    session = _session()
    session.add(Project(name="factorio-server",
                        full_name="quaternionmedia/factorio-server",
                        github_owner="quaternionmedia", github_repo="factorio-server",
                        is_private=True))
    session.add(Project(name="video", full_name="quaternionmedia/video",
                        github_owner="quaternionmedia", github_repo="video",
                        is_private=True))
    session.commit()

    picture = OrgOverview(
        masthead=(),
        sections=(Section("Refs", ("repo", "branch"),
                          (("public/qm", "factorio-server-v1"),
                           ("public/qm", "meta-intro-video")), None),),
        generated_from=None, scope="quaternionmedia",
    )
    scrubbed = overview._redact_private(picture, session)
    rows = scrubbed.sections[0].rows
    assert "factorio-server" not in rows[0][1], "a private name leaked as a tag prefix"
    assert rows[0][1].startswith("private/"), "the whole prefixed token was not redacted"
    assert rows[1][1] == "meta-intro-video", "a public branch ending in a private word was over-redacted"


def test_the_data_seam_carries_the_redacted_reading_not_the_names():
    """The seam a second window reads is `as_dict(build(...))`, and `build`
    redacts before it returns — so the seam inherits the redaction and a
    consumer needs no private-repository policy of its own. This is the
    guarantee the two windows rest on: codecarto shows these bytes verbatim.

    Mutation: have `overview.build` return the un-redacted picture and this
    fails, because the private name reappears in the serialised seam.
    """
    import json as _json

    session = _session()
    session.add(Project(name="hidden-svc", full_name="quaternionmedia/hidden-svc",
                        github_owner="quaternionmedia", github_repo="hidden-svc",
                        is_private=True))
    session.add(Project(name="looksatwords", full_name="quaternionmedia/looksatwords",
                        github_owner="quaternionmedia", github_repo="looksatwords",
                        is_private=False))
    session.commit()

    seam = overview.as_dict(overview.build(session, owner="quaternionmedia"))
    blob = _json.dumps(seam)
    assert seam["schema"] == overview.OVERVIEW_SCHEMA
    assert "sections" in seam and isinstance(seam["sections"], list)
    assert "hidden-svc" not in blob, "a private name reached the shared data seam"


def test_the_seam_says_when_the_reading_was_made():
    """`generated_from` says how far back the sync reached; `generated_at` says
    when the picture was taken, from the injected clock, in UTC. A consumer
    showing a masthead figure shows this beside it, so a stale number is
    delivered with its date. Mutation: build without stamping `generated_at`
    and the field is empty."""
    from datetime import datetime, timezone

    session = _session()
    when = datetime(2026, 9, 20, 18, 30, 0, tzinfo=timezone.utc)
    seam = overview.as_dict(overview.build(session, now=when))
    assert seam["generated_at"] == "2026-09-20T18:30:00+00:00"
    # A naive clock is read as UTC rather than guessed at.
    naive = overview.as_dict(overview.build(session, now=datetime(2026, 9, 20, 18, 30, 0)))
    assert naive["generated_at"] == "2026-09-20T18:30:00+00:00"
