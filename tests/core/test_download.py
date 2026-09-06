"""One writer for "fetch a GitHub repository and store it", and what it fixed.

**THERE WERE THREE, AND TWO OF THEM WERE WRONG.** The command line's was
complete. The panel's single-project sync read four keys the client does not
emit, and SQLModel drops unrecognised keyword arguments silently, so every
branch landed with no commit date and every pull request with no timestamps.
The panel's *batch* sync fetched seven related tables per repository, discarded
all seven, and then called `.get()` on a dataclass — an `AttributeError` its
own `except Exception` swallowed, so `s` and the ring's sync reported "Failed to
sync" for every project in every batch.

None of that is visible from inside any one of the three. The tests below are
what a list makes possible.

**NO TEST HERE REACHES GITHUB.** The client and the parser are both passed in,
so what is under test is which column takes which key and what the batch does
when one repository fails — not whether the network is up.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from dossier import download as module
from dossier.models import utcnow
from dossier.models.schemas import (
    Project,
    ProjectBranch,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
)


# --- the doubles --------------------------------------------------------------


class FakeRepo:
    """What `list_user_repos` returns, with the fields `absorb` reads."""

    def __init__(self, owner="qm", name="dossier", language="Python",
                 is_fork=False):
        self.owner, self.name = owner, name
        self.description = f"{name} description"
        self.html_url = f"https://github.com/{owner}/{name}"
        self.language = language
        self.stars = 7
        self.is_fork = is_fork
        self.is_archived = False

    @property
    def full_name(self):
        return f"{self.owner}/{self.name}"


class FakeParser:
    """Returns no document sections, and records what it was asked for."""

    def __init__(self, raises=None):
        self.asked = []
        self._raises = raises

    def parse_repo(self, owner, name, include_docs_folder=True):
        self.asked.append((owner, name, include_docs_folder))
        if self._raises and f"{owner}/{name}" in self._raises:
            raise RuntimeError(self._raises[f"{owner}/{name}"])
        return FakeRepo(owner, name), []


class FakeRateLimit:
    def __init__(self, remaining=5000):
        self.remaining = remaining
        self.seconds_until_reset = 30


class FakeClient:
    """Answers every getter with one row carrying the keys it really emits."""

    def __init__(self, account_type="User", repos=None, remaining=5000):
        self._type = account_type
        self._repos = repos if repos is not None else [FakeRepo()]
        self.rate_limit = FakeRateLimit(remaining)
        self.listed = []

    def get(self, url, **kwargs):
        class Response:
            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        return Response({"type": self._type, "login": url.rsplit("/", 1)[-1]})

    def list_user_repos(self, login, **kwargs):
        self.listed.append(("user", login))
        return list(self._repos)

    def list_org_repos(self, login, **kwargs):
        self.listed.append(("org", login))
        return list(self._repos)

    def get_languages(self, owner, name):
        return [{"language": "Python", "bytes_count": 10, "percentage": 100.0,
                 "file_extensions": ".py", "encoding": "utf-8"}]

    def get_dependencies(self, owner, name):
        return [{"name": "httpx", "version_spec": ">=0.27",
                 "dep_type": "runtime", "source": "pyproject.toml"}]

    def get_contributors(self, owner, name, **kwargs):
        return [{"username": "someone", "contributions": 3}]

    def get_issues(self, owner, name, **kwargs):
        return [{"issue_number": 1, "title": "an issue", "state": "open",
                 "author": "someone", "labels": "bug",
                 "issue_created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                 "issue_updated_at": datetime(2026, 1, 3, tzinfo=timezone.utc)}]

    def get_branches(self, owner, name, **kwargs):
        return [{"name": "main", "is_default": True, "is_protected": True,
                 "commit_sha": "abc123", "commit_message": "a commit",
                 "commit_author": "someone",
                 "commit_date": datetime(2026, 2, 3, tzinfo=timezone.utc)}]

    def get_pull_requests(self, owner, name, **kwargs):
        return [{"pr_number": 9, "title": "a pull request", "state": "closed",
                 "author": "someone", "base_branch": "main",
                 "head_branch": "work", "is_merged": True,
                 "pr_created_at": datetime(2026, 3, 4, tzinfo=timezone.utc),
                 "pr_updated_at": datetime(2026, 3, 5, tzinfo=timezone.utc),
                 "pr_merged_at": datetime(2026, 3, 6, tzinfo=timezone.utc)}]

    def get_releases(self, owner, name, **kwargs):
        return [{"tag_name": "v1", "name": "one", "body": "notes"}]


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as made:
        yield made


# --- who an owner is ----------------------------------------------------------


def test_an_organisation_is_listed_from_the_organisation_endpoint():
    """THE ONE THIS EXISTS FOR, on this half.

    `/users/x/repos` returns an empty list for an organisation rather than
    failing, so guessing wrong reads as "that org has no repositories".

    Mutation: always call `list_user_repos` and this fails.
    """
    client = FakeClient(account_type="Organization")
    found = module.look_up(client, "quaternionmedia")

    assert found.kind == module.ORGANIZATION and found.is_organization
    assert client.listed == [("org", "quaternionmedia")]


def test_a_person_is_listed_from_the_user_endpoint():
    client = FakeClient(account_type="User")
    found = module.look_up(client, "octocat")

    assert found.kind == module.USER
    assert client.listed == [("user", "octocat")]


def test_a_pasted_profile_url_is_a_login_somebody_had_in_their_hand():
    """The failure mode this avoids is a field that looks right and resolves to
    nothing.

    Mutation: drop the URL handling and this fails.
    """
    client = FakeClient()
    assert module.look_up(client, "https://github.com/octocat/").login == "octocat"
    assert module.look_up(client, " octocat ").login == "octocat"


def test_an_empty_owner_is_refused_rather_than_looked_up():
    with pytest.raises(ValueError):
        module.look_up(FakeClient(), "   ")


# --- what it would do, before it does it --------------------------------------


def test_the_inventory_separates_what_is_new_from_what_is_held(session):
    """**LIST FIRST, ACT SECOND**, the pattern `clone.py` already uses. Tens of
    repositories and hundreds of API calls is something a person reads before
    it happens.

    Mutation: return every repository as new and this fails.
    """
    session.add(Project(name="qm/dossier", full_name="qm/dossier"))
    session.commit()

    client = FakeClient(repos=[FakeRepo(name="dossier"), FakeRepo(name="qmcp")])
    found = module.inventory(session, client, "qm")

    assert [r.name for r in found.new] == ["qmcp"]
    assert [r.name for r in found.already] == ["dossier"]
    assert "1 new" in found.summary() and "1 already held" in found.summary()


def test_an_owner_with_nothing_says_so_rather_than_reporting_a_count(session):
    found = module.inventory(session, FakeClient(repos=[]), "empty")
    assert "no repositories" in found.summary()


def test_skipping_forks_reads_the_fork_flag_not_the_name():
    """**THE COMMAND LINE TESTED THE NAME.** `--skip-forks` filtered on
    `r.name.endswith("-fork")`, which is not what a fork is and matched almost
    nothing on GitHub.

    Mutation: filter on the name again and this fails.
    """
    repos = [FakeRepo(name="real"), FakeRepo(name="borrowed", is_fork=True)]
    assert [r.name for r in module.narrow(repos, skip_forks=True)] == ["real"]


def test_the_filters_compose_in_the_order_the_command_line_offered_them():
    repos = [FakeRepo(name="a", language="Python"),
             FakeRepo(name="b", language="Rust"),
             FakeRepo(name="c", language="python")]
    assert [r.name for r in module.narrow(repos, language="Python")] == ["a", "c"]
    assert [r.name for r in module.narrow(repos, limit=2)] == ["a", "b"]


# --- the one writer -----------------------------------------------------------


def test_a_branch_keeps_its_commit_date(session):
    """**THE PANEL WROTE NULL HERE, SILENTLY, FOR AS LONG AS IT EXISTED.** It
    read `branch["committed_at"]`; the client emits `commit_date`. SQLModel
    drops keyword arguments it does not recognise, so nothing failed and the
    column was simply empty.

    Mutation: read `committed_at` in `_absorb_extended` and this fails.
    """
    module.absorb(session, FakeParser(), FakeClient(), FakeRepo())
    session.commit()

    branch = session.exec(select(ProjectBranch)).first()
    assert branch.commit_date is not None, "the branch landed with no commit date"
    assert branch.commit_sha == "abc123"


def test_a_pull_request_keeps_its_own_timestamps(session):
    """Same failure, three more columns: the panel read `created_at`,
    `merged_at` and `closed_at`; the client emits `pr_created_at`,
    `pr_updated_at` and `pr_merged_at`.

    `created_at` is the worse half — it exists on the model as the *row's* own
    timestamp, so reading it there was not even a no-op.

    Mutation: read the panel's names and this fails.
    """
    module.absorb(session, FakeParser(), FakeClient(), FakeRepo())
    session.commit()

    pull = session.exec(select(ProjectPullRequest)).first()
    assert pull.pr_created_at is not None
    assert pull.pr_merged_at is not None


def test_an_issue_keeps_the_dates_no_writer_ever_stored(session):
    """The client has emitted these since it learned to page and all three
    writers dropped them.

    Mutation: stop passing them and this fails.
    """
    module.absorb(session, FakeParser(), FakeClient(), FakeRepo())
    session.commit()

    issue = session.exec(select(ProjectIssue)).first()
    assert issue.issue_created_at is not None


def test_refreshing_replaces_rather_than_appends(session):
    """Twice through is one set of rows, not two. A refresh that appended would
    double every table on every sync.

    Mutation: drop `_replace` and this fails.
    """
    for _ in range(2):
        module.absorb(session, FakeParser(), FakeClient(), FakeRepo())
        session.commit()

    assert len(session.exec(select(Project)).all()) == 1
    assert len(session.exec(select(ProjectLanguage)).all()) == 1
    assert len(session.exec(select(ProjectBranch)).all()) == 1


def test_the_project_row_survives_a_refusal_to_read_the_related_tables(session):
    """An owner whose token cannot read issues can still have their branches
    stored, and a partial refresh is worth more than a refusal.

    Mutation: let `_absorb_extended` raise and this fails.
    """
    class Refuses(FakeClient):
        def get_issues(self, owner, name, **kwargs):
            raise RuntimeError("403 Forbidden")

    module.absorb(session, FakeParser(), Refuses(), FakeRepo())
    session.commit()

    assert session.exec(select(Project)).first().name == "qm/dossier"


def test_not_asking_for_the_related_tables_does_not_spend_the_calls(session):
    """**THE PANEL'S BATCH SYNC SPENT THEM AND THREW THE ROWS AWAY**, which is
    the worst of both.

    Mutation: ignore `extended` and this fails.
    """
    class Counts(FakeClient):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def get_languages(self, owner, name):
            self.calls += 1
            return []

    client = Counts()
    module.absorb(session, FakeParser(), client, FakeRepo(), extended=False)
    session.commit()

    assert client.calls == 0
    assert session.exec(select(Project)).first() is not None


# --- the batch ----------------------------------------------------------------


def test_every_repository_is_reported_as_it_lands(session):
    """`on_each` is how this is rendered. A shared engine that printed would be
    one only the command line could use.

    Mutation: report only at the end and this fails on the running counts.
    """
    repos = [FakeRepo(name=n) for n in ("a", "b", "c")]
    seen = []
    report = module.download(session, FakeParser(), FakeClient(), repos,
                             on_each=seen.append, delay_between_batches=0)

    assert [f.repo for f in seen] == ["qm/a", "qm/b", "qm/c"]
    assert [f.index for f in seen] == [1, 2, 3]
    assert all(f.total == 3 for f in seen)
    assert report.fetched == 3 and not report.rate_limited


def test_one_repository_failing_does_not_stop_the_others(session):
    """Mutation: let the exception out of the loop and this fails.
    """
    parser = FakeParser(raises={"qm/b": "404 Not Found"})
    repos = [FakeRepo(name=n) for n in ("a", "b", "c")]
    report = module.download(session, parser, FakeClient(), repos,
                             delay_between_batches=0)

    assert report.fetched == 2 and report.failed == 1
    failed = [o for o in report.outcomes if o.outcome == module.FAILED]
    assert "404" in failed[0].detail, "the API's words were not carried through"


def test_a_rate_limit_stops_the_run_and_keeps_what_landed(session):
    """**THAT IS WHAT MAKES "RUN IT AGAIN TO CONTINUE" TRUE** rather than a
    hope. It commits per repository, so the ones already fetched are in the
    database when it stops.

    Mutation: commit once at the end and this fails.
    """
    parser = FakeParser(raises={"qm/b": "API rate limit exceeded"})
    repos = [FakeRepo(name=n) for n in ("a", "b", "c")]
    report = module.download(session, parser, FakeClient(), repos,
                             delay_between_batches=0)

    assert report.rate_limited
    assert report.fetched == 1, "it kept going past the limit"
    assert session.exec(select(Project)).first().name == "qm/a"
    assert "running it again continues" in report.summary()


def test_a_repository_synced_within_the_hour_is_passed_over(session):
    """Mutation: drop the recency check and this fails."""
    session.add(Project(name="qm/dossier", full_name="qm/dossier",
                        last_synced_at=utcnow()))
    session.commit()

    report = module.download(session, FakeParser(), FakeClient(), [FakeRepo()],
                             delay_between_batches=0)
    assert report.skipped == 1 and report.fetched == 0


def test_force_fetches_what_recency_would_have_passed_over(session):
    session.add(Project(name="qm/dossier", full_name="qm/dossier",
                        last_synced_at=utcnow()))
    session.commit()

    report = module.download(session, FakeParser(), FakeClient(), [FakeRepo()],
                             force=True, delay_between_batches=0)
    assert report.fetched == 1


def test_a_naive_timestamp_out_of_sqlite_does_not_read_as_a_failure(session):
    """**IT WOULD HAVE.** SQLite hands back timezone-naive datetimes, and
    comparing one to an aware `utcnow()` raises — inside a per-repository
    `try`, that reads as the repository failing to fetch.

    Mutation: compare without normalising and this fails.
    """
    naive = (utcnow() - timedelta(minutes=5)).replace(tzinfo=None)
    session.add(Project(name="qm/dossier", full_name="qm/dossier",
                        last_synced_at=naive))
    session.commit()

    report = module.download(session, FakeParser(), FakeClient(), [FakeRepo()],
                             delay_between_batches=0)
    assert report.skipped == 1, report.outcomes


def test_a_thin_rate_limit_waits_between_batches_rather_than_spending_it(session):
    """Mutation: drop the floor check and nothing waits."""
    slept = []
    repos = [FakeRepo(name=n) for n in ("a", "b", "c", "d")]
    module.download(session, FakeParser(), FakeClient(remaining=1), repos,
                    batch_size=2, sleep=slept.append)

    assert slept and slept[0] == 30, slept


def test_downloading_an_owner_returns_what_it_set_out_to_do_and_what_it_did(session):
    """Recomputing the inventory afterwards would list what is *now* held
    rather than what was, and the two readings are shown together.

    Mutation: return the report alone and the caller cannot say how many were
    new.
    """
    client = FakeClient(repos=[FakeRepo(name="a"), FakeRepo(name="b")])
    done = module.onboard(session, FakeParser(), client, "qm",
                          delay_between_batches=0)

    assert len(done.inventory.new) == 2 and done.report.fetched == 2
    assert done.inventory.owner.login == "qm"


def test_a_filter_narrows_what_the_owner_download_fetches(session):
    client = FakeClient(repos=[FakeRepo(name="a"),
                              FakeRepo(name="b", is_fork=True)])
    done = module.onboard(session, FakeParser(), client, "qm",
                          skip_forks=True, delay_between_batches=0)

    assert len(done.inventory.repos) == 2, (
        "the inventory reports what the owner has")
    assert done.report.fetched == 1, "the fetch is what was narrowed"
