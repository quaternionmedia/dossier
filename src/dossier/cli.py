"""Click CLI for Dossier."""

import os
import sys
import textwrap
from pathlib import Path
from typing import Optional

import click
from sqlmodel import Session, SQLModel, create_engine, select

from dossier.models import (
    DocumentationLevel,
    DocumentSection,
    Project,
    ProjectBranch,
    ProjectComponent,
    ProjectContributor,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
)


# Database setup
# Where the database is, and the one way to point this somewhere else.
#
# `sqlite:///dossier.db` is relative to the working directory, so which database
# you get depends on where you launched from -- `dossier/health.py` records the
# failure that came out of exactly that. Until this override existed there was
# no other way to redirect it, so anything that wanted a scratch database had to
# change directory, and anything that forgot wrote into whichever `dossier.db`
# was underfoot. A demo, an experiment or a walkthrough run in the repository
# root wrote into the operator's own data, which is how this was found.
#
# `qmcp dashboard --database` is the same affordance on the other side of the
# seam, and it existed first.
def _database_url() -> str:
    """The database URL, with `~` resolved.

    No shell expands a tilde in the middle of a string, so
    `sqlite:///~/hil/panel.db` arrives here literally. Passed through, it makes
    a directory actually named `~` and reports success -- and `.gitignore`
    carries `*~`, so it does not appear in `git status` either.
    """
    from pathlib import Path as _Path

    url = os.environ.get("DOSSIER_DATABASE_URL")
    if not url:
        return "sqlite:///dossier.db"
    prefix = "sqlite:///"
    if url.startswith(prefix) and "~" in url:
        return prefix + _Path(url[len(prefix):]).expanduser().as_posix()
    return url


DATABASE_URL = _database_url()
engine = create_engine(DATABASE_URL, echo=False)


def _alembic_config():
    """An alembic config that does not rebind logging on every use.

    `fileConfig` attaches a handler to whatever `sys.stderr` is when it runs,
    so a process that invokes alembic twice writes the second run's output to a
    stream the first caller has closed. The database commands are fine alone
    and failed when another command had run first, which is the hardest kind of
    failure to read. It also resolves `alembic.ini` from the package, so these
    commands work from any directory.
    """
    from alembic.config import Config

    from dossier.health import project_root

    # `stdout` is passed explicitly. Alembic's `Config.__init__` declares
    # `stdout=sys.stdout` as a *default argument*, which Python evaluates once
    # when `alembic.config` is first imported -- binding whatever `sys.stdout`
    # was at that moment. Any later run then writes its output to that stream,
    # and if the first import happened inside something that has since replaced
    # or closed stdout, alembic fails with "I/O operation on closed file" for a
    # command that is otherwise fine.
    config = Config(str(project_root() / "alembic.ini"), stdout=sys.stdout)
    config.set_main_option("script_location", str(project_root() / "alembic"))

    # The database this process is actually using, not the one `alembic.ini`
    # names. Without this the migration commands read `sqlalchemy.url` from the
    # ini file -- `sqlite:///dossier.db`, relative to the working directory --
    # so `db upgrade` migrated whichever database was underfoot while every
    # query ran against the one the caller asked for, and reported success.
    #
    # That is the two-databases failure `dossier/health.py` exists for, and it
    # survived two earlier repairs: the engine learned about the override, then
    # `health.candidate_databases` did, and this third path did not. Three
    # resolvers, one answer.
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

    config.attributes["configure_logger"] = False
    return config


def init_db() -> None:
    """Make sure this installation has a database the code can read.

    It does NOT call `create_all`. That is what produced every schema failure
    reported against this project: `create_all` builds tables with no alembic
    stamp, so the first command a fresh installation ran left a database
    alembic had no record of -- and once it held data, no stamp could be
    inferred and it could not be migrated at all. The schema comes from the
    migrations, which stamp as they go.
    """
    from dossier.health import ensure_schema

    ensure_schema()


def get_session() -> Session:
    """Get database session."""
    return Session(engine)


def _make_output_encodable() -> None:
    """Stop a glyph in a progress message aborting the command that printed it.

    A Windows console is cp1252 by default, and this CLI prints emoji. The
    failure mode is the bad one: `sync-org` raised UnicodeEncodeError on its
    first status line, and `projects remove` raised on the line it printed
    *after* committing the deletion -- so the command reported a crash for work
    that had already happened. Setting the stream encoding once at the entry
    point fixes every message, including ones not written yet; replacing the
    glyphs one at a time fixes only the ones somebody remembered.
    """
    for stream in (sys.stdout, sys.stderr):
        # Only a stream that would actually fail is touched. Under pytest and
        # under click's CliRunner, stdout is already a UTF-8 capture buffer;
        # reconfiguring one of those detached it, and a later command in the
        # same process wrote to a closed file. The symptom was a test failing
        # only when another test had run first, which is the hardest kind to
        # read.
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if getattr(stream, "closed", False) or encoding.startswith("utf"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # A stream that will not be reconfigured (a pipe under some
                # runners) is left as it is: `errors` cannot be set on it
                # either, so there is nothing further to try.
                pass


class DossierGroup(click.Group):
    """The command group, with one exception turned into an instruction.

    Caught here rather than in the sync commands because the limit can be
    reached by any command that talks to GitHub, and a fix applied only where
    the failure was first seen leaves the same traceback waiting behind every
    other route. This is the whole class, in one place.
    """

    # **THE COMMAND EXPLORER IS LOADED WHEN IT IS ASKED FOR.** `@tui()` from
    # trogon decorates the group, so importing this module imported trogon --
    # 0.21s of a 0.86s import, on every invocation, for a command almost nobody
    # runs. Registering it here instead means `dossier tui` still exists and
    # still appears in `--help`, and nothing else pays for it.
    #
    # A stated requirement is running on very underpowered hardware, where
    # import time is the whole of what "start" means.
    _EXPLORER = "tui"

    def _explorer(self) -> click.Command | None:
        from trogon import tui as _trogon_tui

        holder = click.Group(name="_holder")
        _trogon_tui()(holder)
        return holder.commands.get(self._EXPLORER)

    def get_command(self, ctx, name):
        if name == self._EXPLORER and name not in self.commands:
            found = self._explorer()
            if found is not None:
                self.add_command(found, self._EXPLORER)
        return super().get_command(ctx, name)

    def list_commands(self, ctx):
        # Named without importing, so `--help` lists it and costs nothing.
        listed = set(super().list_commands(ctx)) | {self._EXPLORER}
        return sorted(listed)

    def invoke(self, ctx):
        from dossier.ratelimit import advice, is_rate_limit

        try:
            return super().invoke(ctx)
        except SystemExit:
            raise
        except Exception as error:
            if is_rate_limit(error):
                click.echo(advice(error), err=True)
                raise SystemExit(2) from None
            raise


@click.group(cls=DossierGroup)
@click.version_option(version="0.1.0", prog_name="dossier")
def cli() -> None:
    """Dossier - Documentation standardization tool.
    
    Auto-parse project documentation and query at different detail levels.
    
    Quick start:
        dossier dashboard         Launch interactive TUI dashboard
        dossier tui               Launch command explorer (Trogon)
        dossier projects list     List all projects
        dossier github sync URL   Sync a GitHub repo
    """
    _make_output_encodable()
    init_db()


@cli.command()
def dashboard() -> None:
    """Launch the interactive TUI dashboard.
    
    Full-featured terminal UI for project tracking with:
    - Project list with search
    - Real-time sync status
    - Documentation browser
    - Component tree view
    
    Keyboard shortcuts:
        q - Quit
        r - Refresh
        s - Sync selected project
        a - Add project
        d - Delete project
        / - Search
        ? - Help
    """
    from dossier.health import BLOCKED, prepare, render, summary_line, worst
    from dossier.tui import DossierApp

    # The dashboard is the only command a fresh clone needs after `uv sync`.
    # `prepare` is the whole of init: it creates a database that does not
    # exist, applies migrations that have not run, and corrects a stamp that
    # claims they did. It runs every launch rather than behind a first-run
    # flag, because the state it repairs arrives from outside -- pulling a
    # branch with a new migration is the ordinary way to get it.
    actions, findings = prepare()
    for action in actions:
        click.echo(f"  {action}")

    if worst(findings) == BLOCKED:
        # Refusing is the point: the app would open and then fail on the first
        # query naming a missing column, in the middle of a screen, with a
        # driver error that says nothing about what to do next.
        click.echo(render(findings), err=True)
        raise SystemExit(1)

    click.echo(summary_line(findings))
    app = DossierApp()
    app.run()


# =============================================================================
# Projects Commands - Manage registered projects
# =============================================================================


@cli.group()
def deltas() -> None:
    """Deltas: units of work, including ones another system emitted."""
    pass


def _store_links(session, delta, links: list[dict]) -> None:
    """Write a payload's links, without writing one twice.

    Re-ingesting the same payload is ordinary -- a harness emits its state on
    every run -- so a link is matched on what identifies it rather than
    appended. `(delta, link_type, target_name)` is that identity: two links of
    the same type at the same target are one link, however many runs mentioned
    it.
    """
    from sqlmodel import select

    from dossier.models.schemas import DeltaLink

    for link in links:
        link_type = link.get("link_type")
        target_name = link.get("target_name")
        if not link_type:
            continue
        existing = session.exec(
            select(DeltaLink)
            .where(DeltaLink.delta_id == delta.id)
            .where(DeltaLink.link_type == str(link_type))
            .where(DeltaLink.target_name == (
                None if target_name is None else str(target_name)))
        ).first()
        if existing is not None:
            continue
        session.add(DeltaLink(
            delta_id=delta.id,
            link_type=str(link_type),
            target_id=link.get("target_id"),
            target_name=None if target_name is None else str(target_name),
        ))


@deltas.command("relate")
@click.argument("source")
@click.argument("relation")
@click.argument("target")
@click.option("--by", default=None, help="who is stating this")
@click.option("--proposed", is_flag=True,
              help="a detector suggests it; proposing is not asserting")
@click.option("--note", default=None)
def deltas_relate(source: str, relation: str, target: str, by: str | None,
                  proposed: bool, note: str | None) -> None:
    """State that two deltas compose.

    SOURCE and TARGET are addresses -- `<owner>/<repo>/delta/<id>` -- so a
    relation crosses repositories and threads. Either may name a delta this
    database has not ingested; an address denotes without existing.

    \b
    part-of       closing the whole requires closing this
    same-as       two addresses denote one strand
    blocks        this must close before that can start
    crosses       both must happen, they interact at one point, and neither
                  contains the other
    derived-from  this strand came out of that one and both continue

    `crosses` is not a weak `blocks`. A block orders whole strands; a crossing
    orders them at one place and leaves the rest independent. Recording a
    crossing as a block is how a board comes to say nothing can start.
    """
    from sqlmodel import select

    from dossier.composition import RELATIONS, check_address, check_relation
    from dossier.models.harness import DeltaRelation

    for problem in (check_relation(relation), check_address(source),
                    check_address(target)):
        if problem:
            raise SystemExit(problem)
    if source == target and relation not in ("same-as", "crosses"):
        raise SystemExit(
            f"a delta cannot be {relation!r} itself. Only the symmetric "
            f"relations are meaningful reflexively, and even those say nothing."
        )

    with get_session() as session:
        existing = session.exec(
            select(DeltaRelation)
            .where(DeltaRelation.source_address == source)
            .where(DeltaRelation.relation == relation)
            .where(DeltaRelation.target_address == target)
        ).first()
        if existing is not None:
            click.echo(f"  [=] already stated"
                       + (f" by {existing.stated_by}" if existing.stated_by else ""))
            return
        session.add(DeltaRelation(
            source_address=source, relation=relation, target_address=target,
            stated_by=by, proposed=proposed, note=note))
        session.commit()

    click.echo(f"  [+] {source}")
    click.echo(f"      {relation}  ({RELATIONS[relation]})")
    click.echo(f"      {target}")
    if proposed:
        click.echo("      Proposed, not asserted. A detector suggested it.")


@deltas.command("search")
@click.argument("text")
def deltas_search(text: str) -> None:
    """Find deltas by name, title or branch, across every repository.

    **EVERY OTHER WAY OF FINDING ONE STARTS BY CHOOSING A REPOSITORY**, and a
    compound crosses them by construction -- a relation joins two addresses,
    and an address carries its own owner.
    """
    from sqlmodel import select

    from dossier.compound import search
    from dossier.models.schemas import Project, ProjectDelta

    with get_session() as session:
        rows = session.exec(select(ProjectDelta)).all()
        found = search(rows, text)
        names = {p.id: (p.full_name or p.name)
                 for p in session.exec(select(Project)).all()}
        listed = [
            (f"{names.get(row.project_id, '?')}/delta/{row.id}",
             row.title or row.name or "",
             getattr(row.phase, "value", str(row.phase)))
            for row in found
        ]

    if not listed:
        click.echo(f"No delta matches {text!r}.")
        return
    click.echo(f"{len(listed)} delta(s) match {text!r}:")
    for address, title, phase in listed:
        click.echo(f"  {address:<40} {phase:<16} {title[:44]}")


@deltas.command("compound")
@click.argument("address")
def deltas_compound(address: str) -> None:
    """Every delta that moves together with ADDRESS, and whether each can.

    Walks `part-of` -- closing the whole requires closing this -- and
    `same-as`, which denotes one strand under two addresses. It does not walk
    `blocks`: "this must close first" is not "these close together", and that
    is the distinction the relation vocabulary exists to make possible.

    Reads and prints. Nothing is advanced.
    """
    from sqlmodel import select

    from dossier.compound import can_advance, compound_of, edges_from
    from dossier.models.harness import DeltaRelation
    from dossier.models.schemas import Project, ProjectDelta

    with get_session() as session:
        edges = edges_from(session.exec(select(DeltaRelation)).all())
        names = {p.id: (p.full_name or p.name)
                 for p in session.exec(select(Project)).all()}
        rows = []
        for row in session.exec(select(ProjectDelta)).all():
            row.address = f"{names.get(row.project_id, '?')}/delta/{row.id}"
            rows.append(row)
        found = compound_of(address, edges, rows)

    if found.is_alone:
        click.echo(f"{address} is the whole of it -- nothing else is stated to "
                   f"move with it.")
        return

    click.echo(f"{found.size} delta(s) move with {address}:")
    for one in found.members:
        why = can_advance(one)
        mark = f"   ({why})" if why else ""
        click.echo(f"  {one.address:<40} {one.because:<10} "
                   f"{one.phase or '--':<14}{mark}")

    if found.truncated:
        click.echo("")
        click.echo("The walk stopped at its depth limit, so this may be part "
                   "of something larger. It is not a complete answer.")


@deltas.command("tangles")
def deltas_tangles() -> None:
    """Every cycle the relations form. Reports, and changes nothing.

    Other trackers refuse a cycle as invalid input. What happens then is that
    somebody deletes whichever relation the tool complained about, so the tool
    is consistent and the record is false. A tangle is a fact about the work.
    """
    from sqlmodel import select

    from dossier.composition import Edge, render_tangles, tangles
    from dossier.models.harness import DeltaRelation

    with get_session() as session:
        edges = [
            Edge(row.source_address, row.relation, row.target_address,
                 row.stated_by)
            for row in session.exec(select(DeltaRelation)).all()
        ]
    click.echo(render_tangles(tangles(edges)))


@deltas.command("compose")
@click.argument("address")
def deltas_compose(address: str) -> None:
    """What one delta is made of, and what else is the same strand."""
    from sqlmodel import select

    from dossier.composition import Edge, check_address, parts_of, strands
    from dossier.models.harness import DeltaRelation

    problem = check_address(address)
    if problem:
        raise SystemExit(problem)

    with get_session() as session:
        edges = [
            Edge(row.source_address, row.relation, row.target_address,
                 row.stated_by)
            for row in session.exec(select(DeltaRelation)).all()
        ]

    click.echo(f"  {address}")
    parts, truncated = parts_of(address, edges)
    if parts:
        click.echo("")
        click.echo("  made of")
        for part in parts:
            click.echo(f"    {part}")
        if truncated:
            click.echo("    ... and deeper. This walk stopped at its bound "
                       "rather than running on: the relations are allowed to "
                       "contain a cycle, so an unbounded walk is a hang.")
    else:
        click.echo("  Nothing states it is made of anything.")

    same = strands(address, edges)
    if same:
        click.echo("")
        click.echo("  the same strand as")
        for other in same:
            click.echo(f"    {other}")
        click.echo("    Both names are kept. Neither is retired, because "
                   "documents already cite each of them.")


@deltas.command("ingest")
@click.argument("payload", type=click.Path(exists=True, path_type=Path))
@click.option("--write", is_flag=True,
              help="apply the plan; without it nothing is written")
def deltas_ingest(payload: Path, write: bool) -> None:
    """Ingest delta payloads another system emitted.

    What crosses is a schema, not an import: the payload's `delta` key holds
    this project's own column names. Reports by default -- a sync that wrote on
    sight is one nobody dares run against real data.
    """
    from sqlmodel import select

    from dossier.ingest import WRITABLE, load, plan, render
    from dossier.models import Project, ProjectDelta

    payloads = load(payload)
    init_db()
    with get_session() as session:
        def lookup_project(full_name: str):
            return session.exec(
                select(Project).where(Project.full_name == full_name)
            ).first() or session.exec(
                select(Project).where(Project.name == full_name)
            ).first()

        def lookup_delta(project_id: int, name: str):
            return session.exec(
                select(ProjectDelta)
                .where(ProjectDelta.project_id == project_id)
                .where(ProjectDelta.name == name)
            ).first()

        verdicts = plan(payloads, lookup_project, lookup_delta)

        if write:
            by_name = {v.name: v for v in verdicts}
            for item in payloads:
                row = item.get("delta") or {}
                verdict = by_name.get(str(row.get("name") or ""))
                # `unchanged` reaches the link pass too. A delta whose own
                # fields are identical can still have gained a link -- a second
                # run of the same failing check produces the same delta and a
                # new invocation -- and skipping it would drop exactly the rows
                # that accumulate.
                if verdict is None or verdict.action == "refused":
                    continue
                project = lookup_project(item["project"])
                fields = {k: row[k] for k in WRITABLE if k in row}
                if verdict.action == "create":
                    delta = ProjectDelta(project_id=project.id, **fields)
                    session.add(delta)
                else:
                    delta = lookup_delta(project.id, fields["name"])
                    if verdict.action == "update":
                        for key, value in fields.items():
                            setattr(delta, key, value)
                        session.add(delta)

                # `links` used to be read for the address and then dropped, so
                # the row that names what a delta points at -- the invocation
                # that found it, and the address that joins it to the other
                # view -- was never stored. Both sides believed the join
                # existed and nothing held it.
                session.flush()   # the delta needs its id before a link can cite it
                _store_links(session, delta, item.get("links") or [])
            session.commit()

        click.echo(render(verdicts, write))


@cli.group()
def projects() -> None:
    """Manage registered projects.
    
    Commands for listing, adding, removing, and inspecting projects.
    """
    pass


@projects.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.option("--synced", is_flag=True, help="Show only GitHub-synced projects")
def projects_list(verbose: bool, synced: bool) -> None:
    """List all registered projects."""
    with get_session() as session:
        stmt = select(Project)
        projects = session.exec(stmt).all()
        
        if synced:
            projects = [p for p in projects if p.last_synced_at]
        
        if not projects:
            click.echo("No projects registered.")
            return
        
        click.echo("\n📁 Registered Projects:")
        click.echo("=" * 50)
        
        for project in sorted(projects, key=lambda p: p.name):
            # Count docs for this project
            doc_count = len(session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            ).all())
            
            # Project name with badges
            badges = []
            if project.github_stars:
                badges.append(f"⭐{project.github_stars}")
            if doc_count:
                badges.append(f"📄{doc_count}")
            
            badge_str = f" [{' '.join(badges)}]" if badges else ""
            click.echo(f"\n  {project.name}{badge_str}")
            
            if verbose or project.description:
                if project.description:
                    desc = project.description[:60] + "..." if len(project.description) > 60 else project.description
                    click.echo(f"    {desc}")
            
            if verbose:
                if project.repository_url:
                    click.echo(f"    URL: {project.repository_url}")
                if project.documentation_path:
                    click.echo(f"    Docs: {project.documentation_path}")
                if project.last_synced_at:
                    click.echo(f"    Synced: {project.last_synced_at.strftime('%Y-%m-%d %H:%M')}")
        
        click.echo(f"\nTotal: {len(projects)} projects")


@projects.command("add")
@click.argument("name")
@click.option("--description", "-d", help="Project description")
@click.option("--repo-url", "-r", help="Repository URL")
@click.option("--docs-path", "-p", help="Path to documentation files")
def projects_add(
    name: str,
    description: Optional[str],
    repo_url: Optional[str],
    docs_path: Optional[str],
) -> None:
    """Add a new project.
    
    NAME: Unique name for the project
    """
    with get_session() as session:
        existing = session.exec(
            select(Project).where(Project.name == name)
        ).first()
        if existing:
            click.echo(f"Error: Project '{name}' already exists.", err=True)
            raise SystemExit(1)
        
        project = Project(
            name=name,
            description=description,
            repository_url=repo_url,
            documentation_path=docs_path,
        )
        session.add(project)
        session.commit()
        click.echo(f"OK Added project: {name}")


@projects.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--keep-docs", is_flag=True, help="Keep associated documentation")
def projects_remove(name: str, yes: bool, keep_docs: bool) -> None:
    """Remove a project.
    
    NAME: Name of the project to remove
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{name}' not found.", err=True)
            raise SystemExit(1)
        
        # Count docs
        doc_count = len(session.exec(
            select(DocumentSection).where(DocumentSection.project_id == project.id)
        ).all())
        
        if not yes:
            msg = f"Remove project '{name}'"
            if doc_count and not keep_docs:
                msg += f" and {doc_count} documentation sections"
            msg += "?"
            click.confirm(msg, abort=True)
        
        # Remove docs unless keeping
        if not keep_docs:
            docs = session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            ).all()
            for doc in docs:
                session.delete(doc)
        
        # Remove component relationships
        components = session.exec(
            select(ProjectComponent).where(
                (ProjectComponent.parent_id == project.id) | 
                (ProjectComponent.child_id == project.id)
            )
        ).all()
        for comp in components:
            session.delete(comp)
        
        session.delete(project)
        session.commit()
        
        click.echo(f"OK Removed project: {name}")
        if doc_count and not keep_docs:
            click.echo(f"  Deleted {doc_count} documentation sections")


@projects.command("show")
@click.argument("name")
def projects_show(name: str) -> None:
    """Show detailed information about a project.
    
    NAME: Name of the project to inspect
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{name}' not found.", err=True)
            raise SystemExit(1)
        
        # Count docs by level
        docs = session.exec(
            select(DocumentSection).where(DocumentSection.project_id == project.id)
        ).all()
        
        level_counts = {}
        for doc in docs:
            level_counts[doc.level.value] = level_counts.get(doc.level.value, 0) + 1
        
        # Get components
        child_components = session.exec(
            select(ProjectComponent).where(ProjectComponent.parent_id == project.id)
        ).all()
        parent_components = session.exec(
            select(ProjectComponent).where(ProjectComponent.child_id == project.id)
        ).all()
        
        click.echo(f"\n{'=' * 50}")
        click.echo(f"  {project.name}")
        click.echo(f"{'=' * 50}")
        
        if project.description:
            click.echo(f"\n{project.description}")
        
        click.echo("\n📋 Details:")
        click.echo(f"  ID: {project.id}")
        if project.repository_url:
            click.echo(f"  Repository: {project.repository_url}")
        if project.documentation_path:
            click.echo(f"  Docs Path: {project.documentation_path}")
        click.echo(f"  Created: {project.created_at.strftime('%Y-%m-%d %H:%M')}")
        click.echo(f"  Updated: {project.updated_at.strftime('%Y-%m-%d %H:%M')}")
        
        if project.github_owner or project.github_stars:
            click.echo("\n🐙 GitHub:")
            if project.github_owner:
                click.echo(f"  Owner: {project.github_owner}")
            if project.github_repo:
                click.echo(f"  Repo: {project.github_repo}")
            if project.github_stars:
                click.echo(f"  Stars: {project.github_stars:,}")
            if project.github_language:
                click.echo(f"  Language: {project.github_language}")
            if project.last_synced_at:
                click.echo(f"  Last Synced: {project.last_synced_at.strftime('%Y-%m-%d %H:%M')}")
        
        if docs:
            click.echo("\n📄 Documentation:")
            click.echo(f"  Total Sections: {len(docs)}")
            for level, count in sorted(level_counts.items()):
                click.echo(f"    {level}: {count}")
        
        if child_components:
            click.echo("\n🔗 Components (children):")
            for comp in child_components:
                child = session.exec(select(Project).where(Project.id == comp.child_id)).first()
                if child:
                    click.echo(f"  → {child.name} [{comp.relationship_type}]")
        
        if parent_components:
            click.echo("\n🔗 Part of (parents):")
            for comp in parent_components:
                parent = session.exec(select(Project).where(Project.id == comp.parent_id)).first()
                if parent:
                    click.echo(f"  ← {parent.name} [{comp.relationship_type}]")
        
        click.echo()


@projects.command("rename")
@click.argument("old_name")
@click.argument("new_name")
def projects_rename(old_name: str, new_name: str) -> None:
    """Rename a project.
    
    OLD_NAME: Current name of the project
    NEW_NAME: New name for the project
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == old_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{old_name}' not found.", err=True)
            raise SystemExit(1)
        
        # Check if new name exists
        existing = session.exec(
            select(Project).where(Project.name == new_name)
        ).first()
        if existing:
            click.echo(f"Error: Project '{new_name}' already exists.", err=True)
            raise SystemExit(1)
        
        project.name = new_name
        session.add(project)
        session.commit()
        click.echo(f"OK Renamed '{old_name}' to '{new_name}'")


# =============================================================================
# Parse and Query Commands
# =============================================================================


@cli.command()
@click.option("--owner", "-o", default=None,
              help="Scope to one owner. Default: the owner most repositories share.")
@click.option("--limit", "-n", default=8, show_default=True,
              help="Rows per section.")
@click.option("--section", "-s", "only", default=None,
              help="Print one section by title, case-insensitive substring.")
@click.option("--forks/--no-forks", default=False, show_default=True,
              help="Include forks in scope.")
@click.option("--fast", is_flag=True, default=False,
              help="Skip the readings that spawn git or dial the harness.")
def overview(owner: Optional[str], limit: int, only: Optional[str],
             forks: bool, fast: bool) -> None:
    """Every repository in one reading: the org overview, as text.

    **THE OVERVIEW EXISTED AND ONLY THE TUI COULD SHOW IT.** `overview.build`
    assembles a masthead and every facet at org scope, and the only consumer was
    the dashboard -- so the cohesive picture required an interactive terminal,
    could not be piped, quoted, or put in a pull request, and could not be read
    at all over a connection that will not carry a full-screen application.

    Same builder, same facets, same notes. Nothing here computes a figure: a
    second way of counting is how two views of one number start disagreeing.
    """
    from dossier.overview import build, dominant_owner

    with get_session() as session:
        scope_owner = owner or dominant_owner(session)
        # Everything, unless asked otherwise. Two facets cross a process
        # boundary and cost seconds; the dashboard skips them because it is on
        # the startup path, and this is not -- somebody typed the command.
        picture = build(session, limit=limit, owner=scope_owner,
                        include_forks=forks, beyond_the_database=not fast)

        click.echo("=" * 78)
        click.echo(f"  {picture.scope}")
        click.echo(f"  read from a sync {picture.generated_from}")
        click.echo("=" * 78)

        if picture.masthead and not only:
            click.echo()
            for cell in picture.masthead:
                label = getattr(cell, "label", "")
                value = getattr(cell, "value", "")
                note = getattr(cell, "note", "") or ""
                click.echo(f"  {label:<28} {value}"
                           + (f"   {note}" if note else ""))

        for section in picture.sections:
            if only and only.lower() not in section.title.lower():
                continue
            click.echo()
            click.echo(f"--- {section.title} " + "-" * max(0, 74 - len(section.title)))
            if section.is_empty:
                # An empty section is a fact about the data, not a reason to
                # print nothing: a heading with no rows and no sentence reads
                # as a section that failed to load.
                click.echo("    (nothing in scope)")
            else:
                widths = [
                    max(len(str(section.headers[i])),
                        max(len(str(row[i])) for row in section.rows))
                    for i in range(len(section.headers))
                ]
                click.echo("    " + "  ".join(
                    str(h).ljust(widths[i])
                    for i, h in enumerate(section.headers)))
                click.echo("    " + "  ".join("-" * w for w in widths))
                for row in section.rows:
                    click.echo("    " + "  ".join(
                        str(cell).ljust(widths[i])
                        for i, cell in enumerate(row)))
            if section.note:
                click.echo()
                for line in textwrap.wrap(section.note, width=72):
                    click.echo(f"    {line}")

        click.echo()
        click.echo("-" * 78)
        click.echo("  Every figure is from the last sync, not from now. A section's")
        click.echo("  note says what its rows do and do not mean; read it before")
        click.echo("  quoting a number out of the table above it.")


@cli.command("clone")
@click.argument("repo", required=False)
@click.option("--all", "everything", is_flag=True, default=False,
              help="Clone every absent repository. Asks first.")
@click.option("--into", type=click.Path(), default=None,
              help="Where clones land. Default: beside this checkout.")
@click.option("--depth", type=int, default=None,
              help="Shallow clone. Branch hygiene cannot read one, so it is "
                   "asked for and never assumed.")
@click.option("--yes", is_flag=True, default=False,
              help="Do not ask. For a script that has already decided.")
def clone_cmd(repo, everything, into, depth, yes):
    """Clone what this database knows about and this disk does not have.

    Without REPO or --all it lists and stops. A clone is a network fetch and a
    write to somebody's disk, so listing is the default and acting is asked
    for.

    REPO matches `owner/name` or the bare name.
    """
    from sqlmodel import select

    from dossier.clone import absent, clone, summarise
    from dossier.models.schemas import Project

    with get_session() as session:
        projects = session.exec(select(Project)).all()
        gone = absent(projects, into=Path(into) if into else None)

    if repo:
        wanted = [one for one in gone
                  if repo in (one.repo, one.name)]
        if not wanted:
            here = [one for one in gone if repo.lower() in one.repo.lower()]
            if not here:
                click.echo(f"Nothing absent matches {repo!r}. It may already "
                           f"be here, or not be indexed.", err=True)
                raise SystemExit(1)
            wanted = here
    elif everything:
        wanted = list(gone)
    else:
        if not gone:
            click.echo("Every indexed repository has a clone on this machine.")
            return
        click.echo(f"{len(gone)} indexed repository(ies) have no clone here. "
                   f"Name one, or pass --all:")
        for one in gone:
            mark = "" if one.can_be_cloned else "   (no URL recorded)"
            click.echo(f"  {one.repo:<40} -> {one.into}{mark}")
        return

    if not yes:
        click.echo(f"About to clone {len(wanted)} repository(ies) into "
                   f"{wanted[0].into.parent}:")
        for one in wanted[:10]:
            click.echo(f"  {one.repo}")
        if len(wanted) > 10:
            click.echo(f"  ... and {len(wanted) - 10} more")
        click.confirm("Go ahead?", abort=True)

    outcomes = []
    for one in wanted:
        outcome = clone(one, depth=depth)
        outcomes.append(outcome)
        mark = "ok " if outcome.ok else "-- "
        click.echo(f"{mark}{one.repo}: {outcome.state} {outcome.detail}")
    click.echo("")
    click.echo(summarise(outcomes))


@cli.command("trim")
@click.argument("repo")
@click.option("--delete", is_flag=True, default=False,
              help="Remove them. Without this nothing is removed.")
@click.option("--path", type=click.Path(path_type=Path), default=None,
              help="The clone to read, when it is not beside this one.")
@click.option("--only", multiple=True,
              help="Trim only these branches. Repeatable. Nothing outside the "
                   "plan is ever removed, so naming a kept branch does nothing.")
def trim_cmd(repo: str, delete: bool, path: Path | None, only: tuple[str, ...]):
    """Local branches already in REPO's default branch.

    Lists and stops. `--delete` removes them, and a dry run is what this does
    unless told otherwise -- the same shape as `dossier clone`, mirrored: that
    one writes to a disk and this one removes from it.

    **A branch is trimmable when its tip is an ancestor of `origin/main`**, so
    every commit on it is already there. A branch that reached `main` by squash
    or rebase has no such link and is reported rather than removed. **No remote
    branch is touched**, with or without `--delete`.

    This command makes no network request and reads no API. It runs `git` in a
    clone on this machine.
    """
    from dossier.branches import find_clone
    from dossier.trim import execute, plan, render

    where = path or find_clone(repo)
    if where is None:
        click.echo(f"No clone of {repo!r} beside this one. Pass --path to "
                   f"name it, or `dossier clone {repo}` to make one.", err=True)
        raise SystemExit(1)

    plan_ = plan(repo, where)
    if not plan_.readable:
        click.echo(render(plan_), err=True)
        raise SystemExit(1)

    if not delete:
        click.echo(render(plan_))
        return

    if not plan_.trimmable:
        click.echo(render(plan_))
        return

    removals = execute(plan_, only=only)
    click.echo(render(plan_, removals))

    # **THE RESULT OF A SWEEP IS A DELTA.** `dossier.sweep` states the rule and
    # this follows it: eighteen branches removed in one pass is one unit of
    # work with eighteen parts, not eighteen chores that happened together.
    # Recorded only when something was actually removed -- a sweep that removed
    # nothing produced no work, and a delta for it would be a unit of work
    # nobody did.
    address = _record_trim_delta(repo, plan_, removals) if any(
        r.removed for r in removals) else None
    if address:
        click.echo("")
        click.echo(f"  Recorded as {address}")
        click.echo("")
        _show_delta(address)

    # A refusal exits non-zero. git disagreeing with this module's own claim
    # that a branch is merged is a defect here, and a caller that recorded
    # success would bury it.
    if any(not r.removed for r in removals):
        raise SystemExit(1)


def _record_trim_delta(repo: str, plan_, removals) -> str | None:
    """Store one trim as a delta and return its address, or None with a reason.

    **A TRIM THAT CANNOT BE RECORDED IS STILL A TRIM THAT HAPPENED.** The
    branches are already gone by the time this runs, so failing to find the
    project is reported and never raised -- the alternative is a traceback
    after a successful removal, which reads as though the removal failed.
    """
    from sqlmodel import select

    from dossier.models import utcnow
    from dossier.models.schemas import DeltaPhase, Project, ProjectDelta
    from dossier.trim import as_delta

    fields = as_delta(plan_, removals)
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == repo)).first()
        if project is None:
            project = session.exec(
                select(Project).where(Project.full_name.contains(repo))).first()
        if project is None:
            click.echo("")
            click.echo(f"  No project named {repo!r} in this database, so the "
                       f"trim was not recorded as a delta. The restore "
                       f"commands above are the only copy.", err=True)
            return None

        existing = session.exec(
            select(ProjectDelta)
            .where(ProjectDelta.project_id == project.id)
            .where(ProjectDelta.name == fields["name"])).first()
        # The name is content-addressed, so re-running a trim that removed the
        # same branches finds the delta it already made rather than a second.
        delta = existing or ProjectDelta(project_id=project.id, **fields)
        # Complete on arrival: the work was done before this line ran, and a
        # phase claiming otherwise would be a claim about the future.
        delta.phase = DeltaPhase.COMPLETE
        delta.completed_at = utcnow()
        session.add(delta)
        session.commit()
        session.refresh(delta)
        owner = (project.full_name or f"local/{project.name}").split("/")[0]
        return f"{owner}/{project.name}/delta/{delta.name}"


def _show_delta(address: str) -> None:
    """Navigate to one delta's overview, which in a terminal means showing it.

    **THE SAME VIEW `dossier deltas compose` PRINTS, CALLED RATHER THAN
    COPIED.** A second rendering here would be a second place the delta
    overview is defined, and the two would disagree the first time one was
    fixed. A sweep that told somebody to go and look somewhere else would also
    be a sweep that left its last step undone.
    """
    click.echo("  " + "-" * 60)
    deltas_compose.callback(address)


@cli.command()
@click.option("--name", "-n", default=None,
              help="One workflow by name, case-insensitive substring.")
@click.option("--write", type=click.Path(), default=None,
              help="Write the generated page to this path.")
def cookbook(name, write):
    """Project and git workflows, with the person marked.

    Short, repeatable, composable, and every one of them stops somewhere for a
    human -- or says why it does not. `dossier disk cookbook` is the other one,
    for keeping the workstation off the floor.
    """
    from dossier.cookbook import WORKFLOWS, as_markdown

    if write:
        Path(write).write_text(as_markdown(), encoding="utf-8")
        click.echo(f"Wrote {write}")
        return

    found = [w for w in WORKFLOWS
             if not name or name.lower() in w.name.lower()]
    if not found:
        click.echo(f"No workflow matching {name!r}.", err=True)
        raise SystemExit(1)

    for workflow in found:
        mark = "" if workflow.state == "worked through" else "   (a sketch)"
        click.echo("")
        click.echo(f"{workflow.name}{mark}")
        click.echo(f"  {workflow.intent}")
        click.echo("")
        for index, step in enumerate(workflow.steps, start=1):
            if step.is_gate:
                click.echo(f"  {index}. [you decide] {step.does}")
                click.echo(f"        {step.decides}")
            else:
                click.echo(f"  {index}. {step.does}")
                click.echo(f"        $ {step.command}")
                if step.in_project:
                    click.echo(f"        $ {step.in_project}"
                               f"   (in a project repository)")
            if step.says:
                click.echo(f"        {step.says}")
        if workflow.follows:
            click.echo(f"  follows: {', '.join(workflow.follows)}")
        if workflow.feeds:
            click.echo(f"  feeds:   {', '.join(workflow.feeds)}")
        if workflow.cannot:
            click.echo(f"  cannot:  {workflow.cannot}")


@cli.command()
@click.argument("view", required=False)
@click.option("--project", "-p", default=None,
              help="One repository by name. Default: every repository.")
@click.option("--limit", "-n", default=20, show_default=True,
              help="Rows to print.")
def show(view, project, limit):
    """Print one view outside the application.

    VIEW is a name from the index -- `branches`, `dependencies`, `waiting`.
    Without one this lists what there is.

    **EVERY VIEW BACKED BY A FACET GETS A ROUTE FROM THIS ONE COMMAND.** Eight
    views have a command of their own and ten did not, and writing ten more
    would have been ten more places for the set of views to drift apart. The
    reading is the same one the tab draws, from `dossier.facets`.
    """
    from dossier import facets, views

    if not view:
        click.echo("Views, by the keys that reach them:")
        from dossier.toc import entries

        for entry in entries():
            if not entry.action.startswith("view."):
                continue
            name = entry.action.split(".", 1)[1]
            click.echo(f"  {entry.number:<8} {name:<16} {entry.summary}")
        click.echo("")
        click.echo("`dossier index` prints the whole menu.")
        return

    found = views.BY_NAME.get(view)
    if found is None:
        near = ", ".join(sorted(views.BY_NAME)[:6])
        click.echo(f"No view called {view!r}. Try one of: {near}, ...", err=True)
        raise SystemExit(1)

    on_tab = facets.BY_TAB.get(found.tab, ())
    if not on_tab:
        where = found.cli or "the application"
        click.echo(f"{found.title} is not read from the database. "
                   f"Use `{where}`.", err=True)
        raise SystemExit(1)

    with get_session() as session:
        scoped = None
        if project:
            scoped = session.exec(
                select(Project).where(Project.name == project)
            ).first()
            if scoped is None:
                click.echo(f"No project called {project!r}.", err=True)
                raise SystemExit(1)

        for facet in on_tab:
            section = facet.at(session, project=scoped, limit=limit)
            click.echo("")
            click.echo(section.title)
            click.echo("  " + "  ".join(section.headers))
            for row in section.rows:
                click.echo("  " + "  ".join(str(cell) for cell in row))
            if not section.rows:
                click.echo("  (nothing)")
            if section.note:
                click.echo("")
                click.echo("  " + section.note)


@cli.command()
@click.option("--markdown/--plain", default=False,
              help="Print the generated page instead of the terminal form.")
def index(markdown):
    """Every command in the ring, numbered by the keys that reach it.

    `8.6.6` is the route rather than a label: `m` opens the ring, `8` is Go,
    `6` is Work, `6` is Sweep. The same numbering is in `docs/commands.md`, which
    the test suite regenerates.
    """
    from dossier.toc import as_markdown, entries

    if markdown:
        from dossier.tui.app import DossierApp

        click.echo(as_markdown(DossierApp.RAD_HANDLED), nl=False)
        return

    from dossier.tui.app import DossierApp

    for entry in entries(DossierApp.RAD_HANDLED):
        pad = "  " * (entry.depth - 1)
        if entry.is_menu:
            click.echo(f"{entry.number:<10} {pad}{entry.title}")
            continue
        keys = " ".join(entry.keys)
        mark = "" if entry.wired else "   (not applied yet)"
        click.echo(f"{entry.number:<10} {pad}{entry.title:<24} {keys}{mark}")
        if entry.cli:
            click.echo(f"{'':<10} {pad}  {entry.cli}")


@cli.command()
@click.argument("package", required=False)
@click.option("--at-least", default=2, show_default=True,
              help="How many repositories must declare a package for it to "
                   "count as shared.")
def sweep(package: Optional[str], at_least: int) -> None:
    """What a sweep of PACKAGE would touch, and the version it would reach.

    PACKAGE is optional. Without it this lists what is shared and stops,
    because there is no such thing as *the* package to sweep -- the
    widest-shared one is where a panel starts when nobody has said, and that is
    a starting point rather than an answer.

    The target version is derived from the shares, never given: see
    `sweep.furthest_ahead`.

    Reads and prints. Nothing is written and no pull request is opened.
    """
    from dossier.sweep import find, furthest_ahead, plan, shared_needs

    with get_session() as session:
        if not package:
            shared = shared_needs(session, at_least=at_least)
            if not shared:
                click.echo(f"No package is declared by {at_least} or more "
                           f"repositories.")
                return
            click.echo(f"Declared by {at_least} or more repositories, widest "
                       f"first. Name one to see what a sweep would touch:")
            for name, count in shared:
                click.echo(f"  {name:<32} {count}")
            return

        found = find(session, package)
        if not found.shares:
            click.echo(f"No repository declares {package}.", err=True)
            raise SystemExit(1)

        to_version = furthest_ahead(found)
        if not to_version:
            click.echo(f"{package} is declared by {found.blast_radius} "
                       f"repository(ies) and none states a comparable version, "
                       f"so there is no target to sweep to. That is a person's "
                       f"call, not this command's.", err=True)
            raise SystemExit(1)

        planned = plan(found, to_version)
        click.echo(f"{planned.package} to {to_version} across "
                   f"{planned.blast_radius} repository(ies)")
        click.echo("")
        for share in sorted(planned.shares, key=lambda s: s.project):
            declared = share.declared if share.declared else "no version"
            click.echo(f"  {share.project:<28} {declared:<16} {share.shape}")
            if share.why:
                click.echo(f"  {'':<28} {share.why}")


@cli.command()
@click.argument("project_name")
@click.argument("path", type=click.Path(exists=True))
def parse(project_name: str, path: str) -> None:
    """Parse documentation files for a project.
    
    PROJECT_NAME: Name of the registered project
    PATH: Path to documentation file or directory
    """
    with get_session() as session:
        # Get project
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{project_name}' not found.", err=True)
            raise SystemExit(1)
        
        from dossier.parsers import ParserRegistry

        registry = ParserRegistry.default()
        path_obj = Path(path)
        files_to_parse: list[Path] = []
        
        if path_obj.is_file():
            files_to_parse = [path_obj]
        else:
            # Find all parseable files in directory
            for ext in [".md", ".markdown"]:
                files_to_parse.extend(path_obj.rglob(f"*{ext}"))
        
        total_sections = 0
        for file_path in files_to_parse:
            parser = registry.get_parser(file_path)
            if not parser:
                click.echo(f"  Skipping {file_path} (no parser available)")
                continue
            
            content = file_path.read_text(encoding="utf-8")
            sections = parser.parse(
                content,
                source_file=str(file_path),
                project_id=project.id,
            )
            
            for section in sections:
                session.add(section)
                total_sections += 1
            
            click.echo(f"  Parsed {file_path.name}: {len(sections)} sections")
        
        session.commit()
        click.echo(f"\nTotal sections added: {total_sections}")


@cli.command()
@click.argument("project_name")
@click.option(
    "--level",
    "-l",
    type=click.Choice(["summary", "overview", "detailed", "technical"]),
    default="overview",
    help="Level of detail",
)
@click.option("--section-type", "-t", help="Filter by section type")
@click.option("--search", "-s", help="Search term")
def query(
    project_name: str,
    level: str,
    section_type: Optional[str],
    search: Optional[str],
) -> None:
    """Query documentation for a project.
    
    PROJECT_NAME: Name of the project to query
    """
    doc_level = DocumentationLevel(level)
    
    with get_session() as session:
        # Get project
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{project_name}' not found.", err=True)
            raise SystemExit(1)
        
        # Build query
        level_order = [
            DocumentationLevel.SUMMARY,
            DocumentationLevel.OVERVIEW,
            DocumentationLevel.DETAILED,
            DocumentationLevel.TECHNICAL,
        ]
        max_level_idx = level_order.index(doc_level)
        allowed_levels = level_order[: max_level_idx + 1]
        
        stmt = select(DocumentSection).where(
            DocumentSection.project_id == project.id,
            DocumentSection.level.in_(allowed_levels),
        )
        
        if section_type:
            stmt = stmt.where(DocumentSection.section_type == section_type)
        
        stmt = stmt.order_by(DocumentSection.order)
        sections = list(session.exec(stmt).all())
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            sections = [
                s
                for s in sections
                if search_lower in s.title.lower() or search_lower in s.content.lower()
            ]
        
        if not sections:
            click.echo("No documentation found matching criteria.")
            return
        
        click.echo(f"\n=== {project_name} Documentation ({level}) ===\n")
        for section in sections:
            click.echo(f"## {section.title}")
            click.echo(f"   Type: {section.section_type} | Level: {section.level.value}")
            click.echo(f"\n{section.content}\n")
            click.echo("-" * 40)


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the Dossier API server."""
    import uvicorn
    
    click.echo(f"Starting Dossier API server at http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")
    uvicorn.run(
        "dossier.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


# GitHub commands group
@cli.group()
def github() -> None:
    """GitHub repository commands."""
    pass


@github.command("sync")
@click.argument("repo_url")
@click.option("--name", "-n", help="Project name (default: repo name)")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--description", "-d", help="Override repository description")
@click.option("--no-docs", is_flag=True, help="Skip parsing docs/ folder")
def github_sync(
    repo_url: str,
    name: Optional[str],
    token: Optional[str],
    description: Optional[str],
    no_docs: bool,
) -> None:
    """Sync a GitHub repository as a project.
    
    REPO_URL: GitHub repository URL (e.g., https://github.com/owner/repo)
    
    This command will:
    1. Fetch repository metadata from GitHub
    2. Register or update the project in Dossier
    3. Parse README and documentation files
    4. Fetch languages, dependencies, contributors, and issues
    
    Set GITHUB_TOKEN environment variable for private repos or higher rate limits.
    """
    from dossier.parsers.github import GitHubClient
    from dossier.models import utcnow
    
    with get_session() as session:
        from dossier.parsers import GitHubParser

        with GitHubParser(token) as parser:
            click.echo(f"Fetching repository: {repo_url}")
            
            try:
                repo, sections = parser.parse_repo_url(
                    repo_url,
                    include_docs_folder=not no_docs,
                )
            except Exception as e:
                click.echo(f"Error fetching repository: {e}", err=True)
                raise SystemExit(1)
            
            project_name = name or f"{repo.owner}/{repo.name}"
            
            # Check if project exists
            existing = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if existing:
                click.echo(f"Updating existing project: {project_name}")
                existing.description = description or repo.description
                existing.repository_url = repo.html_url
                existing.github_owner = repo.owner
                existing.github_repo = repo.name
                existing.github_stars = repo.stars
                existing.is_fork = repo.is_fork
                existing.is_archived = repo.is_archived
                existing.github_language = repo.language
                existing.last_synced_at = utcnow()
                existing.updated_at = utcnow()
                project = existing
                
                # Remove old sections for this project
                old_sections = session.exec(
                    select(DocumentSection).where(
                        DocumentSection.project_id == existing.id
                    )
                ).all()
                for old_section in old_sections:
                    session.delete(old_section)
            else:
                click.echo(f"Creating new project: {project_name}")
                project = Project(
                    name=project_name,
                    full_name=f"{repo.owner}/{repo.name}",
                    description=description or repo.description,
                    repository_url=repo.html_url,
                    github_owner=repo.owner,
                    github_repo=repo.name,
                    github_stars=repo.stars,
                    is_fork=repo.is_fork,
                    is_archived=repo.is_archived,
                    github_language=repo.language,
                    last_synced_at=utcnow(),
                )
                session.add(project)
                session.flush()  # Get project ID
            
            # Add sections with correct project_id
            for section in sections:
                section.project_id = project.id
                session.add(section)
            
            # Fetch extended data
            click.echo("  Fetching extended data...")
            
            with GitHubClient(token) as client:
                # Languages
                languages = client.get_languages(repo.owner, repo.name)
                old_langs = session.exec(
                    select(ProjectLanguage).where(ProjectLanguage.project_id == project.id)
                ).all()
                for old in old_langs:
                    session.delete(old)
                for lang in languages:
                    session.add(ProjectLanguage(
                        project_id=project.id,
                        language=lang["language"],
                        bytes_count=lang.get("bytes_count", 0),
                        percentage=lang.get("percentage", 0.0),
                        file_extensions=lang.get("file_extensions"),
                        encoding=lang.get("encoding"),
                    ))
                
                # Dependencies
                dependencies = client.get_dependencies(repo.owner, repo.name)
                old_deps = session.exec(
                    select(ProjectDependency).where(ProjectDependency.project_id == project.id)
                ).all()
                for old in old_deps:
                    session.delete(old)
                for dep in dependencies:
                    session.add(ProjectDependency(
                        project_id=project.id,
                        name=dep["name"],
                        version_spec=dep.get("version_spec"),
                        dep_type=dep.get("dep_type", "runtime"),
                        source=dep.get("source", "unknown"),
                    ))
                
                # Contributors
                contributors = client.get_contributors(repo.owner, repo.name)
                old_contribs = session.exec(
                    select(ProjectContributor).where(ProjectContributor.project_id == project.id)
                ).all()
                for old in old_contribs:
                    session.delete(old)
                for contrib in contributors:
                    session.add(ProjectContributor(
                        project_id=project.id,
                        username=contrib["username"],
                        avatar_url=contrib.get("avatar_url"),
                        contributions=contrib.get("contributions", 0),
                        profile_url=contrib.get("profile_url"),
                    ))
                
                # Issues
                issues = client.get_issues(repo.owner, repo.name, state="all")
                old_issues = session.exec(
                    select(ProjectIssue).where(ProjectIssue.project_id == project.id)
                ).all()
                for old in old_issues:
                    session.delete(old)
                for issue in issues:
                    session.add(ProjectIssue(
                        project_id=project.id,
                        issue_number=issue["issue_number"],
                        title=issue["title"],
                        state=issue.get("state", "open"),
                        author=issue.get("author"),
                        labels=issue.get("labels"),
                    ))
                
                # Branches
                branches = client.get_branches(repo.owner, repo.name)
                old_branches = session.exec(
                    select(ProjectBranch).where(ProjectBranch.project_id == project.id)
                ).all()
                for old in old_branches:
                    session.delete(old)
                for branch in branches:
                    session.add(ProjectBranch(
                        project_id=project.id,
                        name=branch["name"],
                        is_default=branch.get("is_default", False),
                        is_protected=branch.get("is_protected", False),
                        commit_sha=branch.get("commit_sha"),
                        commit_message=branch.get("commit_message"),
                        commit_author=branch.get("commit_author"),
                        commit_date=branch.get("commit_date"),
                    ))
                
                # Pull Requests
                pull_requests = client.get_pull_requests(repo.owner, repo.name, state="all")
                old_prs = session.exec(
                    select(ProjectPullRequest).where(ProjectPullRequest.project_id == project.id)
                ).all()
                for old in old_prs:
                    session.delete(old)
                for pr in pull_requests:
                    session.add(ProjectPullRequest(
                        project_id=project.id,
                        pr_number=pr["pr_number"],
                        title=pr["title"],
                        state=pr.get("state", "open"),
                        author=pr.get("author"),
                        base_branch=pr.get("base_branch"),
                        head_branch=pr.get("head_branch"),
                        is_draft=pr.get("is_draft", False),
                        is_merged=pr.get("is_merged", False),
                        additions=pr.get("additions", 0),
                        deletions=pr.get("deletions", 0),
                        labels=pr.get("labels"),
                        pr_created_at=pr.get("pr_created_at"),
                        pr_updated_at=pr.get("pr_updated_at"),
                        pr_merged_at=pr.get("pr_merged_at"),
                    ))
                
                # Releases
                releases = client.get_releases(repo.owner, repo.name)
                old_releases = session.exec(
                    select(ProjectRelease).where(ProjectRelease.project_id == project.id)
                ).all()
                for old in old_releases:
                    session.delete(old)
                for release in releases:
                    session.add(ProjectRelease(
                        project_id=project.id,
                        tag_name=release["tag_name"],
                        name=release.get("name"),
                        body=release.get("body"),
                        is_prerelease=release.get("is_prerelease", False),
                        is_draft=release.get("is_draft", False),
                        author=release.get("author"),
                        target_commitish=release.get("target_commitish"),
                        release_created_at=release.get("release_created_at"),
                        release_published_at=release.get("release_published_at"),
                    ))
            
            session.commit()
            
            click.echo(f"\nOK Synced: {repo.full_name}")
            click.echo(f"  Project: {project_name}")
            click.echo(f"  Description: {repo.description or 'N/A'}")
            click.echo(f"  Stars: {repo.stars}")
            click.echo(f"  Language: {repo.language or 'N/A'}")
            click.echo(f"  📄 Docs: {len(sections)}")
            click.echo(f"  💻 Languages: {len(languages)}")
            click.echo(f"  📦 Dependencies: {len(dependencies)}")
            click.echo(f"  👥 Contributors: {len(contributors)}")
            click.echo(f"  🐛 Issues: {len(issues)}")
            click.echo(f"  🌿 Branches: {len(branches)}")
            click.echo(f"  🔀 Pull Requests: {len(pull_requests)}")
            click.echo(f"  🏷️  Releases: {len(releases)}")


@github.command("search")
@click.argument("query")
@click.option("--limit", "-l", default=10, help="Number of results")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--sort", type=click.Choice(["stars", "forks", "updated"]), default="stars")
def github_search(query: str, limit: int, token: Optional[str], sort: str) -> None:
    """Search GitHub repositories.
    
    QUERY: Search query (supports GitHub search syntax)
    
    Examples:
        dossier github search "fastapi"
        dossier github search "language:python topic:cli"
        dossier github search "org:microsoft language:typescript"
    """
    from dossier.parsers import GitHubClient
    
    with GitHubClient(token) as client:
        try:
            repos = client.search_repos(query, sort=sort, per_page=limit)
        except Exception as e:
            click.echo(f"Error searching: {e}", err=True)
            raise SystemExit(1)
        
        if not repos:
            click.echo("No repositories found.")
            return
        
        click.echo(f"\nFound {len(repos)} repositories:\n")
        click.echo("-" * 60)
        
        for repo in repos:
            click.echo(f"  {repo.full_name} ★ {repo.stars}")
            if repo.description:
                # Truncate long descriptions
                desc = repo.description[:60] + "..." if len(repo.description) > 60 else repo.description
                click.echo(f"    {desc}")
            if repo.language:
                click.echo(f"    Language: {repo.language}")
            click.echo(f"    URL: {repo.html_url}")
            click.echo()


@github.command("info")
@click.argument("repo_url")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
def github_info(repo_url: str, token: Optional[str]) -> None:
    """Show information about a GitHub repository.
    
    REPO_URL: GitHub repository URL
    """
    from dossier.parsers import GitHubClient
    
    with GitHubClient(token) as client:
        try:
            repo = client.get_repo_from_url(repo_url)
        except Exception as e:
            click.echo(f"Error fetching repository: {e}", err=True)
            raise SystemExit(1)
        
        click.echo(f"\n{repo.full_name}")
        click.echo("=" * 40)
        click.echo(f"Description: {repo.description or 'N/A'}")
        click.echo(f"URL: {repo.html_url}")
        click.echo(f"Default branch: {repo.default_branch}")
        click.echo(f"Language: {repo.language or 'N/A'}")
        click.echo(f"Stars: {repo.stars}")
        if repo.topics:
            click.echo(f"Topics: {', '.join(repo.topics)}")
        
        # Check for docs
        docs = client.list_docs_files(repo.owner, repo.name)
        readme = client.get_readme(repo.owner, repo.name)
        
        click.echo(f"\nDocumentation:")
        click.echo(f"  README: {'Yes' if readme else 'No'}")
        click.echo(f"  Doc files: {len(docs)}")
        if docs:
            for doc in docs[:5]:  # Show first 5
                click.echo(f"    - {doc['path']}")
            if len(docs) > 5:
                click.echo(f"    ... and {len(docs) - 5} more")


def _sync_repos_batch(
    repos: list,
    token: Optional[str],
    session,
    parent_project,
    owner_name: str,
    no_docs: bool,
    batch_size: int = 5,
    delay_between_batches: float = 2.0,
    force: bool = False,
) -> tuple[int, int, int, bool]:
    """Sync repositories in intelligent batches with rate limit handling.
    
    Returns:
        Tuple of (synced_count, failed_count, skipped_count, was_rate_limited)
    """
    from dossier.parsers import GitHubClient
    from dossier.parsers.github import BatchResult
    from dossier.models import utcnow
    import time
    
    synced = 0
    failed = 0
    skipped = 0
    rate_limited = False
    
    total = len(repos)
    
    with GitHubClient(token, respect_rate_limit=True) as client:
        # Check rate limit before starting
        try:
            rate_info = client.check_rate_limit()
            click.echo(f"📊 Rate limit: {rate_info.remaining}/{rate_info.limit} remaining")
            if rate_info.remaining < 10:
                click.echo(click.style(
                    f"⚠️  Low rate limit! Consider using --token for higher limits.",
                    fg="yellow"
                ))
        except Exception:
            pass  # Continue without rate info
        
        from dossier.parsers import GitHubParser

        with GitHubParser(token) as parser:
            # Process in batches
            for batch_start in range(0, total, batch_size):
                batch_end = min(batch_start + batch_size, total)
                batch_repos = repos[batch_start:batch_end]
                batch_num = (batch_start // batch_size) + 1
                total_batches = (total + batch_size - 1) // batch_size
                
                click.echo(f"\n📦 Batch {batch_num}/{total_batches} ({len(batch_repos)} repos)")
                
                for i, repo in enumerate(batch_repos):
                    repo_num = batch_start + i + 1
                    click.echo(f"  [{repo_num}/{total}] {repo.full_name}...", nl=False)
                    
                    # Check if already synced recently (within last hour)
                    project_name = f"{owner_name}/{repo.name}"
                    existing = session.exec(
                        select(Project).where(Project.name == project_name)
                    ).first()
                    
                    if existing and existing.last_synced_at and not force:
                        from datetime import timedelta, timezone
                        # Handle timezone-naive datetimes from SQLite
                        last_synced = existing.last_synced_at
                        if last_synced.tzinfo is None:
                            last_synced = last_synced.replace(tzinfo=timezone.utc)
                        age = utcnow() - last_synced
                        if age < timedelta(hours=1):
                            click.echo(click.style(" ⏭ skipped (recently synced)", fg="cyan"))
                            skipped += 1
                            continue
                    
                    try:
                        _, sections = parser.parse_repo(
                            repo.owner,
                            repo.name,
                            include_docs_folder=not no_docs,
                        )
                        
                        if existing:
                            existing.description = repo.description
                            existing.repository_url = repo.html_url
                            existing.github_owner = repo.owner
                            existing.github_repo = repo.name
                            existing.github_stars = repo.stars
                            existing.is_fork = repo.is_fork
                            existing.is_archived = repo.is_archived
                            existing.github_language = repo.language
                            existing.last_synced_at = utcnow()
                            existing.updated_at = utcnow()
                            project = existing
                            
                            # Remove old sections
                            old_sections = session.exec(
                                select(DocumentSection).where(
                                    DocumentSection.project_id == existing.id
                                )
                            ).all()
                            for old in old_sections:
                                session.delete(old)
                        else:
                            project = Project(
                                name=project_name,
                                full_name=f"{repo.owner}/{repo.name}",
                                description=repo.description,
                                repository_url=repo.html_url,
                                github_owner=repo.owner,
                                github_repo=repo.name,
                                github_stars=repo.stars,
                                is_fork=repo.is_fork,
                                is_archived=repo.is_archived,
                                github_language=repo.language,
                                last_synced_at=utcnow(),
                            )
                            session.add(project)
                            session.flush()
                        
                        # Add sections
                        for section in sections:
                            section.project_id = project.id
                            session.add(section)
                        
                        # Fetch and store extended data
                        try:
                            # Languages
                            languages = client.get_languages(repo.owner, repo.name)
                            old_langs = session.exec(
                                select(ProjectLanguage).where(
                                    ProjectLanguage.project_id == project.id
                                )
                            ).all()
                            for old in old_langs:
                                session.delete(old)
                            for lang in languages:
                                session.add(ProjectLanguage(
                                    project_id=project.id,
                                    language=lang["language"],
                                    bytes_count=lang.get("bytes_count", 0),
                                    percentage=lang.get("percentage", 0.0),
                                    file_extensions=lang.get("file_extensions"),
                                    encoding=lang.get("encoding"),
                                ))
                            
                            # Dependencies
                            dependencies = client.get_dependencies(repo.owner, repo.name)
                            old_deps = session.exec(
                                select(ProjectDependency).where(
                                    ProjectDependency.project_id == project.id
                                )
                            ).all()
                            for old in old_deps:
                                session.delete(old)
                            for dep in dependencies:
                                session.add(ProjectDependency(
                                    project_id=project.id,
                                    name=dep["name"],
                                    version_spec=dep.get("version_spec"),
                                    dep_type=dep.get("dep_type", "runtime"),
                                    source=dep.get("source", "unknown"),
                                ))
                            
                            # Contributors (limit to top 10 for batch)
                            contributors = client.get_contributors(
                                repo.owner, repo.name, max_contributors=10
                            )
                            old_contribs = session.exec(
                                select(ProjectContributor).where(
                                    ProjectContributor.project_id == project.id
                                )
                            ).all()
                            for old in old_contribs:
                                session.delete(old)
                            for contrib in contributors:
                                session.add(ProjectContributor(
                                    project_id=project.id,
                                    username=contrib["username"],
                                    avatar_url=contrib.get("avatar_url"),
                                    contributions=contrib.get("contributions", 0),
                                    profile_url=contrib.get("profile_url"),
                                ))
                            
                            # Issues (limit to 20 for batch)
                            issues = client.get_issues(
                                repo.owner, repo.name, state="all", max_issues=20
                            )
                            old_issues = session.exec(
                                select(ProjectIssue).where(
                                    ProjectIssue.project_id == project.id
                                )
                            ).all()
                            for old in old_issues:
                                session.delete(old)
                            for issue in issues:
                                session.add(ProjectIssue(
                                    project_id=project.id,
                                    issue_number=issue["issue_number"],
                                    title=issue["title"],
                                    state=issue.get("state", "open"),
                                    author=issue.get("author"),
                                    labels=issue.get("labels"),
                                ))
                            
                            # Branches (limit to 20 for batch)
                            branches = client.get_branches(
                                repo.owner, repo.name, max_branches=20
                            )
                            old_branches = session.exec(
                                select(ProjectBranch).where(
                                    ProjectBranch.project_id == project.id
                                )
                            ).all()
                            for old in old_branches:
                                session.delete(old)
                            for branch in branches:
                                session.add(ProjectBranch(
                                    project_id=project.id,
                                    name=branch["name"],
                                    is_default=branch.get("is_default", False),
                                    is_protected=branch.get("is_protected", False),
                                    commit_sha=branch.get("commit_sha"),
                                    commit_message=branch.get("commit_message"),
                                    commit_author=branch.get("commit_author"),
                                    commit_date=branch.get("commit_date"),
                                ))
                            
                            # Pull Requests (limit to 20 for batch)
                            pull_requests = client.get_pull_requests(
                                repo.owner, repo.name, state="all", max_prs=20
                            )
                            old_prs = session.exec(
                                select(ProjectPullRequest).where(
                                    ProjectPullRequest.project_id == project.id
                                )
                            ).all()
                            for old in old_prs:
                                session.delete(old)
                            for pr in pull_requests:
                                session.add(ProjectPullRequest(
                                    project_id=project.id,
                                    pr_number=pr["pr_number"],
                                    title=pr["title"],
                                    state=pr.get("state", "open"),
                                    author=pr.get("author"),
                                    base_branch=pr.get("base_branch"),
                                    head_branch=pr.get("head_branch"),
                                    is_draft=pr.get("is_draft", False),
                                    is_merged=pr.get("is_merged", False),
                                    additions=pr.get("additions", 0),
                                    deletions=pr.get("deletions", 0),
                                    labels=pr.get("labels"),
                                    pr_created_at=pr.get("pr_created_at"),
                                    pr_updated_at=pr.get("pr_updated_at"),
                                    pr_merged_at=pr.get("pr_merged_at"),
                                ))
                            
                            # Releases (limit to 10 for batch)
                            releases = client.get_releases(
                                repo.owner, repo.name, max_releases=10
                            )
                            old_releases = session.exec(
                                select(ProjectRelease).where(
                                    ProjectRelease.project_id == project.id
                                )
                            ).all()
                            for old in old_releases:
                                session.delete(old)
                            for release in releases:
                                session.add(ProjectRelease(
                                    project_id=project.id,
                                    tag_name=release["tag_name"],
                                    name=release.get("name"),
                                    body=release.get("body"),
                                    is_prerelease=release.get("is_prerelease", False),
                                    is_draft=release.get("is_draft", False),
                                    author=release.get("author"),
                                    target_commitish=release.get("target_commitish"),
                                    release_created_at=release.get("release_created_at"),
                                    release_published_at=release.get("release_published_at"),
                                ))
                        except Exception:
                            pass  # Extended data is optional
                        
                        # Add as subcomponent if parent specified
                        if parent_project and project.id != parent_project.id:
                            existing_link = session.exec(
                                select(ProjectComponent).where(
                                    ProjectComponent.parent_id == parent_project.id,
                                    ProjectComponent.child_id == project.id,
                                )
                            ).first()
                            
                            if not existing_link:
                                link = ProjectComponent(
                                    parent_id=parent_project.id,
                                    child_id=project.id,
                                    relationship_type="component",
                                    order=repo_num,
                                )
                                session.add(link)
                        
                        session.commit()
                        click.echo(click.style(f" OK ({len(sections)} sections)", fg="green"))
                        synced += 1
                        
                    except Exception as e:
                        error_msg = str(e)
                        if "rate limit" in error_msg.lower():
                            click.echo(click.style(f" ⏸ rate limited", fg="yellow"))
                            rate_limited = True
                            # Save progress and stop
                            session.commit()
                            click.echo(click.style(
                                f"\n⚠️  Rate limit hit. Run again to continue from where you left off.",
                                fg="yellow"
                            ))
                            return synced, failed, skipped, rate_limited
                        else:
                            click.echo(click.style(f" ✗ {error_msg[:50]}", fg="red"))
                            failed += 1
                            session.rollback()
                
                # Commit batch and pause between batches (except last)
                session.commit()
                if batch_end < total:
                    # Check remaining rate limit
                    remaining = client.rate_limit.remaining
                    if remaining < 20:
                        wait_time = min(client.rate_limit.seconds_until_reset, 60)
                        if wait_time > 0:
                            click.echo(f"  ⏳ Pausing {wait_time:.0f}s (rate limit: {remaining} remaining)")
                            time.sleep(wait_time)
                    else:
                        time.sleep(delay_between_batches)
    
    return synced, failed, skipped, rate_limited


@github.command("sync-user")
@click.argument("username")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--parent", "-p", help="Parent project to add repos as subcomponents")
@click.option("--limit", "-l", default=0, help="Max repos to sync (0 = all)")
@click.option("--skip-forks", is_flag=True, help="Skip forked repositories")
@click.option("--language", help="Filter by programming language")
@click.option("--no-docs", is_flag=True, help="Skip parsing docs/ folder")
@click.option("--batch-size", "-b", default=5, help="Repos per batch (default: 5)")
@click.option("--force", "-f", is_flag=True, help="Force re-sync even if recently synced")
def github_sync_user(
    username: str,
    token: Optional[str],
    parent: Optional[str],
    limit: int,
    skip_forks: bool,
    language: Optional[str],
    no_docs: bool,
    batch_size: int,
    force: bool,
) -> None:
    """Sync all repositories from a GitHub user account.
    
    USERNAME: GitHub username to sync repos from
    
    Features intelligent batching with:
    - Automatic retry on transient errors
    - Rate limit detection and waiting
    - Skip recently synced repos (use --force to override)
    - Resume capability (just run again to continue)
    
    Examples:
        dossier github sync-user octocat
        dossier github sync-user astral-sh --batch-size 3
        dossier github sync-user myuser --language python --force
    """
    from dossier.parsers import GitHubClient
    
    with get_session() as session:
        # Get or create parent project if specified
        parent_project = None
        if parent:
            parent_project = session.exec(
                select(Project).where(Project.name == parent)
            ).first()
            if not parent_project:
                click.echo(f"Creating parent project: {parent}")
                parent_project = Project(
                    name=parent,
                    full_name=f"github/user/{username}",
                    description=f"GitHub repositories for {username}",
                    github_owner=username,
                )
                session.add(parent_project)
                session.flush()
        
        click.echo(f"🔍 Fetching repositories for user: {username}")
        
        with GitHubClient(token) as client:
            try:
                repos = client.list_user_repos(username)
            except Exception as e:
                click.echo(f"Error fetching repositories: {e}", err=True)
                raise SystemExit(1)
        
        # Apply filters
        original_count = len(repos)
        if skip_forks:
            repos = [r for r in repos if not r.name.endswith("-fork")]
        if language:
            repos = [r for r in repos if r.language and r.language.lower() == language.lower()]
        if limit > 0:
            repos = repos[:limit]
        
        click.echo(f"📋 Found {len(repos)} repositories", nl=False)
        if len(repos) != original_count:
            click.echo(f" (filtered from {original_count})")
        else:
            click.echo()
        
        if not repos:
            click.echo("No repositories to sync.")
            return
        
        synced, failed, skipped, rate_limited = _sync_repos_batch(
            repos=repos,
            token=token,
            session=session,
            parent_project=parent_project,
            owner_name=username,
            no_docs=no_docs,
            batch_size=batch_size,
            force=force,
        )
        
        click.echo(f"\n{'='*50}")
        click.echo(f"✅ Synced: {synced} | ❌ Failed: {failed} | ⏭ Skipped: {skipped}")
        if parent_project:
            click.echo(f"📁 Parent project: {parent}")
        if rate_limited:
            click.echo(click.style("💡 Tip: Run again to continue syncing remaining repos", fg="cyan"))


@github.command("sync-org")
@click.argument("org")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--parent", "-p", help="Parent project to add repos as subcomponents")
@click.option("--limit", "-l", default=0, help="Max repos to sync (0 = all)")
@click.option("--language", help="Filter by programming language")
@click.option("--no-docs", is_flag=True, help="Skip parsing docs/ folder")
@click.option("--batch-size", "-b", default=5, help="Repos per batch (default: 5)")
@click.option("--force", "-f", is_flag=True, help="Force re-sync even if recently synced")
def github_sync_org(
    org: str,
    token: Optional[str],
    parent: Optional[str],
    limit: int,
    language: Optional[str],
    no_docs: bool,
    batch_size: int,
    force: bool,
) -> None:
    """Sync all repositories from a GitHub organization.
    
    ORG: GitHub organization name
    
    Features intelligent batching with:
    - Automatic retry on transient errors
    - Rate limit detection and waiting
    - Skip recently synced repos (use --force to override)
    - Resume capability (just run again to continue)
    
    Examples:
        dossier github sync-org microsoft --limit 10
        dossier github sync-org astral-sh --batch-size 3
        dossier github sync-org myorg --language python --force
    """
    from dossier.parsers import GitHubClient
    
    with get_session() as session:
        # Get or create parent project if specified
        parent_project = None
        if parent:
            parent_project = session.exec(
                select(Project).where(Project.name == parent)
            ).first()
            if not parent_project:
                click.echo(f"Creating parent project: {parent}")
                parent_project = Project(
                    name=parent,
                    full_name=f"github/org/{org}",
                    description=f"GitHub repositories for {org}",
                    github_owner=org,
                )
                session.add(parent_project)
                session.flush()
        
        click.echo(f"🔍 Fetching repositories for org: {org}")
        
        with GitHubClient(token) as client:
            try:
                repos = client.list_org_repos(org)
            except Exception as e:
                click.echo(f"Error fetching repositories: {e}", err=True)
                raise SystemExit(1)
        
        # Apply filters
        original_count = len(repos)
        if language:
            repos = [r for r in repos if r.language and r.language.lower() == language.lower()]
        if limit > 0:
            repos = repos[:limit]
        
        click.echo(f"📋 Found {len(repos)} repositories", nl=False)
        if len(repos) != original_count:
            click.echo(f" (filtered from {original_count})")
        else:
            click.echo()
        
        if not repos:
            click.echo("No repositories to sync.")
            return
        
        synced, failed, skipped, rate_limited = _sync_repos_batch(
            repos=repos,
            token=token,
            session=session,
            parent_project=parent_project,
            owner_name=org,
            no_docs=no_docs,
            batch_size=batch_size,
            force=force,
        )
        
        click.echo(f"\n{'='*50}")
        click.echo(f"✅ Synced: {synced} | ❌ Failed: {failed} | ⏭ Skipped: {skipped}")
        if parent_project:
            click.echo(f"📁 Parent project: {parent}")
        if rate_limited:
            click.echo(click.style("💡 Tip: Run again to continue syncing remaining repos", fg="cyan"))


# Project subcomponent commands
@cli.group()
def components() -> None:
    """Manage project subcomponents."""
    pass


@components.command("add")
@click.argument("parent_name")
@click.argument("child_name")
@click.option("--type", "-t", "rel_type", default="component", 
              type=click.Choice(["component", "dependency", "related"]),
              help="Relationship type")
def add_component(parent_name: str, child_name: str, rel_type: str) -> None:
    """Add a project as a subcomponent of another project.
    
    PARENT_NAME: Name of the parent project
    CHILD_NAME: Name of the child project to add
    """
    with get_session() as session:
        parent = session.exec(
            select(Project).where(Project.name == parent_name)
        ).first()
        if not parent:
            click.echo(f"Error: Parent project '{parent_name}' not found.", err=True)
            raise SystemExit(1)
        
        child = session.exec(
            select(Project).where(Project.name == child_name)
        ).first()
        if not child:
            click.echo(f"Error: Child project '{child_name}' not found.", err=True)
            raise SystemExit(1)
        
        if parent.id == child.id:
            click.echo("Error: Cannot add a project as its own component.", err=True)
            raise SystemExit(1)
        
        existing = session.exec(
            select(ProjectComponent).where(
                ProjectComponent.parent_id == parent.id,
                ProjectComponent.child_id == child.id,
            )
        ).first()
        
        if existing:
            click.echo(f"'{child_name}' is already a {existing.relationship_type} of '{parent_name}'.")
            return
        
        # Get max order
        max_order = session.exec(
            select(ProjectComponent.order)
            .where(ProjectComponent.parent_id == parent.id)
            .order_by(ProjectComponent.order.desc())
        ).first() or 0
        
        link = ProjectComponent(
            parent_id=parent.id,
            child_id=child.id,
            relationship_type=rel_type,
            order=max_order + 1,
        )
        session.add(link)
        session.commit()
        
        click.echo(f"Added '{child_name}' as {rel_type} of '{parent_name}'")


@components.command("remove")
@click.argument("parent_name")
@click.argument("child_name")
def remove_component(parent_name: str, child_name: str) -> None:
    """Remove a subcomponent from a project.
    
    PARENT_NAME: Name of the parent project
    CHILD_NAME: Name of the child project to remove
    """
    with get_session() as session:
        parent = session.exec(
            select(Project).where(Project.name == parent_name)
        ).first()
        if not parent:
            click.echo(f"Error: Parent project '{parent_name}' not found.", err=True)
            raise SystemExit(1)
        
        child = session.exec(
            select(Project).where(Project.name == child_name)
        ).first()
        if not child:
            click.echo(f"Error: Child project '{child_name}' not found.", err=True)
            raise SystemExit(1)
        
        link = session.exec(
            select(ProjectComponent).where(
                ProjectComponent.parent_id == parent.id,
                ProjectComponent.child_id == child.id,
            )
        ).first()
        
        if not link:
            click.echo(f"'{child_name}' is not a component of '{parent_name}'.")
            return
        
        session.delete(link)
        session.commit()
        
        click.echo(f"Removed '{child_name}' from '{parent_name}'")


@components.command("list")
@click.argument("project_name")
@click.option("--recursive", "-r", is_flag=True, help="Show nested components")
def list_components(project_name: str, recursive: bool) -> None:
    """List subcomponents of a project.
    
    PROJECT_NAME: Name of the project
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{project_name}' not found.", err=True)
            raise SystemExit(1)
        
        def print_components(proj_id: int, indent: int = 0) -> None:
            links = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.parent_id == proj_id)
                .order_by(ProjectComponent.order)
            ).all()
            
            for link in links:
                child = session.exec(
                    select(Project).where(Project.id == link.child_id)
                ).first()
                if child:
                    prefix = "  " * indent
                    type_badge = f"[{link.relationship_type}]"
                    click.echo(f"{prefix}├─ {child.name} {type_badge}")
                    if child.description:
                        click.echo(f"{prefix}│  {child.description[:50]}...")
                    if recursive:
                        print_components(child.id, indent + 1)
        
        click.echo(f"\n{project_name}")
        click.echo("=" * len(project_name))
        print_components(project.id)
        click.echo()


# =============================================================================
# Dev Commands - Development and iteration helpers
# =============================================================================


@cli.group()
def dev() -> None:
    """Development utilities for quick iteration.
    
    Commands for managing database state, debugging, and rapid development.
    """
    pass


@dev.command("reset")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def dev_reset(yes: bool) -> None:
    """Reset database to fresh state (deletes all data).
    
    This will:
    - Drop all tables
    - Recreate empty tables
    - Remove any orphaned data
    
    Use with caution in production!
    """
    if not yes:
        click.confirm(
            click.style("⚠️  This will delete ALL data. Continue?", fg="yellow"),
            abort=True,
        )
    
    db_path = Path("dossier.db")
    
    # Drop and recreate tables
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    
    click.echo(click.style("OK Database reset to fresh state", fg="green"))
    
    if db_path.exists():
        size = db_path.stat().st_size
        click.echo(f"  Database file: {db_path} ({size} bytes)")


@dev.command("clear")
@click.option("--projects", "-p", is_flag=True, help="Clear all projects")
@click.option("--docs", "-d", is_flag=True, help="Clear all document sections")
@click.option("--components", "-c", is_flag=True, help="Clear all component relationships")
@click.option("--all", "-a", "clear_all", is_flag=True, help="Clear everything")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def dev_clear(
    projects: bool,
    docs: bool,
    components: bool,
    clear_all: bool,
    yes: bool,
) -> None:
    """Clear specific data from the database.
    
    Selectively remove data while keeping tables intact.
    
    Examples:
        dossier dev clear --docs          # Clear only document sections
        dossier dev clear --projects -y   # Clear projects without confirmation
        dossier dev clear --all           # Clear everything
    """
    if not any([projects, docs, components, clear_all]):
        click.echo("Specify what to clear: --projects, --docs, --components, or --all")
        raise SystemExit(1)
    
    if clear_all:
        projects = docs = components = True
    
    targets = []
    if docs:
        targets.append("document sections")
    if components:
        targets.append("component relationships")
    if projects:
        targets.append("projects")
    
    if not yes:
        click.confirm(
            f"Clear {', '.join(targets)}?",
            abort=True,
        )
    
    with get_session() as session:
        counts = {}
        
        # Order matters for foreign key constraints
        if docs:
            result = session.exec(select(DocumentSection)).all()
            counts["Document sections"] = len(result)
            for item in result:
                session.delete(item)
        
        if components:
            result = session.exec(select(ProjectComponent)).all()
            counts["Component relationships"] = len(result)
            for item in result:
                session.delete(item)
        
        if projects:
            result = session.exec(select(Project)).all()
            counts["Projects"] = len(result)
            for item in result:
                session.delete(item)
        
        session.commit()
    
    click.echo(click.style("OK Cleared:", fg="green"))
    for name, count in counts.items():
        click.echo(f"  {name}: {count} deleted")


@dev.command("status")
def dev_status() -> None:
    """Show database status and statistics."""
    db_path = Path("dossier.db")
    
    click.echo("\n📊 Database Status")
    click.echo("=" * 40)
    
    # File info
    if db_path.exists():
        size = db_path.stat().st_size
        size_kb = size / 1024
        click.echo(f"File: {db_path.absolute()}")
        click.echo(f"Size: {size_kb:.1f} KB ({size:,} bytes)")
    else:
        click.echo(f"File: {db_path} (not created yet)")
    
    click.echo()
    
    # Table counts
    with get_session() as session:
        project_count = len(session.exec(select(Project)).all())
        doc_count = len(session.exec(select(DocumentSection)).all())
        component_count = len(session.exec(select(ProjectComponent)).all())
        
        click.echo("📁 Tables:")
        click.echo(f"  Projects:       {project_count:>6}")
        click.echo(f"  Doc Sections:   {doc_count:>6}")
        click.echo(f"  Components:     {component_count:>6}")
        
        # GitHub sync info
        synced_projects = [p for p in session.exec(select(Project)).all() if p.last_synced_at]
        
        if synced_projects:
            click.echo()
            click.echo("🔄 Recently Synced:")
            for proj in sorted(synced_projects, key=lambda p: p.last_synced_at, reverse=True)[:5]:
                sync_time = proj.last_synced_at.strftime("%Y-%m-%d %H:%M") if proj.last_synced_at else "never"
                stars = f"⭐{proj.github_stars}" if proj.github_stars else ""
                click.echo(f"  {proj.name}: {sync_time} {stars}")
    
    click.echo()


@dev.command("vacuum")
def dev_vacuum() -> None:
    """Optimize database by running VACUUM.
    
    Reclaims unused space and defragments the database file.
    """
    from sqlalchemy import text
    
    db_path = Path("dossier.db")
    size_before = db_path.stat().st_size if db_path.exists() else 0
    
    with engine.connect() as conn:
        conn.execute(text("VACUUM"))
        conn.commit()
    
    size_after = db_path.stat().st_size if db_path.exists() else 0
    saved = size_before - size_after
    
    click.echo(click.style("OK Database vacuumed", fg="green"))
    click.echo(f"  Before: {size_before:,} bytes")
    click.echo(f"  After:  {size_after:,} bytes")
    if saved > 0:
        click.echo(f"  Saved:  {saved:,} bytes ({saved/1024:.1f} KB)")


@dev.command("dump")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "summary"]), default="summary")
def dev_dump(output: Optional[str], fmt: str) -> None:
    """Dump database contents for inspection.
    
    Useful for debugging and understanding current state.
    """
    import json
    
    with get_session() as session:
        projects = session.exec(select(Project)).all()
        docs = session.exec(select(DocumentSection)).all()
        components = session.exec(select(ProjectComponent)).all()
        
        if fmt == "json":
            data = {
                "projects": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "github_owner": p.github_owner,
                        "github_stars": p.github_stars,
                        "last_synced_at": p.last_synced_at.isoformat() if p.last_synced_at else None,
                        "doc_count": len([d for d in docs if d.project_id == p.id]),
                    }
                    for p in projects
                ],
                "components": [
                    {
                        "parent_id": c.parent_id,
                        "child_id": c.child_id,
                        "relationship_type": c.relationship_type,
                    }
                    for c in components
                ],
                "stats": {
                    "total_projects": len(projects),
                    "total_docs": len(docs),
                    "total_components": len(components),
                },
            }
            content = json.dumps(data, indent=2)
        else:
            lines = ["=== Database Dump ===", ""]
            lines.append(f"Projects ({len(projects)}):")
            for p in projects:
                doc_count = len([d for d in docs if d.project_id == p.id])
                lines.append(f"  [{p.id}] {p.name} ({doc_count} docs)")
            
            lines.append("")
            lines.append(f"Components ({len(components)}):")
            for c in components:
                parent = next((p.name for p in projects if p.id == c.parent_id), "?")
                child = next((p.name for p in projects if p.id == c.child_id), "?")
                lines.append(f"  {parent} -> {child} [{c.relationship_type}]")
            
            content = "\n".join(lines)
        
        if output:
            Path(output).write_text(content)
            click.echo(f"Dumped to {output}")
        else:
            click.echo(content)


@dev.command("seed")
@click.option("--example", "-e", is_flag=True, help="Create example project with docs")
def dev_seed(example: bool) -> None:
    """Seed database with sample data for testing.
    
    Creates sample projects and documentation for development.
    """
    from dossier.models import utcnow
    
    with get_session() as session:
        if example:
            # Create a sample project
            project = Project(
                name="example-project",
                full_name="example/project",
                description="An example project for testing Dossier",
                repository_url="https://github.com/example/project",
                documentation_path="./docs",
            )
            session.add(project)
            session.flush()
            
            # Add sample documentation
            sections = [
                DocumentSection(
                    project_id=project.id,
                    title="Getting Started",
                    content="This is the getting started guide for the example project.",
                    level=DocumentationLevel.SUMMARY,
                    source_file="README.md",
                    section_type="guide",
                ),
                DocumentSection(
                    project_id=project.id,
                    title="Installation",
                    content="Run `pip install example-project` to install.\n\nRequirements:\n- Python 3.11+\n- pip",
                    level=DocumentationLevel.OVERVIEW,
                    source_file="README.md",
                    section_type="setup",
                ),
                DocumentSection(
                    project_id=project.id,
                    title="API Reference",
                    content="## Functions\n\n### `do_something(arg: str) -> bool`\n\nDoes something important.",
                    level=DocumentationLevel.DETAILED,
                    source_file="docs/api.md",
                    section_type="reference",
                ),
                DocumentSection(
                    project_id=project.id,
                    title="Architecture",
                    content="The system uses a layered architecture with:\n- CLI layer (Click)\n- API layer (FastAPI)\n- Data layer (SQLModel)",
                    level=DocumentationLevel.TECHNICAL,
                    source_file="docs/architecture.md",
                    section_type="development",
                ),
            ]
            for section in sections:
                session.add(section)
            
            session.commit()
            click.echo(click.style("OK Created example project with 4 doc sections", fg="green"))
        else:
            click.echo("Use --example to create sample data")


@dev.command("test")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--coverage", "-c", is_flag=True, help="Run with coverage")
@click.option("--file", "-f", "test_file", help="Run specific test file")
@click.option("--keyword", "-k", help="Run tests matching keyword")
@click.option("--failed", "-x", is_flag=True, help="Stop on first failure")
def dev_test(
    verbose: bool,
    coverage: bool,
    test_file: Optional[str],
    keyword: Optional[str],
    failed: bool,
) -> None:
    """Run the test suite.
    
    Wrapper around pytest with common options.
    
    Examples:
        dossier dev test                    # Run all tests
        dossier dev test -v                 # Verbose output
        dossier dev test -c                 # With coverage report
        dossier dev test -f test_cli.py    # Run specific file
        dossier dev test -k "github"       # Match keyword
        dossier dev test -x                 # Stop on first failure
    """
    import subprocess
    import sys
    
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    if failed:
        cmd.append("-x")
    
    if coverage:
        cmd.extend(["--cov=dossier", "--cov-report=term-missing"])
    
    if keyword:
        cmd.extend(["-k", keyword])
    
    if test_file:
        # Allow both "test_cli.py" and "tests/test_cli.py"
        if not test_file.startswith("tests/"):
            test_file = f"tests/{test_file}"
        cmd.append(test_file)
    
    click.echo(f"Running: {' '.join(cmd)}")
    click.echo("-" * 60)
    
    result = subprocess.run(cmd)
    raise SystemExit(result.returncode)


@dev.command("purge")
@click.option("--pattern", "-p", default="test", help="Pattern to match project names")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be deleted")
def dev_purge(pattern: str, yes: bool, dry_run: bool) -> None:
    """Purge test/temporary projects from the database.
    
    Removes projects matching a pattern (default: 'test').
    Useful for cleaning up after test runs or development.
    
    Examples:
        dossier dev purge                   # Remove projects containing 'test'
        dossier dev purge -p "temp"        # Remove projects containing 'temp'
        dossier dev purge -n               # Dry run - show what would be deleted
        dossier dev purge -y               # Skip confirmation
    """
    with get_session() as session:
        # Find matching projects
        all_projects = session.exec(select(Project)).all()
        matches = [p for p in all_projects if pattern.lower() in p.name.lower()]
        
        if not matches:
            click.echo(f"No projects matching '{pattern}' found.")
            return
        
        click.echo(f"Found {len(matches)} projects matching '{pattern}':")
        for p in matches:
            synced = "🔄" if p.last_synced_at else "○"
            click.echo(f"  {synced} {p.name}")
        
        if dry_run:
            click.echo(click.style("\n(Dry run - no changes made)", fg="yellow"))
            return
        
        if not yes:
            click.confirm(
                click.style(f"\n⚠️  Delete {len(matches)} projects?", fg="yellow"),
                abort=True,
            )
        
        # Delete related data first
        for project in matches:
            # Delete related records
            session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            )
            for section in session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            ).all():
                session.delete(section)
            
            for lang in session.exec(
                select(ProjectLanguage).where(ProjectLanguage.project_id == project.id)
            ).all():
                session.delete(lang)
            
            for branch in session.exec(
                select(ProjectBranch).where(ProjectBranch.project_id == project.id)
            ).all():
                session.delete(branch)
            
            for dep in session.exec(
                select(ProjectDependency).where(ProjectDependency.project_id == project.id)
            ).all():
                session.delete(dep)
            
            for contrib in session.exec(
                select(ProjectContributor).where(ProjectContributor.project_id == project.id)
            ).all():
                session.delete(contrib)
            
            for issue in session.exec(
                select(ProjectIssue).where(ProjectIssue.project_id == project.id)
            ).all():
                session.delete(issue)
            
            for pr in session.exec(
                select(ProjectPullRequest).where(ProjectPullRequest.project_id == project.id)
            ).all():
                session.delete(pr)
            
            for release in session.exec(
                select(ProjectRelease).where(ProjectRelease.project_id == project.id)
            ).all():
                session.delete(release)
            
            # Delete component relationships
            for comp in session.exec(
                select(ProjectComponent).where(
                    (ProjectComponent.parent_id == project.id) |
                    (ProjectComponent.child_id == project.id)
                )
            ).all():
                session.delete(comp)
            
            session.delete(project)
        
        session.commit()
        click.echo(click.style(f"\nOK Purged {len(matches)} projects", fg="green"))


# =============================================================================
# Database Migrations Commands
# =============================================================================


@cli.group()
def db() -> None:
    """Database migration commands (Alembic).
    
    Manage database schema migrations for consistent updates.
    
    Examples:
        dossier db upgrade          Apply all pending migrations
        dossier db downgrade        Rollback one migration
        dossier db history          Show migration history
        dossier db current          Show current revision
        dossier db revision "msg"   Create new migration
    """
    pass


@db.command("upgrade")
@click.argument("revision", default="head")
def db_upgrade(revision: str) -> None:
    """Apply migrations up to a revision.
    
    REVISION is the target revision (default: head for latest).
    
    Examples:
        dossier db upgrade           # Apply all pending migrations
        dossier db upgrade head      # Same as above
        dossier db upgrade +1        # Apply next migration only
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = _alembic_config()
    click.echo(f"🔄 Upgrading database to {revision}...")
    
    try:
        command.upgrade(alembic_cfg, revision)
        click.echo(click.style("OK Database upgraded successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Migration failed: {e}", fg="red"))
        raise click.Abort()


@db.command("downgrade")
@click.argument("revision", default="-1")
def db_downgrade(revision: str) -> None:
    """Rollback migrations.
    
    REVISION is the target revision (default: -1 for previous).
    
    Examples:
        dossier db downgrade         # Rollback one migration
        dossier db downgrade -1      # Same as above
        dossier db downgrade base    # Rollback all migrations
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = _alembic_config()
    click.echo(f"🔄 Downgrading database to {revision}...")
    
    try:
        command.downgrade(alembic_cfg, revision)
        click.echo(click.style("OK Database downgraded successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Migration failed: {e}", fg="red"))
        raise click.Abort()


@db.command("current")
def db_current() -> None:
    """Show current database revision."""
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = _alembic_config()
    click.echo("📊 Current database revision:")
    command.current(alembic_cfg, verbose=True)


@db.command("history")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed history")
def db_history(verbose: bool) -> None:
    """Show migration history."""
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = _alembic_config()
    click.echo("📜 Migration history:")
    command.history(alembic_cfg, verbose=verbose)


@db.command("revision")
@click.argument("message")
@click.option("--autogenerate", "-a", is_flag=True, help="Auto-detect schema changes")
def db_revision(message: str, autogenerate: bool) -> None:
    """Create a new migration revision.
    
    MESSAGE is a short description of the migration.
    
    Examples:
        dossier db revision "add user table"
        dossier db revision "add index" -a   # Auto-detect changes
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = _alembic_config()
    click.echo(f"📝 Creating migration: {message}")
    
    try:
        command.revision(alembic_cfg, message=message, autogenerate=autogenerate)
        click.echo(click.style("OK Migration created successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create migration: {e}", fg="red"))
        raise click.Abort()


@db.command("stamp")
@click.argument("revision")
def db_stamp(revision: str) -> None:
    """Stamp database with revision without running migrations.
    
    Useful for marking an existing database as up-to-date.
    
    Examples:
        dossier db stamp head       # Mark as current
        dossier db stamp 001_init   # Mark specific revision
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = _alembic_config()
    click.echo(f"🔖 Stamping database with {revision}...")
    
    try:
        command.stamp(alembic_cfg, revision)
        click.echo(click.style("OK Database stamped successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Failed to stamp: {e}", fg="red"))
        raise click.Abort()


# =============================================================================
# Graph/Autolinker Commands
# =============================================================================


@cli.group("graph")
def graph_group() -> None:
    """Build and manage entity/link graphs.
    
    Automatically discover and link entities within projects to build
    a hierarchical graph of related projects.
    
    Entity Scoping:
      - Global: lang/*, pkg/* (same entity everywhere)
      - App-scoped: github/user/* (same user across all repos)
      - Repo-scoped: owner/repo/branch/*, owner/repo/issue/*, etc.
    
    Examples:
        dossier graph build owner/repo    Build graph for one project
        dossier graph build-all           Build graphs for all projects
        dossier graph stats               Show graph statistics
    """
    pass


@graph_group.command("build")
@click.argument("project_name")
@click.option("--no-contributors", is_flag=True, help="Skip contributors")
@click.option("--no-languages", is_flag=True, help="Skip languages")
@click.option("--no-dependencies", is_flag=True, help="Skip dependencies")
@click.option("--no-branches", is_flag=True, help="Skip branches")
@click.option("--no-issues", is_flag=True, help="Skip issues")
@click.option("--no-prs", is_flag=True, help="Skip pull requests")
@click.option("--no-versions", is_flag=True, help="Skip versions/releases")
@click.option("--no-docs", is_flag=True, help="Skip documentation")
@click.option("--max-contributors", default=10, help="Max contributors to link")
@click.option("--max-issues", default=50, help="Max issues to link")
@click.option("--max-prs", default=50, help="Max PRs to link")
def graph_build(
    project_name: str,
    no_contributors: bool,
    no_languages: bool,
    no_dependencies: bool,
    no_branches: bool,
    no_issues: bool,
    no_prs: bool,
    no_versions: bool,
    no_docs: bool,
    max_contributors: int,
    max_issues: int,
    max_prs: int,
) -> None:
    """Build entity graph for a project.
    
    PROJECT_NAME is the project to build graph for (e.g., owner/repo).
    
    This command discovers all entities (contributors, languages, dependencies,
    branches, issues, PRs, versions, docs) and creates linked project nodes
    for each, building a navigable entity graph.
    
    Examples:
        dossier graph build microsoft/vscode
        dossier graph build astral-sh/ruff --no-issues --no-prs
        dossier graph build myorg/myrepo --max-contributors 5
    """
    from dossier.parsers.autolinker import AutoLinker
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise click.Abort()
        
        click.echo(f"🔗 Building entity graph for {project_name}...")
        
        linker = AutoLinker(session)
        stats = linker.build_graph(
            project,
            include_contributors=not no_contributors,
            include_languages=not no_languages,
            include_dependencies=not no_dependencies,
            include_branches=not no_branches,
            include_issues=not no_issues,
            include_prs=not no_prs,
            include_versions=not no_versions,
            include_docs=not no_docs,
            max_contributors=max_contributors,
            max_issues=max_issues,
            max_prs=max_prs,
        )
        
        click.echo(f"\nOK Graph built successfully!")
        click.echo(f"  Projects: {stats.projects_created} created, {stats.projects_found} existing")
        click.echo(f"  Links: {stats.links_created} created, {stats.links_found} existing")
        
        if stats.errors:
            click.echo(click.style(f"\n⚠ {len(stats.errors)} errors occurred:", fg="yellow"))
            for error in stats.errors[:5]:
                click.echo(f"    • {error}")
            if len(stats.errors) > 5:
                click.echo(f"    ... and {len(stats.errors) - 5} more")


@graph_group.command("build-all")
@click.option("--no-contributors", is_flag=True, help="Skip contributors")
@click.option("--no-languages", is_flag=True, help="Skip languages")
@click.option("--no-dependencies", is_flag=True, help="Skip dependencies")
@click.option("--no-branches", is_flag=True, help="Skip branches")
@click.option("--no-issues", is_flag=True, help="Skip issues")
@click.option("--no-prs", is_flag=True, help="Skip pull requests")
@click.option("--no-versions", is_flag=True, help="Skip versions/releases")
@click.option("--no-docs", is_flag=True, help="Skip documentation")
@click.option("--max-contributors", default=10, help="Max contributors per project")
@click.option("--max-issues", default=50, help="Max issues per project")
@click.option("--max-prs", default=50, help="Max PRs per project")
def graph_build_all(
    no_contributors: bool,
    no_languages: bool,
    no_dependencies: bool,
    no_branches: bool,
    no_issues: bool,
    no_prs: bool,
    no_versions: bool,
    no_docs: bool,
    max_contributors: int,
    max_issues: int,
    max_prs: int,
) -> None:
    """Build entity graphs for all synced projects.
    
    This processes all projects with GitHub owner/repo info and builds
    their entity graphs, creating a fully-linked knowledge base.
    
    Examples:
        dossier graph build-all
        dossier graph build-all --no-issues --no-prs
        dossier graph build-all --max-contributors 5
    """
    from dossier.parsers.autolinker import AutoLinker
    
    with get_session() as session:
        # Count projects first
        projects = session.exec(
            select(Project).where(
                Project.github_owner.isnot(None),
                Project.github_repo.isnot(None),
            )
        ).all()
        
        if not projects:
            click.echo(click.style("No synced projects found", fg="yellow"))
            return
        
        click.echo(f"🔗 Building entity graphs for {len(projects)} projects...")
        
        linker = AutoLinker(session)
        total_stats = linker.build_all_graphs(
            include_contributors=not no_contributors,
            include_languages=not no_languages,
            include_dependencies=not no_dependencies,
            include_branches=not no_branches,
            include_issues=not no_issues,
            include_prs=not no_prs,
            include_versions=not no_versions,
            include_docs=not no_docs,
            max_contributors=max_contributors,
            max_issues=max_issues,
            max_prs=max_prs,
        )
        
        click.echo(f"\nOK All graphs built successfully!")
        click.echo(f"  Projects: {total_stats.projects_created} created, {total_stats.projects_found} existing")
        click.echo(f"  Links: {total_stats.links_created} created, {total_stats.links_found} existing")
        
        if total_stats.errors:
            click.echo(click.style(f"\n⚠ {len(total_stats.errors)} errors occurred", fg="yellow"))


@graph_group.command("stats")
def graph_stats() -> None:
    """Show graph statistics.
    
    Display counts of projects and links by type, showing the
    structure of the entity graph.
    """
    with get_session() as session:
        # Count projects by type
        all_projects = session.exec(select(Project)).all()
        
        # Categorize by prefix
        categories = {
            "GitHub Repos": 0,
            "Users (github/user/)": 0,
            "Languages (lang/)": 0,
            "Packages (pkg/)": 0,
            "Branches": 0,
            "Issues": 0,
            "PRs": 0,
            "Versions": 0,
            "Docs": 0,
            "Other": 0,
        }
        
        for p in all_projects:
            name = p.name
            if name.startswith("github/user/"):
                categories["Users (github/user/)"] += 1
            elif name.startswith("lang/"):
                categories["Languages (lang/)"] += 1
            elif name.startswith("pkg/"):
                categories["Packages (pkg/)"] += 1
            elif "/branch/" in name:
                categories["Branches"] += 1
            elif "/issue/" in name:
                categories["Issues"] += 1
            elif "/pr/" in name:
                categories["PRs"] += 1
            elif "/ver/" in name:
                categories["Versions"] += 1
            elif "/doc/" in name:
                categories["Docs"] += 1
            elif "/" in name and not any(x in name for x in ["/branch/", "/issue/", "/pr/", "/ver/", "/doc/"]):
                categories["GitHub Repos"] += 1
            else:
                categories["Other"] += 1
        
        # Count links by type
        links = session.exec(select(ProjectComponent)).all()
        link_types: dict[str, int] = {}
        for link in links:
            rel_type = link.relationship_type or "unknown"
            link_types[rel_type] = link_types.get(rel_type, 0) + 1
        
        click.echo("📊 Graph Statistics\n")
        click.echo("Projects by Type:")
        for cat, count in categories.items():
            if count > 0:
                click.echo(f"  {cat}: {count}")
        click.echo(f"  {'─' * 30}")
        click.echo(f"  Total: {len(all_projects)}")
        
        click.echo("\nLinks by Relationship:")
        for rel_type, count in sorted(link_types.items()):
            click.echo(f"  {rel_type}: {count}")
        click.echo(f"  {'─' * 30}")
        click.echo(f"  Total: {len(links)}")


# =============================================================================
# Dossier File Commands
# =============================================================================


@cli.group("export")
def export_group() -> None:
    """Export project data to various formats.
    
    Generate .dossier files, JSON exports, and other formats.
    
    Examples:
        dossier export dossier owner/repo
        dossier export dossier owner/repo -o project.dossier
        dossier export all --format json
    """
    pass


@export_group.command("dossier")
@click.argument("project_name")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--no-docs", is_flag=True, help="Exclude documentation overview")
@click.option("--no-activity", is_flag=True, help="Exclude activity metrics")
def export_dossier(
    project_name: str,
    output: Optional[str],
    no_docs: bool,
    no_activity: bool,
) -> None:
    """Export a project to .dossier format.
    
    PROJECT_NAME is the project to export (e.g., owner/repo).
    
    The .dossier format is a YAML-based file that provides a standardized
    overview of a project's metadata, tech stack, dependencies, and activity.
    
    Examples:
        dossier export dossier astral-sh/ruff
        dossier export dossier myproject -o myproject.dossier
    """
    from pathlib import Path
    from dossier.dossier_file import export_dossier_yaml
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise click.Abort()
        
        # Generate output path if not specified
        if output:
            output_path = Path(output)
        else:
            # Default to {repo_name}.dossier in current directory
            safe_name = project_name.replace("/", "_")
            output_path = Path(f"{safe_name}.dossier")
        
        # Generate the dossier
        from dossier.dossier_file import generate_dossier
        import yaml
        
        dossier = generate_dossier(
            session,
            project,
            include_docs=not no_docs,
            include_activity=not no_activity,
        )
        
        # Write to file
        yaml_content = yaml.dump(
            dossier,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        output_path.write_text(yaml_content, encoding="utf-8")
        
        click.echo(click.style(f"OK Exported to {output_path}", fg="green"))
        
        # Show summary
        click.echo(f"\n📄 {project.name}")
        if project.description:
            click.echo(f"   {project.description[:60]}...")
        if "tech_stack" in dossier:
            langs = ", ".join(t["name"] for t in dossier["tech_stack"][:3])
            click.echo(f"   Languages: {langs}")
        if "activity" in dossier:
            act = dossier["activity"]
            click.echo(f"   Activity: {act.get('open_issues', 0)} issues, {act.get('open_prs', 0)} PRs")


@export_group.command("all")
@click.option("--output-dir", "-d", type=click.Path(), default=".", help="Output directory")
@click.option("--format", "-f", type=click.Choice(["dossier", "json"]), default="dossier")
@click.option("--synced-only", is_flag=True, help="Only export synced projects")
def export_all(output_dir: str, format: str, synced_only: bool) -> None:
    """Export all projects.
    
    Creates one file per project in the output directory.
    
    Examples:
        dossier export all
        dossier export all -d ./exports
        dossier export all --format json
    """
    from pathlib import Path
    import json
    from dossier.dossier_file import generate_dossier
    import yaml
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    with get_session() as session:
        stmt = select(Project).order_by(Project.name)
        projects = session.exec(stmt).all()
        
        if synced_only:
            projects = [p for p in projects if p.last_synced_at]
        
        if not projects:
            click.echo("No projects to export")
            return
        
        click.echo(f"Exporting {len(projects)} projects to {output_path}/")
        
        for project in projects:
            safe_name = project.name.replace("/", "_")
            
            if format == "dossier":
                file_path = output_path / f"{safe_name}.dossier"
                dossier = generate_dossier(session, project)
                content = yaml.dump(
                    dossier,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            else:  # json
                file_path = output_path / f"{safe_name}.json"
                dossier = generate_dossier(session, project)
                content = json.dumps(dossier, indent=2, default=str)
            
            file_path.write_text(content, encoding="utf-8")
            click.echo(f"  OK {file_path.name}")
        
        click.echo(click.style(f"\nOK Exported {len(projects)} projects", fg="green"))


@export_group.command("show")
@click.argument("project_name")
def export_show(project_name: str) -> None:
    """Show project dossier without saving to file.
    
    Displays the .dossier format content to stdout.
    
    Examples:
        dossier export show astral-sh/ruff
        dossier export show myproject | less
    """
    from dossier.dossier_file import generate_dossier
    import yaml
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise click.Abort()
        
        dossier = generate_dossier(session, project)
        yaml_content = yaml.dump(
            dossier,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        
        click.echo(yaml_content)


# =============================================================================
# Test Command - Quick test runner
# =============================================================================


@cli.command("test")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--coverage", "-c", is_flag=True, help="Run with coverage")
@click.option("--file", "-f", "test_file", help="Run specific test file")
@click.option("--keyword", "-k", help="Run tests matching keyword")
@click.option("--failed", "-x", is_flag=True, help="Stop on first failure")
@click.option("--screenshots", is_flag=True, help="Generate TUI screenshots")
def test_cmd(
    verbose: bool,
    coverage: bool,
    test_file: Optional[str],
    keyword: Optional[str],
    failed: bool,
    screenshots: bool,
) -> None:
    """Run the test suite (quick by default).
    
    Runs pytest with sensible defaults for fast iteration.
    
    Examples:
        dossier test                    # Quick run, all tests
        dossier test -v                 # Verbose output
        dossier test -c                 # With coverage report
        dossier test -f test_cli.py    # Run specific file
        dossier test -k "github"       # Match keyword
        dossier test -x                 # Stop on first failure
        dossier test --screenshots      # Generate TUI screenshots
    """
    import subprocess
    import sys
    
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    if failed:
        cmd.append("-x")
    
    if coverage:
        cmd.extend(["--cov=dossier", "--cov-report=term-missing"])
    
    if keyword:
        cmd.extend(["-k", keyword])
    
    if screenshots:
        cmd.append("--screenshots")
    
    if test_file:
        # Allow both "test_cli.py" and "tests/test_cli.py"
        if not test_file.startswith("tests/"):
            test_file = f"tests/{test_file}"
        cmd.append(test_file)
    
    click.echo(f"Running: {' '.join(cmd)}")
    click.echo("-" * 60)
    
    result = subprocess.run(cmd)
    raise SystemExit(result.returncode)


@cli.command("init")
@click.argument("project_name", required=False)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def init_dossier(project_name: Optional[str], output: Optional[str]) -> None:
    """Initialize a new .dossier file.
    
    Creates a template .dossier file that can be edited manually.
    If PROJECT_NAME is provided, it will be used as the project name.
    
    Examples:
        dossier init                    # Create template
        dossier init myproject          # Create with name
        dossier init myproject -o .dossier
    """
    from pathlib import Path
    from dossier.dossier_file import create_dossier_from_scratch
    import yaml
    
    # Determine project name
    if not project_name:
        # Try to infer from current directory
        project_name = Path.cwd().name
    
    # Create template dossier
    dossier = create_dossier_from_scratch(
        name=project_name,
        description="TODO: Add project description",
        repository=None,
    )
    
    # Add template sections
    dossier["overview"] = {
        "summary": "TODO: Brief one-line summary",
        "purpose": "TODO: What does this project do?",
        "audience": "TODO: Who is this project for?",
    }
    
    dossier["tech_stack"] = [
        {"name": "TODO", "percentage": 100.0},
    ]
    
    dossier["dependencies"] = {
        "runtime": [
            {"name": "TODO", "version": "^1.0"},
        ],
    }
    
    dossier["links"] = {
        "documentation": "TODO",
        "repository": "TODO",
    }
    
    # Write to file
    output_path = Path(output) if output else Path(f"{project_name}.dossier")
    yaml_content = yaml.dump(
        dossier,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    output_path.write_text(yaml_content, encoding="utf-8")
    
    click.echo(click.style(f"OK Created {output_path}", fg="green"))
    click.echo(f"\nEdit the file to fill in project details:")
    click.echo(f"  {output_path}")


# =============================================================================
# View Command - Open docs in frogmouth viewer
# =============================================================================


def _check_frogmouth_installed() -> tuple[bool, str | None]:
    """Check if frogmouth is installed and return the path if found.
    
    Returns:
        Tuple of (is_installed, executable_path)
    """
    import shutil
    
    # First check if it's on PATH
    frogmouth_path = shutil.which("frogmouth")
    if frogmouth_path:
        return True, frogmouth_path
    
    # Try importing to see if it's installed as a Python package
    try:
        import frogmouth
        # It's installed but not on PATH - try to find the module location
        import importlib.util
        spec = importlib.util.find_spec("frogmouth")
        if spec and spec.origin:
            return True, f"python -m frogmouth"
        return True, None
    except ImportError:
        pass
    
    return False, None


@cli.command("view")
@click.argument("project_name")
@click.option("--section", "-s", help="Specific documentation section to view")
@click.option("--readme", "-r", is_flag=True, help="View README only")
@click.option("--export", "-e", is_flag=True, help="View exported .dossier file")
def view_cmd(
    project_name: str,
    section: Optional[str],
    readme: bool,
    export: bool,
) -> None:
    """Open project documentation in frogmouth viewer.
    
    Opens documentation in the frogmouth terminal markdown viewer.
    Requires frogmouth to be installed separately (due to dependency constraints).
    
    PROJECT_NAME: Name of the project (e.g., owner/repo)
    
    Examples:
        dossier view astral-sh/ruff              # View all docs
        dossier view astral-sh/ruff --readme     # View README only
        dossier view astral-sh/ruff -s "API"     # View specific section
        dossier view astral-sh/ruff --export     # View .dossier export
    """
    import tempfile
    import subprocess
    
    is_installed, frogmouth_cmd = _check_frogmouth_installed()
    if not is_installed:
        click.echo(click.style("frogmouth is not installed.", fg="yellow"))
        click.echo()
        click.echo("Install frogmouth using one of these methods:")
        click.echo(click.style("  pipx install frogmouth", fg="cyan") + "  (recommended - isolated install)")
        click.echo(click.style("  pip install frogmouth", fg="cyan") + "   (global install)")
        click.echo(click.style("  uv tool install frogmouth", fg="cyan") + "  (uv tool install)")
        click.echo()
        click.echo("Note: frogmouth is installed separately due to dependency version constraints.")
        raise SystemExit(1)
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise SystemExit(1)
        
        if export:
            # Generate and view .dossier file
            from dossier.dossier_file import generate_dossier
            import yaml
            
            dossier = generate_dossier(session, project)
            content = yaml.dump(
                dossier,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
            suffix = ".yaml"
        else:
            # Build markdown from documentation sections
            stmt = select(DocumentSection).where(
                DocumentSection.project_id == project.id
            ).order_by(DocumentSection.order)
            
            docs = session.exec(stmt).all()
            
            if section:
                docs = [d for d in docs if section.lower() in d.title.lower()]
            elif readme:
                docs = [d for d in docs if "readme" in (d.source_file or "").lower()]
            
            if not docs:
                click.echo(click.style(
                    f"No documentation found for '{project_name}'", fg="yellow"
                ))
                if section:
                    click.echo(f"  (searched for section matching '{section}')")
                raise SystemExit(1)
            
            # Build combined markdown
            content = f"# {project.name}\n\n"
            if project.description:
                content += f"> {project.description}\n\n"
            content += "---\n\n"
            
            for doc in docs:
                content += f"## {doc.title}\n\n"
                content += f"{doc.content}\n\n"
                content += "---\n\n"
            
            suffix = ".md"
        
        # Write to temp file and open in frogmouth
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            click.echo(f"Opening in frogmouth: {project_name}")
            subprocess.run(["frogmouth", temp_path], check=True)
        finally:
            # Clean up temp file
            import os
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@cli.group(name="governance")
def governance_group() -> None:
    """Read the corpus's generated governance documents.

    dossier renders these documents; it does not decide governance. They are
    generated in the corpus from git and the host, and nothing here writes
    back to them.

    Examples:
        dossier governance dashboard --corpus-dir ../qm --refresh
        dossier governance load       Read both documents into the store
        dossier governance show       Where every project stands
        dossier governance threads    What work is in flight, and where
    """
    _warn_if_run_outside_dossier()


def _warn_if_run_outside_dossier() -> None:
    """Say so when the store is being created somewhere unexpected.

    Every command calls `init_db()`, which creates `dossier.db` in the current
    directory. Run from the corpus checkout, that leaves a stray database in a
    repository it has nothing to do with, and the store is then separate from
    the one the dossier checkout uses -- so `load` here and `show` there
    disagree for a reason neither command mentions.

    A warning rather than an error: running from elsewhere with an explicit
    --corpus-dir does work, and the operator may mean it.
    """
    cwd = Path.cwd()
    if (cwd / "src" / "dossier").is_dir():
        return  # a dossier checkout, which is the expected place
    click.echo(
        click.style("note:", fg="yellow")
        + f" the store for this run is {cwd / 'dossier.db'}, which is per-directory."
        "\n      Running from elsewhere gets a different store, and the two will"
        " not agree.",
        err=True,
    )


@governance_group.command(name="load")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Where the corpus is mounted. Defaults to governance/qm.",
)
def governance_load(corpus_dir: Optional[Path]) -> None:
    """Read governance-status.yaml and harness-status.json into the store.

    A document that cannot be read is reported and leaves what it owns
    untouched, rather than emptying it. An empty table reads as "nothing is
    wrong", which is the one thing an unreadable document does not mean.
    """
    from dossier import governance as gov

    with get_session() as session:
        report = gov.load_documents(session, corpus_dir=corpus_dir)

    for label, outcome in (("governance", report.governance), ("harness", report.harness)):
        mark = "ok  " if outcome.loaded else "MISS"
        click.echo(f"{mark} {label:<11} {outcome.path}")
        click.echo(f"     {outcome.summary}")

    if report.threads:
        click.echo(f"     {report.threads} thread(s) in flight")
    if report.removed:
        click.echo(f"     removed: {', '.join(report.removed)}")

    if not report.anything_loaded:
        click.echo(
            "\nNeither document could be read, so nothing was changed. Anything "
            "already stored is still there and still carries its own age."
        )
        click.echo(
            "\nBoth documents are generated by the corpus's own ci/ and live at "
            "the corpus root. The vendored copy at governance/qm is pinned to\n"
            "this project's branch, which is cut from the corpus's main -- and "
            "they are not on main yet, so the default path is empty by\n"
            "construction rather than by accident."
        )
        click.echo(
            "\nPoint the loader at a corpus checkout that has them:\n"
            "    dossier governance load --corpus-dir ../qm\n"
            "\nThat checkout needs to be on a branch carrying ci/ and the two "
            "documents. To confirm before running:\n"
            "    ls <corpus>/governance-status.yaml <corpus>/harness-status.json\n"
            "\nThe default path starts working on its own once the corpus change "
            "adding them lands on main and this project's pin is bumped."
        )
        raise SystemExit(1)


@governance_group.command(name="show")
def governance_show() -> None:
    """Where every project stands: current, drifted, or unmeasured."""
    from dossier import governance as gov

    with get_session() as session:
        rows = gov.repositories(session)
        ages = gov.document_age(session)
        # The reverse link: which governed repositories this store has synced.
        synced = {}
        for row in rows:
            match, how = gov.project_for_repository(session, row)
            synced[row.name] = gov.coverage_text(match, how)

    if not rows:
        click.echo("Nothing stored. Run: dossier governance load")
        raise SystemExit(1)

    click.echo(_age_line("governance-status.yaml", ages["governance"], None))
    click.echo()

    header = (
        f"{'REPOSITORY':<25} {'PHASE':<8} {'CORPUS':<12} {'SEED':<7} "
        f"{'SLOT':<6} {'RELEASE':<22} {'IN DOSSIER':<14} EVIDENCE"
    )
    click.echo(header)
    click.echo("-" * len(header))
    for row in rows:
        state = gov.health(row)
        prefix = {"unknown": "?", "drift": "!", "ok": " "}[state]
        evidence = gov.show_pair(row.precondition, row.precondition_unknown)
        if row.precondition_missing:
            evidence = f"{evidence} ({row.precondition_missing})"
        if row.slot_violations:
            evidence = f"{evidence} [holds {row.slot_violations}]"
        click.echo(
            f"{prefix}{_fit(row.name, 24):<24} "
            f"{_fit(row.phase, 8):<8} "
            f"{gov.drift_text(row):<12} "
            f"{gov.show_pair(row.seed_drift, row.seed_drift_unknown):<7} "
            f"{gov.show_pair(row.slot_state, row.slot_unknown):<6} "
            f"{_fit(gov.release_text(row), 22):<22} "
            f"{_fit(synced.get(row.name), 14):<14} "
            f"{evidence}"
        )
    click.echo()
    click.echo("? unknown - nobody could measure it, which is not the same as compliant")
    click.echo("! drift   - behind the corpus, seed drift, or over the slot limit")
    click.echo("phase is a claim a human entered; evidence is what has landed")
    click.echo("in dossier - the project this store holds for it, if any")
    click.echo("release   - main is readiness; a v tag is governance passed")


@governance_group.command(name="threads")
def governance_threads() -> None:
    """Every line of work in flight, most idle first.

    Stages are observable states, not progress. Nothing here estimates
    completion: the corpus has no definition of done a tool could read.
    """
    from dossier import governance as gov

    with get_session() as session:
        rows = gov.threads(session)
        ages = gov.document_age(session)
        budget = next(
            (r.harness_staleness_budget_hours for r in gov.repositories(session)
             if r.harness_staleness_budget_hours),
            None,
        )

    if ages["harness"] is None:
        click.echo(
            "harness-status.json has never been read into this store, so nothing "
            "is known about work in flight.\nThat is not the same as nothing "
            "being in flight. Run: dossier governance load"
        )
        raise SystemExit(1)

    click.echo(_age_line("harness-status.json", ages["harness"], budget))
    click.echo()

    if not rows:
        click.echo("The document was read and reports no threads in flight.")
        return

    header = f"{'REPOSITORY':<16} {'THREAD':<38} {'STAGE':<15} {'DELTA':<22} {'IDLE':<8} PR"
    click.echo(header)
    click.echo("-" * len(header))
    for t in rows:
        stage = (t.stage or "-") + (" STALLED" if t.stalled else "")
        delta = (
            f"{t.commits or 0}c {t.changed_files or 0}f "
            f"+{t.additions or 0}/-{t.deletions or 0}"
        )
        idle = f"{t.idle_hours:.0f}h" if t.idle_hours is not None else "unknown"
        click.echo(
            f"{t.repository_name:<16} {_fit(t.name, 37):<38} {stage:<15} "
            f"{delta:<22} {idle:<8} {('#' + str(t.pr)) if t.pr else '-'}"
        )


@governance_group.command(name="dashboard")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to read. Found automatically when omitted: the "
    "current directory, then governance/qm, then ../qm.",
)
@click.option(
    "--refresh/--no-refresh",
    default=True,
    help="Regenerate both documents first, by running the corpus's own "
    "generators. On by default; reads the network and writes into the "
    "corpus checkout.",
)
@click.option(
    "--offline",
    is_flag=True,
    default=False,
    help="With a refresh, pass --offline to the governance generator.",
)
@click.option(
    "--no-load",
    is_flag=True,
    default=False,
    help="Open the view on what is already stored, reading no document.",
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Print both tables instead of launching the dashboard.",
)
def governance_dashboard(
    corpus_dir: Optional[Path],
    refresh: bool,
    offline: bool,
    no_load: bool,
    no_tui: bool,
) -> None:
    """Get the latest and open the dashboard, in one command.

    Refresh -> load -> launch, on the Governance tab.

    \b
    From a corpus checkout, or from a project that vendors one:
        dossier governance dashboard
        dossier governance dashboard --no-refresh      # read what is on disk
        dossier governance dashboard --corpus-dir ../qm

    \b
    The corpus is found automatically: the current directory, then
    governance/qm, then ../qm. Whichever wins is printed, because a resolution
    that stays silent is how a reader ends up looking at a different
    repository than the one they think they are.

    \b
    A refresh runs the corpus's own generators, so it queries the host for
    every repository in the org and rewrites two committed files in that
    checkout. That diff is yours to review. --no-refresh skips it and reads
    what is on disk; either way the view prints how old the documents are.
    """
    from dossier import corpus as corpus_tools
    from dossier import governance as gov

    root, why = gov.resolve_corpus_dir(corpus_dir)
    click.echo(f"corpus  {root}  ({why})")

    if refresh:
        blocked = corpus_tools.can_refresh(root)
        if blocked:
            click.echo(f"skip    refresh - {blocked}")
        else:
            click.echo("refresh running the corpus's own generators ...")
            for outcome in corpus_tools.refresh(root, offline=offline):
                mark = "ok  " if outcome.ok else ("skip" if not outcome.ran else "FAIL")
                click.echo(f"{mark}    {outcome.document:<24} {outcome.summary}")
                if outcome.output and not outcome.ok:
                    for line in outcome.output.splitlines():
                        click.echo(f"           {line}")
            click.echo(
                f"        two committed files in {root} now differ -- that diff "
                "is yours to review"
            )
    click.echo()

    if not no_load:
        with get_session() as session:
            report = gov.load_documents(session, corpus_dir=root)
        for label, outcome in (
            ("governance", report.governance),
            ("harness", report.harness),
        ):
            mark = "ok  " if outcome.loaded else "MISS"
            click.echo(f"{mark} {label:<11} {outcome.summary}")
        if report.threads:
            click.echo(f"     {report.threads} thread(s) in flight")

        if not report.anything_loaded:
            click.echo(
                f"\nNeither document could be read under {root}, so there is "
                "nothing new to show."
            )
            if corpus_dir is None:
                click.echo(
                    "Nothing was found in the current directory, in "
                    "governance/qm, or in ../qm. A project's vendored copy is\n"
                    "pinned to a branch cut from the corpus's main, and the "
                    "documents are not on main yet, so it is empty by\n"
                    "construction. Point at a corpus checkout that has them:\n"
                    "    dossier governance dashboard --corpus-dir <corpus>"
                )
            raise SystemExit(1)
        click.echo()

    if no_tui:
        ctx = click.get_current_context()
        ctx.invoke(governance_show)
        click.echo()
        ctx.invoke(governance_threads)
        return

    from dossier.tui import DossierApp

    DossierApp(initial_tab="tab-governance").run()


# =============================================================================
# Disk Commands - keeping the workstation off the floor
# =============================================================================


@cli.group(name="disk")
def disk_group() -> None:
    """Watch and reclaim disk space, through the corpus's own tooling.

    dossier measures nothing here and decides nothing. Every figure comes from
    the corpus's ci/disk_status.py, and every deletion is authorised by
    ci/disk-policy.yaml there -- a reviewed file, not a script.

    \b
    Examples:
        dossier disk check        Is anything under its floor? Writes nothing.
        dossier disk status       What is eating the disk, largest first
        dossier disk reclaim      What could be freed -- a dry run
        dossier disk cookbook     The recipes, where the work happens
    """
    _warn_if_run_outside_dossier()


def _disk_corpus(corpus_dir: Optional[Path]) -> Path:
    """Resolve the corpus and print the choice, or explain and exit.

    Resolution is `governance.resolve_corpus_dir` unchanged -- one definition of
    "where is the corpus", shared with the governance commands. What differs is
    what this group needs once it gets there, so the suitability check is
    `disk.can_measure` and its reason is printed rather than swallowed.
    """
    from dossier import disk as disk_tools
    from dossier import governance as gov

    root, why = gov.resolve_corpus_dir(corpus_dir)
    click.echo(f"corpus  {root}  ({why})")

    blocked = disk_tools.can_measure(root)
    if blocked:
        click.echo(f"\nThis checkout cannot run the disk tooling: {blocked}", err=True)
        if corpus_dir is None:
            click.echo(
                "\nNothing carrying ci/ was found in the current directory, in "
                "governance/qm, or in ../qm. A project's vendored copy is\n"
                "pinned to a branch cut from the corpus's main, and the disk "
                "tooling is not on main yet, so that path is empty by\n"
                "construction rather than by accident. Point at a corpus "
                "checkout that has it:\n"
                "    dossier disk status --corpus-dir <corpus>",
                err=True,
            )
        raise SystemExit(1)
    return root


@disk_group.command(name="check")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted: the "
    "current directory, then governance/qm, then ../qm.",
)
def disk_check(corpus_dir: Optional[Path]) -> None:
    """Is any volume under its floor? Fast, and writes nothing.

    \b
    The cheap call -- put it in front of anything that writes a lot:
        dossier disk check && make build

    \b
    The exit status is the corpus tool's, unmodified:
        2   a volume is critical
        1   a volume is low, or could not be read
        0   every volume measured is above both thresholds

    A volume nobody could measure exits 1 rather than 0, because an unreadable
    volume is not a volume with room on it.
    """
    from dossier import disk as disk_tools

    root = _disk_corpus(corpus_dir)
    outcome = disk_tools.check(root)
    if outcome.stdout:
        click.echo(outcome.stdout)
    if not outcome.ran or outcome.status is None:
        click.echo(f"FAIL    {outcome.summary}", err=True)
        raise SystemExit(1)
    raise SystemExit(outcome.status)


@disk_group.command(name="status")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--measure/--no-measure",
    default=True,
    help="Take a fresh measurement first. On by default; it is a filesystem "
    "walk, not a network call. --no-measure reads the document already there.",
)
@click.option(
    "--search-root",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Where this stack's clones live, for the sweeps that cross projects. "
    "Repeatable. Defaults to the corpus tool's own choice.",
)
@click.option(
    "--html",
    "as_html",
    is_flag=True,
    default=False,
    help="Write a self-contained page beside the document and print its path.",
)
def disk_status(
    corpus_dir: Optional[Path],
    measure: bool,
    search_root: tuple[Path, ...],
    as_html: bool,
) -> None:
    """Measure the disk and print what is eating it, largest first.

    \b
        dossier disk status
        dossier disk status --no-measure          # read what is on disk
        dossier disk status --html                # a page instead of a table

    \b
    The document lands in ~/.dossier/disk-status.json -- outside every
    repository, deliberately. Free space, cache sizes and paths under a home
    directory are one machine at one moment, so it is never committed
    anywhere, and this command refuses a destination inside a git repository
    rather than trusting anyone to remember.

    Every figure carries its own age and the corpus's staleness budget. A
    target that could not be measured is reported as unknown with its reason,
    never as a target with nothing in it.
    """
    from dossier import disk as disk_tools

    root = _disk_corpus(corpus_dir)
    document = disk_tools.document_path()

    if measure:
        click.echo("measure walking the policy's targets ...")
        outcome = disk_tools.measure(root, search_roots=search_root)
        if not outcome.ok:
            click.echo(f"FAIL    {outcome.summary}", err=True)
            if outcome.stdout:
                click.echo(outcome.stdout, err=True)
            raise SystemExit(1)
        click.echo(f"ok      {outcome.stdout or document}")
        click.echo()

    if as_html:
        page = document.with_suffix(".html")
        outcome = disk_tools.render(root, fmt="html", out=page)
        if not outcome.ok:
            click.echo(f"FAIL    {outcome.summary}", err=True)
            raise SystemExit(1)
        click.echo(f"page    {page}")
        return

    outcome = disk_tools.render(root, fmt="md")
    if not outcome.ok:
        click.echo(f"FAIL    {outcome.summary}", err=True)
        if not measure:
            click.echo(
                "\nNothing has been measured on this machine yet. Drop "
                "--no-measure to take a reading first.",
                err=True,
            )
        raise SystemExit(1)
    click.echo(outcome.stdout)


@disk_group.command(name="reclaim")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--apply",
    "apply_",
    is_flag=True,
    default=False,
    help="Actually delete. Without it nothing is removed and the plan is "
    "printed. There is no setting that changes this default.",
)
@click.option(
    "--allow",
    type=click.Choice(("refetched", "rebuilt", "destructive")),
    default="refetched",
    help="The most expensive tier permitted. Permits every cheaper tier too.",
)
@click.option(
    "--target",
    multiple=True,
    help="Run only this policy entry, by name. Repeatable. Names come from "
    "`dossier disk status`.",
)
@click.option(
    "--until-free",
    type=float,
    metavar="GB",
    help="Stop once the volume has this many GB free, rather than clearing "
    "every permitted target.",
)
@click.option(
    "--search-root",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Where this stack's clones live. Repeatable.",
)
def disk_reclaim(
    corpus_dir: Optional[Path],
    apply_: bool,
    allow: str,
    target: tuple[str, ...],
    until_free: Optional[float],
    search_root: tuple[Path, ...],
) -> None:
    """Free space, and print what it would take before it takes it.

    \b
        dossier disk reclaim                        # a dry run, always
        dossier disk reclaim --apply
        dossier disk reclaim --target uv-cache --apply
        dossier disk reclaim --allow rebuilt --apply

    \b
    Safety is the cost of getting the bytes back, not a guess at risk:
        refetched     the owning tool downloads it again, unprompted
        rebuilt       a command you run: an install, a build, a download
        destructive   nothing comes back

    \b
    The tiers are a ratchet. --allow rebuilt permits refetched as well, so
    there is no invocation that empties the recycle bin while sparing a
    download cache -- which is the shape every cleanup script grows into, one
    urgent afternoon at a time.

    The reclaimer does not read the measurement document. That document has a
    staleness budget and deletion has none, so it resolves the same policy
    against the filesystem now.
    """
    from dossier import disk as disk_tools
    from dossier import disk_store

    root = _disk_corpus(corpus_dir)

    with get_session() as session:
        record, outcome = disk_tools.reclaim_and_record(
            session,
            root,
            allow=allow,
            apply=apply_,
            targets=target,
            until_free=until_free,
            search_roots=search_root,
        )
        if outcome.stdout:
            click.echo(outcome.stdout)

        click.echo()
        click.echo(f"recorded run {record.id} [{record.outcome}]")

        # Claimed and freed are printed together, always, and the gap between
        # them is named rather than left for the reader to subtract. They
        # diverge for ordinary reasons -- a concurrent write, or space freed
        # inside a container disk that does not shrink -- and printing only the
        # first would let this tool claim space that never came back.
        click.echo(f"  claimed  {_size(record.claimed_bytes)}   (what the reclaimer removed)")
        if record.applied:
            if record.freed_bytes is None:
                click.echo(
                    f"  freed    unknown  ({record.freed_unknown or 'not measured'})"
                )
            elif record.freed_bytes < 0:
                # Not "gave back -37KB". The volume finished the run with less
                # space than it started, because something else was writing
                # throughout -- which is a true and useful thing to say, and
                # a negative number wearing the word `freed` is not.
                click.echo(
                    f"  freed    none — the volume ended "
                    f"{_size(abs(record.freed_bytes))} smaller than it started."
                    "\n           Something else was writing during the run; "
                    "what this removed still went."
                )
            else:
                click.echo(
                    f"  freed    {_size(record.freed_bytes)}   "
                    "(what the volume gave back)"
                )
                gap = (record.claimed_bytes or 0) - record.freed_bytes
                if record.claimed_bytes and abs(gap) > 10**9:
                    click.echo(
                        f"  gap      {_size(gap)} — the two disagree. Space freed "
                        "inside a container disk does not\n"
                        "           shrink the host file, and anything else "
                        "writing at the time counts too."
                    )
            delta = disk_store.reclaim_delta(session, record)
            if delta.available:
                shrank = [t for t in delta.targets if t.status == "shrank"]
                for target_change in sorted(shrank, key=lambda t: t.change or 0)[:8]:
                    click.echo(
                        f"    {_fit(target_change.name, 26):<26} "
                        f"{_change(target_change.change)}"
                    )
        else:
            click.echo("  freed    nothing — this was a dry run")

    if not outcome.ok:
        click.echo(f"FAIL    {outcome.summary}", err=True)
        raise SystemExit(outcome.status or 1)


def _size(count: Optional[int]) -> str:
    """Bytes at a scale a person reads, and never rounded to nothing.

    A 40MB cache rendered as `0.0GB` reads as empty, which is the same failure
    as rendering an unknown as a zero.
    """
    if count is None:
        return "unknown"
    negative = count < 0
    value = abs(count)
    if value >= 10**9:
        text = f"{value / 10**9:.1f}GB"
    elif value >= 10**6:
        text = f"{value / 10**6:.0f}MB"
    elif value >= 10**3:
        text = f"{value / 10**3:.0f}KB"
    else:
        text = f"{value}B"
    return f"-{text}" if negative else text


def _change(count: Optional[int]) -> str:
    """A signed change, with the sign kept even at zero-ish sizes."""
    if count is None:
        return "unknown"
    if count == 0:
        return "no change"
    return f"+{_size(count)}" if count > 0 else _size(count)


@disk_group.command(name="load")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--measure/--no-measure",
    default=True,
    help="Take a fresh reading first. On by default.",
)
@click.option(
    "--search-root",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Where this stack's clones live. Repeatable.",
)
@click.option(
    "--keep",
    type=int,
    default=None,
    help="Snapshots to keep for this machine. Older ones are pruned.",
)
def disk_load(
    corpus_dir: Optional[Path],
    measure: bool,
    search_root: tuple[Path, ...],
    keep: Optional[int],
) -> None:
    """Read a disk document into the store as a new snapshot.

    \b
        dossier disk load                  # measure, then store
        dossier disk load --no-measure     # store the reading already taken

    Appends rather than replaces, which is the difference between this and
    `governance load`. The question worth asking of a disk is what grew since
    last time, and no single reading can answer it -- so every load keeps the
    previous ones, and `dossier disk delta` compares them.

    Old snapshots are pruned per machine, so a second machine sharing a store
    cannot evict this one's history.
    """
    from dossier import disk as disk_tools
    from dossier import disk_store

    if measure:
        root = _disk_corpus(corpus_dir)
        click.echo("measure walking the policy's targets ...")
        outcome = disk_tools.measure(root, search_roots=search_root)
        if not outcome.ok:
            click.echo(f"FAIL    {outcome.summary}", err=True)
            raise SystemExit(1)
        click.echo(f"ok      {outcome.stdout or disk_tools.document_path()}")

    with get_session() as session:
        report = disk_store.load_document(
            session,
            keep=keep if keep is not None else disk_store.DEFAULT_KEEP,
        )

    mark = "ok  " if report.loaded else "MISS"
    click.echo(f"{mark} disk        {report.summary}")
    if not report.loaded:
        click.echo(
            "\nNothing was stored, and nothing already stored was changed. "
            "Take a reading first:\n    dossier disk load",
            err=True,
        )
        raise SystemExit(1)
    click.echo(f"     machine {report.machine}")
    if report.pruned:
        click.echo(f"     pruned {report.pruned} older snapshot(s)")


@disk_group.command(name="delta")
@click.option(
    "--machine",
    default=None,
    help="Which machine's history to read. Defaults to this one.",
)
@click.option(
    "--limit",
    type=int,
    default=12,
    help="How many changed targets to print.",
)
def disk_delta(machine: Optional[str], limit: int) -> None:
    """What changed between the two most recent readings.

    \b
        dossier disk delta

    The question a single reading cannot answer. Volumes first -- the change
    shown is in FREE space, so a negative number is the disk filling up --
    then the targets that moved, largest growth first.

    \b
    A change is only ever printed where subtracting was honest. Four cases
    print a word instead of a number, because the arithmetic would have
    invented a fact:
        unknown   nobody could measure one of the two readings
        new       the target is not in the earlier snapshot
        gone      the target is not in the later one
        different the two readings describe different machines

    One reading is not an error. It is a machine measured once, and the
    honest report is that there is nothing to compare it with yet.
    """
    from dossier import disk_store

    with get_session() as session:
        delta = disk_store.latest_delta(session, machine=machine)

        if not delta.available:
            click.echo(f"no delta: {delta.reason}")
            click.echo(
                "\nThis is not a claim that nothing changed -- it is the "
                "absence of a second measurement.\nRun `dossier disk load` "
                "again later, and the comparison becomes available."
            )
            return

        click.echo(
            f"machine {delta.machine}   over {delta.hours:.0f}h   "
            f"{delta.older.generated_at} -> {delta.newer.generated_at}"
        )
        click.echo()

        click.echo("Volumes (change in FREE space; negative is filling up)")
        header = f"  {'Volume':<12} {'Free now':>10} {'Change':>12}  State"
        click.echo(header)
        click.echo("  " + "-" * (len(header) - 2))
        for volume in delta.volumes:
            if volume.unknown:
                click.echo(
                    f"  {volume.path:<12} {'unknown':>10} {'unknown':>12}  "
                    f"{volume.unknown}"
                )
                continue
            click.echo(
                f"  {volume.path:<12} {_size(volume.after_free):>10} "
                f"{_change(volume.change):>12}  {volume.severity or '-'}"
            )
        click.echo()

        moved = [t for t in delta.targets if t.status in ("grew", "shrank")]
        moved.sort(key=lambda t: -(t.change or 0))
        click.echo("Targets that moved")
        if not moved:
            click.echo("  nothing measurable changed size")
        else:
            header = f"  {'Target':<28} {'Now':>10} {'Change':>12}  Safety"
            click.echo(header)
            click.echo("  " + "-" * (len(header) - 2))
            for target in moved[:limit]:
                click.echo(
                    f"  {_fit(target.name, 28):<28} {_size(target.after):>10} "
                    f"{_change(target.change):>12}  {target.safety or '-'}"
                )
            if len(moved) > limit:
                click.echo(f"  ... and {len(moved) - limit} more")

        # Never folded into the table above. A target nobody could compare is
        # not a target that did not change, and a row of dashes among real
        # numbers is read as the second thing.
        gaps = delta.unreadable
        if gaps:
            click.echo()
            click.echo(f"No change could be established for {len(gaps)} target(s):")
            for target in gaps:
                click.echo(f"  {target.name:<28} {target.status:<8} {target.unknown}")


@disk_group.command(name="reclaims")
@click.option(
    "--machine", default=None, help="Whose history. Defaults to this machine."
)
@click.option("--limit", type=int, default=15, help="How many, newest first.")
@click.option(
    "--compose",
    "compose_all",
    is_flag=True,
    default=False,
    help="Chain the listed runs into one delta over the whole span.",
)
def disk_reclaims(machine: Optional[str], limit: int, compose_all: bool) -> None:
    """What has been reclaimed here, and what actually came back.

    \b
        dossier disk reclaims
        dossier disk reclaims --compose      # the whole session as one delta

    Every run is stored as the pair of readings it sits between, so what it
    did is the same kind of fact as any other change and composes with them.

    \b
    Two columns that are not the same number, deliberately:
        claimed   what the reclaimer removed
        freed     what the volume gave back
    They diverge for ordinary reasons -- something else writing at the time,
    or space freed inside a container disk that does not shrink -- and a tool
    that printed only the first would claim space that never returned.
    """
    from dossier import disk_store

    with get_session() as session:
        rows = disk_store.reclaims(
            session, machine=machine or disk_store.this_machine(), limit=limit
        )
        if not rows:
            click.echo("No reclaim run has been recorded on this machine.")
            click.echo(
                "That is not a claim that nothing was ever cleaned up -- it is "
                "the absence of a record.\nRun `dossier disk reclaim --apply`."
            )
            return

        header = (
            f"{'#':>4}  {'when':<20} {'tier':<12} {'outcome':<9} "
            f"{'claimed':>10} {'freed':>10}"
        )
        click.echo(header)
        click.echo("-" * len(header))
        for row in rows:
            freed = (
                "dry run" if not row.applied
                else "unknown" if row.freed_bytes is None
                else _size(row.freed_bytes)
            )
            click.echo(
                f"{row.id:>4}  {row.started_at:%Y-%m-%d %H:%M:%S}  "
                f"{row.allow:<12} {row.outcome:<9} "
                f"{_size(row.claimed_bytes):>10} {freed:>10}"
            )
            if row.targets:
                click.echo(f"      targets: {row.targets}")

        if not compose_all:
            return

        # Composed from the endpoints, never by adding the rows up: an unknown
        # is not zero, so a sum would launder a run nobody measured into a
        # confident total.
        deltas = [disk_store.reclaim_delta(session, row) for row in rows]
        combined = disk_store.compose(session, *deltas)
        click.echo()
        if not combined.available:
            click.echo(f"composed: {combined.reason}")
            return
        click.echo(
            f"composed over {combined.hours:.0f}h, "
            f"{combined.older.generated_at} -> {combined.newer.generated_at}"
        )
        if not combined.contiguous:
            # Stated as the ordinary case it is, not as an anomaly. Each run
            # takes its own reading before it starts, so consecutive runs never
            # meet exactly -- the gap is the time between them. A warning that
            # fires every time is one people stop reading, and the fact worth
            # carrying is what the figure includes, not that something is off.
            click.echo(
                "  The runs are separated by the time between them, so this "
                "span also holds\n  ordinary drift. The total is what the "
                "volume did; not all of it is what the runs did."
            )
        for volume in combined.volumes:
            if volume.unknown:
                click.echo(f"  {volume.path:<10} unknown — {volume.unknown}")
                continue
            click.echo(
                f"  {volume.path:<10} free {_size(volume.after_free)}  "
                f"{_change(volume.change)}"
            )


@disk_group.command(name="dashboard")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--load/--no-load",
    "do_load",
    default=True,
    help="Measure and store a fresh reading first. On by default.",
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Print the delta instead of launching the dashboard.",
)
def disk_dashboard(
    corpus_dir: Optional[Path], do_load: bool, no_tui: bool
) -> None:
    """Get the latest and open the dashboard, in one command.

    \b
    Measure -> store -> launch, on the Disk tab:
        dossier disk dashboard
        dossier disk dashboard --no-load       # open on what is stored
        dossier disk dashboard --no-tui        # print instead

    Unlike the governance dashboard this reads no network and writes into no
    repository: a reading is a filesystem walk, and it lands in ~/.dossier.
    """
    ctx = click.get_current_context()

    if do_load:
        ctx.invoke(disk_load, corpus_dir=corpus_dir, measure=True)
        click.echo()

    if no_tui:
        ctx.invoke(disk_delta)
        return

    from dossier.tui import DossierApp

    DossierApp(initial_tab="tab-disk").run()


@disk_group.command(name="cookbook")
@click.option(
    "--markdown",
    "as_markdown",
    is_flag=True,
    default=False,
    help="Emit the docs page instead of the terminal view. Both are generated "
    "from the same recipes, so they cannot drift.",
)
@click.option(
    "--write",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the docs page here, as UTF-8 with LF endings and no byte order "
    "mark. Use this rather than a shell redirect.",
)
def disk_cookbook(as_markdown: bool, write: Optional[Path]) -> None:
    """The recipes, printed where the work happens.

    \b
        dossier disk cookbook
        dossier disk cookbook --write docs/disk.md

    docs/disk.md is generated from exactly these recipes, and tests/test_disk.py
    regenerates it and compares. A hand edit to that page fails the suite, which
    is the only reason it can be trusted after a flag changes.

    \b
    --write rather than `--markdown > docs/disk.md`, because PowerShell's
    redirect writes UTF-8 with a byte order mark. The page then differs from
    what this command produces on every other platform, and the drift test
    fails for a reason that has nothing to do with the recipes.
    """
    from dossier import disk as disk_tools

    if write is not None:
        write.write_text(disk_tools.cookbook_markdown(), encoding="utf-8", newline="\n")
        click.echo(f"wrote {write}")
        return

    if as_markdown:
        click.echo(disk_tools.cookbook_markdown(), nl=False)
        return

    click.echo(click.style("Disk - a cookbook", bold=True))
    click.echo(
        "Every command runs the corpus's own tooling. dossier measures nothing."
    )
    for recipe in disk_tools.COOKBOOK:
        click.echo()
        click.echo(click.style(recipe.task, fg="cyan"))
        click.echo(f"    {recipe.command}")
        for line in textwrap.wrap(recipe.when, width=74):
            click.echo(f"    {line}")
        if recipe.note:
            for line in textwrap.wrap(recipe.note, width=72):
                click.echo(f"      {line}")
    click.echo()
    click.echo("Full page: docs/disk.md")


def _fit(text: Optional[str], width: int) -> str:
    """Truncate to width so a long name cannot shunt every later column.

    `streaming-infrastructure` is 24 characters and broke the alignment of
    every row below it before this existed.
    """
    value = text or "-"
    return value if len(value) <= width else value[: width - 1] + "…"


def _age_line(name: str, age: Optional[float], budget: Optional[float]) -> str:
    """Say how old the document is, always, and never imply it is live."""
    if age is None:
        return f"{name}: never read into this store"
    text = f"{name}: generated {age:.0f}h ago"
    if budget is None:
        return f"{text} (the document states no staleness budget)"
    if age > budget:
        return f"{text} — PAST its {budget:.0f}h budget; treat every figure as stale"
    return f"{text}, within its {budget:.0f}h budget"


def main() -> None:
    """Entry point for the CLI."""
    cli()



# `backup` joins the existing `db` group defined above -- a second
# `@cli.group() def db()` silently replaced it, taking `db current`,
# `db history` and every other alembic route with it.
@db.command("backup")
@click.option("--to", "destination", type=click.Path(path_type=Path), default=None,
              help="Where to write it (default: beside the database, timestamped)")
def db_backup(destination: Optional[Path]) -> None:
    """Copy the database through SQLite's online backup API."""
    from dossier.maintenance import backup, timestamped_name

    source = Path("dossier.db")
    if not source.exists():
        click.echo(f"Error: {source} does not exist.", err=True)
        raise SystemExit(1)
    target = Path(destination) if destination else timestamped_name(source)
    backup(source, target)
    click.echo(f"Backed up {source} -> {target} ({target.stat().st_size:,} bytes)")


@projects.command("purge")
@click.option("--keep-owner", required=True,
              help="The only owner whose projects are kept")
@click.option("--apply", is_flag=True,
              help="Actually delete. Without this the plan is printed and nothing changes.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def projects_purge(keep_owner: str, apply: bool, yes: bool) -> None:
    """Remove every project not owned by KEEP-OWNER, and all of its rows.

    Prints the plan and exits unless --apply is given. A dry run walks exactly
    the same rows as a real one, so the plan is what the deletion does.
    """
    from dossier.maintenance import purge_other_owners

    with get_session() as session:
        plan = purge_other_owners(session, keep_owner, apply=False)
        if not plan.projects:
            click.echo(f"Nothing to purge: every project is owned by {keep_owner}.")
            return

        click.echo(f"Would remove {len(plan.projects)} project(s) not owned by "
                   f"{keep_owner}, and {plan.total_rows - len(plan.projects)} related row(s):")
        for table, count in sorted(plan.rows_by_table.items()):
            click.echo(f"  {table:24} {count:>6}")
        click.echo("  " + ", ".join(plan.projects[:12])
                   + (" ..." if len(plan.projects) > 12 else ""))

        if not apply:
            click.echo("\nDry run. Re-run with --apply to delete. "
                       "Back up first: dossier db backup")
            return
        if not yes:
            click.confirm(f"Delete {plan.total_rows} rows?", abort=True)

        done = purge_other_owners(session, keep_owner, apply=True)
        click.echo(f"Removed {len(done.projects)} project(s) and "
                   f"{done.total_rows - len(done.projects)} related row(s).")


@deltas.command("prune")
@click.option("--apply", is_flag=True, help="Actually delete. Without this nothing changes.")
def deltas_prune(apply: bool) -> None:
    """Remove deltas carrying no evidence of work.

    A stub has no description, no branch, no issue and no pull request -- a row
    somebody started and left, or one an old test wrote.
    """
    from dossier.maintenance import prune_stub_deltas

    with get_session() as session:
        names = prune_stub_deltas(session, apply=False)
        if not names:
            click.echo("No stub deltas.")
            return
        click.echo(f"{len(names)} stub delta(s): {', '.join(names)}")
        if not apply:
            click.echo("Dry run. Re-run with --apply to delete.")
            return
        prune_stub_deltas(session, apply=True)
        click.echo(f"Removed {len(names)} stub delta(s).")


@deltas.command("from-prs")
@click.option("--apply", is_flag=True, help="Actually write. Without this nothing changes.")
def deltas_from_prs(apply: bool) -> None:
    """Derive a delta from every open pull request.

    Identity is the project plus the PR number, so re-running updates rather
    than duplicating. A draft PR lands in implementation and a ready one in
    review, because draft means incomplete and nothing else.
    """
    from dossier.maintenance import deltas_from_pull_requests

    with get_session() as session:
        names = deltas_from_pull_requests(session, apply=False)
        if not names:
            click.echo("No open pull requests to derive from.")
            return
        click.echo(f"{len(names)} delta(s) from open pull requests.")
        if not apply:
            click.echo("Dry run. Re-run with --apply to write.")
            return
        deltas_from_pull_requests(session, apply=True)
        click.echo(f"Wrote {len(names)} delta(s).")


@deltas.command("prune-forks")
@click.option("--apply", is_flag=True, help="Actually delete. Without this nothing changes.")
def deltas_prune_forks(apply: bool) -> None:
    """Remove deltas belonging to forks.

    A fork's open pull requests are upstream's work. On a board they read
    exactly like the organisation's own.
    """
    from dossier.maintenance import prune_fork_deltas

    with get_session() as session:
        names = prune_fork_deltas(session, apply=False)
        if not names:
            click.echo("No deltas belong to forks.")
            return
        click.echo(f"{len(names)} delta(s) on forks: {', '.join(names[:10])}"
                   + (" ..." if len(names) > 10 else ""))
        if not apply:
            click.echo("Dry run. Re-run with --apply to delete.")
            return
        prune_fork_deltas(session, apply=True)
        click.echo(f"Removed {len(names)} delta(s).")


@db.command("health")
@click.option("--fix", is_flag=True,
              help="Apply the repairs this reports, backing up first")
def db_health(fix: bool) -> None:
    """Report what is wrong with this installation, and how to fix it."""
    from dossier.health import BLOCKED, check, render, repair, worst
    from dossier.health import candidate_databases

    findings = check()
    click.echo(render(findings))

    if not fix:
        if worst(findings) == BLOCKED:
            click.echo("\nRe-run with --fix to apply the repairs above.")
            raise SystemExit(1)
        return

    click.echo("")
    for path in candidate_databases():
        if not path.exists():
            continue
        for action in repair(path):
            click.echo(f"  {path.name}: {action}")
    click.echo("")
    click.echo(render(check()))


@cli.group()
def gates() -> None:
    """The governance checks, and how to run them before a pull request."""


@gates.command("list")
def gates_list() -> None:
    """Every gate, what it checks, and what it cannot see."""
    for gate in GATES:
        click.echo(f"{gate['name']}")
        click.echo(f"    runs:   {gate['command']}")
        click.echo(f"    checks: {gate['checks']}")
        click.echo(f"    misses: {gate['misses']}")
        click.echo("")


@gates.command("run")
@click.option("--base", default="main", help="Base branch, for the provenance check")
def gates_run(base: str) -> None:
    """Run every gate that can run locally, and report what could not.

    This is the route the corpus asks for: a project fork runs the seed scripts
    in place out of `governance/qm/project-seed/ci/`, and remembering four
    paths is how a check gets skipped. `uv run qm preflight` is the same idea in
    the corpus repository; this is its local equivalent.
    """
    import subprocess
    import sys

    from dossier.health import BLOCKED, check, render, worst

    failures: list[str] = []

    click.echo("== installation health")
    findings = check()
    click.echo(render(findings))
    if worst(findings) == BLOCKED:
        failures.append("health")

    for gate in GATES:
        if not gate.get("local"):
            click.echo(f"\n-- {gate['name']}: not runnable locally ({gate['misses']})")
            continue
        click.echo(f"\n== {gate['name']}")
        command = list(gate["argv"])
        if gate.get("takes_base"):
            command += ["--base", base, "--head", _current_branch()]
        if gate["name"] == "tests":
            # Captured, so the determinism claim can be checked against it. A
            # skipped test contributes nothing to that claim, and a fresh clone
            # once skipped two without anything saying so until a tag was
            # refused. Redirected rather than piped: a pipe would replace
            # pytest's exit code with the last command's.
            captured = Path("test-output.txt")
            with captured.open("w", encoding="utf-8") as sink:
                result = subprocess.run([sys.executable, *command],
                                        stdout=sink, stderr=subprocess.STDOUT)
            click.echo(captured.read_text(encoding="utf-8").strip().splitlines()[-1])
            if result.returncode != 0:
                failures.append(gate["name"])
            else:
                claims = subprocess.run(
                    [sys.executable,
                     f"{SEED}/check_tag_claims.py",
                     "--test-output", str(captured)])
                if claims.returncode != 0:
                    failures.append("determinism (a tag would be refused)")
            continue

        result = subprocess.run([sys.executable, *command])
        if result.returncode != 0:
            failures.append(gate["name"])

    click.echo("")
    if failures:
        click.echo(f"FAILED: {', '.join(failures)}")
        raise SystemExit(1)
    click.echo("Every gate that can run here passed. `uses:` steps and the "
               "runner image are not reproduced, so this is evidence, not proof.")


def _current_branch() -> str:
    import subprocess

    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True)
    return result.stdout.strip() or "HEAD"


SEED = "governance/qm/project-seed/ci"

GATES = (
    {
        "name": "tests",
        "command": "uv run pytest tests walkthrough",
        "argv": ["-m", "pytest", "tests", "walkthrough", "-q"],
        "checks": "every behaviour the suite asserts, and every walkthrough example",
        "misses": "anything nobody wrote a test for",
        "local": True,
    },
    {
        "name": "workflows",
        "command": f"python {SEED}/run_workflows_locally.py",
        "argv": [f"{SEED}/run_workflows_locally.py"],
        "checks": "the real steps of each workflow triggered by a pull request",
        "misses": "`uses:` steps and the runner image; tag-triggered workflows",
        "local": True,
    },
    {
        "name": "branch provenance",
        "command": f"python {SEED}/check_pr_base.py --base <base> --head <branch>",
        "argv": [f"{SEED}/check_pr_base.py"],
        "takes_base": True,
        "checks": "what the branch actually carries, and where it was cut from",
        "misses": "whether the changes are correct",
        "local": True,
    },
    {
        "name": "one open pull request",
        "command": f"python {SEED}/check_one_pr.py",
        "checks": "the one-PR-per-repository-per-contributor rule",
        "misses": "runs against the host, so it needs a pushed branch",
        "local": False,
    },
    {
        "name": "tag claims",
        "command": f"python {SEED}/check_tag_claims.py --all",
        "checks": "that a version tag is annotated and names its reviewer",
        "misses": "whether the review or the manual test actually happened",
        "local": False,
    },
)



@cli.group()
def harness() -> None:
    """What a harness reports about itself."""


@harness.command("ingest")
@click.argument("payload", type=click.Path(exists=True, path_type=Path))
@click.option("--write", is_flag=True, help="Apply it. Without this nothing changes.")
def harness_ingest(payload: Path, write: bool) -> None:
    """Read `qmcp dashboard --json` into this database.

    The address on every row is the join. Nothing here imports qmcp: what
    crosses is a schema.
    """
    from sqlmodel import select

    from dossier.harness import (
        asks_of,
        dropped_from_queue,
        invocations_of,
        load,
        plan,
        render,
        totals_of,
    )
    from dossier.models.harness import HarnessAsk, HarnessInvocation, HarnessSnapshot

    document = load(payload)

    with get_session() as session:
        def lookup(address: str):
            return session.exec(
                select(HarnessInvocation).where(HarnessInvocation.address == address)
            ).first()

        def lookup_ask(address: str):
            return session.exec(
                select(HarnessAsk).where(HarnessAsk.address == address)
            ).first()

        verdicts = plan(document, lookup, lookup_ask)
        click.echo(render(verdicts, written=write,
                          dropped=dropped_from_queue(document)))

        # A refusal exits non-zero whether or not --write was passed. It used
        # to exit 0, so a scheduled ingest of an unreadable harness printed the
        # refusal and reported success to whatever ran it -- a check that says
        # nothing was enforced while its caller records that it passed.
        if any(v.state == "refused" for v in verdicts):
            raise SystemExit(1)
        if not write:
            return

        totals = totals_of(document)
        session.add(HarnessSnapshot(
            project=document["project"],
            schema_version=document.get("schema", 1),
            database=document.get("database"),
            **totals,
        ))
        for row in invocations_of(document):
            existing = lookup(row["address"])
            target = existing or HarnessInvocation(
                address=row["address"], project=document["project"])
            target.tool_name = row.get("tool_name")
            target.status = row.get("status")
            target.duration_ms = row.get("duration_ms")
            target.error = row.get("error")
            target.ran_at = row.get("created_at")
            session.add(target)

        # The queue. Updated in place rather than appended: a question seen
        # twice is the same question, and its answer arriving is a change to
        # that row rather than a second one.
        for row in asks_of(document):
            existing = lookup_ask(row["address"])
            target = existing or HarnessAsk(
                address=row["address"], project=document["project"],
                request_id=row.get("id") or row["address"].rsplit("/", 1)[-1])
            target.request_type = row.get("request_type")
            target.prompt = row.get("prompt")
            options = row.get("options") or []
            target.options = "\n".join(str(option) for option in options) or None
            target.status = row.get("status")
            target.asked_at = row.get("created_at")
            target.answered_with = row.get("answered_with")
            target.answered_by = row.get("answered_by")
            target.answered_at = row.get("answered_at")
            session.add(target)

        session.commit()


# Last in the file, deliberately. Commands appended after this guard are not
# registered when the module is run as `python -m dossier.cli`: the guard calls
# through to the group at the point it appears, so anything defined below it
# does not exist yet. The failure is invisible through the console script,
# which imports the whole module before calling anything -- so `dossier db
# health` worked and `python -m dossier.cli db health` said "No such command".
if __name__ == "__main__":
    main()


@cli.command("topology")
@click.option("--kind", default="delegation",
              help="a topology from the harness's own vocabulary")
@click.option("--subject", default="",
              help="a project to read the thread archive for; wins over --kind")
@click.option("--level", default=2, type=click.IntRange(0, 2), show_default=True,
              help="the resolution the harness draws at, as the web window "
                   "offers it: 0 is the black box, 2 is the flows")
@click.option("--width", default=76, show_default=True,
              help="how wide to draw")
@click.option("--list", "listing", is_flag=True,
              help="every topology the harness offers, and exit")
def topology_command(kind: str, subject: str, level: int, width: int,
                     listing: bool) -> None:
    """Draw a harness topology in this terminal.

    **THE ROUTE THAT WAS MISSING.** `dossier.topology` could draw and was
    tested, and no command or tab reached it -- so this front end had a
    renderer nobody could run, which reads exactly like a finished feature.

    The harness decides what a topology is; this decides what it looks like
    here. An edge nobody measured is drawn `-?>` and never as a thin line: one
    is an absence of evidence and the other is evidence of absence, and a
    reader has to be able to tell.
    """
    from dossier import threads, topology as drawing

    if listing:
        found = threads.topologies()
        if not found:
            click.echo("the harness is not answering, so it cannot say what "
                       "it offers")
            click.echo("  uv run qm dashboard --start harness")
            raise SystemExit(1)
        for name in found:
            click.echo(name)
        return

    answer = threads.topology(kind=kind, subject=subject, level=level)
    if not answer.reachable:
        # Named, with the command that fixes it. A front end whose backend is
        # down is the ordinary case, not an exception.
        click.echo(answer.problem)
        if answer.remedy:
            click.echo(f"  {answer.remedy}")
        click.echo(f"  tried {answer.where}")
        raise SystemExit(1)

    # The flow, with each box carrying the address it names and the URL where
    # the code behind it is read -- the same two things the web window puts on
    # the same node.
    drawn = drawing.draw_flow(answer.payload, width=width, link=False)
    click.echo(drawn.text())

    unmeasured = sum(1 for line in drawn.lines if drawing.UNMEASURED in line)
    total = len(answer.payload.get("arrows", []))
    provenance = f" from the {answer.source}" if answer.source else ""
    if answer.surveyed:
        provenance += f", {answer.surveyed} thread(s) read"
    click.echo("")
    if unmeasured:
        click.echo(f"{total - unmeasured} of {total} edge(s) measured{provenance};"
                   f" the rest are drawn -?> because nobody looked")
    else:
        click.echo(f"every one of {total} edge(s) is measured{provenance}")

    if drawn.channels_dropped:
        click.echo(f"this window cannot carry: "
                   f"{', '.join(drawn.channels_dropped)}")
