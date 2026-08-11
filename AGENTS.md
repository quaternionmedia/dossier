# AGENTS.md

This project is governed by the Quaternion Media constitution, vendored at
`governance/qm` (a submodule pinned to this project's `project/dossier`
branch of that repo). If you are an AI coding agent opening this repo with
no other briefing, read this file fully before your first commit or edit.

## Before you do anything

1. Read `governance/qm/README.md` and `governance/qm/PRINCIPLES.md` in full
   — the namespaces/precedence rules and the charter. Both are short.
2. This project's own decision records live in `governance/qm/adr/` — inside
   the submodule, on this project's own branch, not at this repo's root — as
   `ADR-NNNN` (numbered locally, at ratification) or `DRAFT-*.md` before
   ratification. A human ratifies; you draft.
3. **Everything you produce arrives as a pull request.** Work on a branch and
   open a PR for human review — in this repo, and in the `governance/qm`
   submodule when you touch this project's records there. Never commit to,
   merge into, or push a shared branch directly, and never merge your own
   work, however small or mechanical the change looks. If you cannot open a
   PR, hand the branch back rather than merging it.
4. **Human-only contributorship applies to every commit you make here** (see
   `governance/qm/records/DRAFT-human-only-contributorship.md`): do not add
   yourself, your model name, or any co-author trailer naming an unmonitored
   address (e.g. a vendor `noreply@` address) to any commit. If your default
   tooling normally appends a `Co-Authored-By:` trailer, suppress it for
   this repo. Tool involvement is disclosed as a `Tools:` note where the
   artifact calls for one, never as a byline.
5. Follow the drafting-session handoff contract in
   `governance/qm/adr/README.md` before writing or amending any record.
6. A QM record may be tightened by this project's own records, never
   relaxed — see `governance/qm/README.md`'s "Namespaces and precedence."
7. Banned in any pre-ratification `DRAFT-*.md` record: "previously",
   "originally", "earlier draft", "re-review", "renumber", "retroactive",
   "supersedes the ... (stance|finding)", "corrected". Drafts are rewritten
   in place, not narrated. The ADR lint enforces this over prose only, so
   quoting the list in a code span is fine.

## One-time setup on a fresh clone (Windows)

`CLAUDE.md` and `.github/copilot-instructions.md` are real symlinks to this
file, not copies — POSIX checkouts resolve them with no setup. On Windows,
enable Developer Mode (Settings → For developers) and run `git config
core.symlinks true` once per clone, then `git checkout -- .` if the files
were already checked out before that. Skipping this doesn't break
anything — the files degrade to one-line pointers containing just the
target path — but it isn't the intended, tested experience; see the
IDE-integrated governance discovery record in `governance/qm/records/` for
what was actually verified.

The submodule is a clone of its own, and it does not inherit this setting.
Run `git config core.symlinks true` inside `governance/qm` too, then
`git -C governance/qm checkout -- .`, or the seed's own pointer files there
will read as one-line text stubs.

## Where this project stands against the constitution

`governance/qm/adr/DRAFT-constitution-adoption-scope.md` is this project's
adoption record. dossier predates its adoption of the corpus, so that record
carries a conflict table: what is known to conflict with an org record, what
compliance would look like, and how each row is pinned. Read it before
concluding this project complies with anything — enumeration is not a waiver,
and five of its rows are open.

Two of those rows constrain what you may decide here. The project's outbound
licence class and the name on its copyright are open questions for a human;
do not settle either in passing while editing licensing files.

<!-- Project-specific setup commands, test commands, and conventions belong
     below this line; this seed only carries the governance-discovery part. -->

## What dossier is

A documentation standardization tool that auto-parses project documentation
and provides different levels of information through consistent, data-modeled
queries.

It is also becoming the surface on which this org reads its own governance:
it renders `governance-status.yaml` and `harness-status.json` from the
corpus. It **renders** those documents and never writes back to them, and it
never re-derives a governance fact a document does not carry — that is a
change to the generator in the corpus, reviewed once. The adoption record's
scope clause is the binding statement of this.

## Tech stack

- **Package manager**: uv
- **API framework**: FastAPI
- **CLI framework**: Click + Trogon (TUI command explorer)
- **TUI dashboard**: Textual
- **ORM/models**: SQLModel
- **HTTP client**: httpx (with retry/rate limit handling)
- **Testing**: pytest, pytest-asyncio, respx

Textual, Trogon and the uv/hatchling toolchain sit outside the org's blessed
set; they are enumerated as open conflicts C2 and C3 in the adoption record,
and closing them needs an org-level record rather than a change here.

## Project structure

```
dossier/
├── governance/qm/          # the constitution, pinned to project/dossier
├── src/
│   └── dossier/
│       ├── cli.py          # Click CLI commands
│       ├── config.py       # Configuration management
│       ├── dossier_file.py # .dossier file format
│       ├── api/main.py     # FastAPI application
│       ├── models/schemas.py   # SQLModel data models
│       ├── parsers/
│       │   ├── base.py     # Documentation parsers
│       │   ├── github.py   # GitHub API client
│       │   └── autolinker.py   # Entity graph builder
│       └── tui/app.py      # Textual TUI dashboard
├── tests/
├── docs/
├── pyproject.toml
└── README.md
```

## Configuration

User settings are stored in `~/.dossier/config.json`:

```python
from dossier.config import DossierConfig

config = DossierConfig.load()  # Load or create defaults
config.theme = "nord"
config.save()  # Persist changes
```

| Setting | Default | Description |
|---------|---------|-------------|
| `theme` | `textual-dark` | TUI color theme |
| `default_tab` | `tab-dossier` | Tab on project select |
| `sync_batch_size` | `10` | Repos per sync batch |
| `sync_delay` | `1.0` | Seconds between batches |
| `export_format` | `yaml` | Export format (yaml/json) |

## Data models

Core models live in `schemas.py`:

- **Project** — main project entity with GitHub metadata and URL helpers
- **ProjectVersion** — semver-parsed releases with metadata
- **DocumentSection** — parsed documentation content with levels
- **ProjectComponent** — parent-child project relationships
- **ProjectLanguage** — language breakdown with file_extensions and encoding
- **ProjectBranch** — repository branches with commit info
- **ProjectDependency** — dependencies from pyproject.toml, package.json, etc.
- **ProjectContributor** — top contributors with commit counts
- **ProjectIssue** — issues with state, labels, and authors
- **ProjectPullRequest** — PRs with merge status, branches, and diff stats
- **ProjectRelease** — version releases with tags and prerelease status
- **Entity** — named entities for graph linking
- **Link** — relationships between entities

**`dossier github sync` is delete-and-repopulate.** It empties and rebuilds
`ProjectBranch`, `ProjectPullRequest`, `DocumentSection`, `ProjectIssue`,
`ProjectContributor`, `ProjectLanguage`, `ProjectDependency` and
`ProjectRelease` on every run. State written into any of those is destroyed
by the next sync, silently and completely, so governance state belongs in a
table sync does not touch.

## Governance commands

```sh
uv run dossier governance dashboard          # refresh, load, and open the tab
uv run dossier governance dashboard --no-refresh
```

Works from a corpus checkout or from a project that vendors one; the corpus is
found automatically and the choice is printed. Full reference, including the
one prep step and what every column means: **`docs/governance.md`**.

Three rules bind anything added here, and each exists because the obvious
alternative produces a table that looks right and is not:

- **Never write back to a document, and never re-derive a fact it does not
  carry.** Both are generated in the corpus. A fact this view wants and the
  document lacks is a change to the generator, reviewed once, so every reader
  gets it — not a computation here, which would be a second definition of a
  governance rule.
- **`{"unknown": "<reason>"}` is a value.** It means nobody could establish the
  fact, and says why. Render it as its own state, never as blank and never as
  the healthy value. A stated `null` is different again: `last_propagation:
  null` means *never propagated*, which is established.
- **Always show the document's age.** A dashboard that looks live and is three
  days old is worse than one that admits its age, because the first stops
  people checking.

Refreshing runs the corpus's generators, so it lives in `dossier/corpus.py`,
deliberately outside the read-and-render path — the corpus's rule is that a
renderer may not run a command. `tests/test_governance.py` asserts the word
`subprocess` appears in neither the parser, the read model, nor the
presentation module.

## Disk commands

```sh
uv run dossier disk check                 # is anything under its floor? writes nothing
uv run dossier disk status                # what is eating the disk, largest first
uv run dossier disk load                  # measure, and store it as a snapshot
uv run dossier disk delta                 # what grew since the reading before
uv run dossier disk dashboard             # load, then open the TUI on the Disk tab
uv run dossier disk reclaim               # what could be freed -- a dry run
uv run dossier disk reclaims --compose    # what past runs actually gave back
uv run dossier disk cookbook              # the recipes, at the terminal
```

On the Disk tab, **`x` plans a reclaim and `X` applies the plan** — two keys
rather than one with a confirmation dialog, because a dialog is one stray Enter
from deleting a hundred gigabytes and is the part people learn to dismiss. `X`
refuses without a plan from this session, and the dashboard reclaims at the
`refetched` tier only; widening belongs where somebody types the word.

The store side arrives in migration `006_disk` (`disk_snapshot`, `disk_volume`,
`disk_target`) and is served at `/disk/snapshots` and `/disk/delta`. On a
database any command has already touched, `db upgrade` aborts with *table
already exists* because `init_db` ran `create_all` first — `dossier db stamp
head`, the same wrinkle and fix as `005_governance`.

**These tables are append-only, and that is the one place this domain departs
from governance.** A governance load replaces what it read; the question worth
asking of a disk is what *grew*, and no single reading answers it. Snapshots
are pruned per machine so a second host sharing a store cannot evict this
one's history.

**A delta against an unknown is unknown, not zero.** This is where the
`{"unknown": "<reason>"}` convention is easiest to lose: subtracting a measured
40GB from a target nobody could read yields `-40GB`, a confident and specific
claim that 40GB was reclaimed. Four subtractions are refused and say which —
an unmeasured end, a target absent from the earlier snapshot (`new`), one
absent from the later (`gone`), and two snapshots describing different
machines. That last one is not hypothetical: docker went from unknown to
23.6GB between two real readings 70 seconds apart.

**A reclaim is a delta.** `007_reclaim` stores each run as the pair of readings
it sits between, so what it did is computed by the same arithmetic as any
observed change and composes with it — there is no second vocabulary for "what
the cleanup achieved", which would need its own unknown handling and would get
it wrong somewhere. Composition recomputes from the outermost readings rather
than summing the parts, because an unknown is not zero.

**`claimed` and `freed` are different facts and both are stored.** The
reclaimer reports what it removed; the volume reports what came back. They
diverge for ordinary reasons — something else writing, or space freed inside a
container disk that does not shrink — and a run whose volume ended *smaller* is
reported as that rather than as a negative `freed`. Both have happened here on
real runs.

The same three rules as the governance view bind anything added here, for the
same reason: **dossier measures no disk fact and authorises no deletion.** Every
figure comes from the corpus's `ci/disk_status.py` and every target from its
`ci/disk-policy.yaml` — a reviewed file, not a script. A figure this group wants
and the document lacks is a change to the corpus generator.

Two properties are worth not breaking, and `tests/test_disk.py` asserts both:

- **The measurement is never committed, in either repository.** It describes one
  machine at one moment. `dossier.disk.inside_a_repository` refuses a
  destination under any `.git`, because the corpus guards its own repo and
  dossier is a second one — a guard that stopped at the boundary would let the
  document land in whichever repo was not checking.
- **A dry run is the default on both sides.** `reclaim` passes `--apply` only
  when asked, and nothing in dossier's configuration changes that. The
  duplication of the corpus's own default is deliberate.

`docs/disk.md` is **generated** from `dossier.disk.COOKBOOK`; regenerate it with
`dossier disk cookbook --write docs/disk.md` (not a shell redirect — PowerShell
writes a BOM). Hand-editing the page fails the suite.

## Development commands

- `uv run dossier` — run CLI
- `uv run dossier dashboard` — launch Textual TUI dashboard
- `uv run dossier tui` — launch Trogon command explorer
- `uv run dossier serve --reload` — run API server
- `uv run dossier view owner/repo` — view docs in frogmouth (installed separately)
- `uv run dossier dev status` — show database stats
- `uv run dossier dev reset -y` — reset database (recreates schema)
- `uv run dossier dev purge -p "test" -y` — purge test projects from database
- `uv run pytest` — run tests

**Never bind a default port.** Other agent sessions run on this workstation
at the same time, in other repositories. `dossier serve` and anything else
listening picks a non-default port, and anything you measure gets asked what
it is — a 200 proves something is listening, not that it is yours.

## Optional dependencies

**frogmouth**: enhanced markdown viewing for `dossier view`. Install
separately due to dependency constraints — `uv tool install frogmouth`
(recommended, adds to PATH), `pipx install frogmouth`, or `pip install
frogmouth`.

## Testing

> **The suite purges the operator's real database.** `pytest_configure` in
> `tests/conftest.py` shells `dossier dev purge` against `./dossier.db`
> before the run, and `pytest_unconfigure` does it again after. On a machine
> with data you care about, that data is gone. Know this before running the
> suite.

- Tests use in-memory SQLite databases to avoid file creep
- Test fixtures are in `tests/conftest.py`
- **Name test projects with "test" in the name so they can be purged**
- Generate screenshots: `uv run pytest tests/test_tui.py --screenshots`
- A passing test is not evidence until it has been seen to fail. After
  writing a check, break the thing it names and confirm the check goes red.

## GitHub commands

- `uv run dossier github sync owner/repo` — sync single repo
- `uv run dossier github sync-user username` — sync all user repos
- `uv run dossier github sync-org orgname` — sync all org repos
- `uv run dossier github search "query"` — search repositories

## Export commands

- `uv run dossier export dossier owner/repo` — export .dossier file
- `uv run dossier export show owner/repo` — preview dossier (no save)
- `uv run dossier export all -d ./exports` — export all projects
- `uv run dossier init projectname` — create template .dossier file

## Graph commands (entity linking)

- `uv run dossier graph build owner/repo` — build entity graph for one project
- `uv run dossier graph build-all` — build graphs for all synced projects
- `uv run dossier graph stats` — show graph statistics

Entities are namespaced for disambiguation:

- **Global**: `lang/{language}`, `pkg/{package}` (same everywhere)
- **App-scoped**: `github/user/{username}` (same user across all repos)
- **Repo-scoped**: `{owner}/{repo}/branch/{name}`,
  `{owner}/{repo}/issue/{number}`, `{owner}/{repo}/pr/{number}`,
  `{owner}/{repo}/ver/v{version}`, `{owner}/{repo}/doc/{slug}`

## Database migration commands

- `uv run dossier db upgrade` — apply pending migrations
- `uv run dossier db downgrade` — rollback one migration
- `uv run dossier db current` — show current revision
- `uv run dossier db history` — show migration history
- `uv run dossier db revision "message"` — create new migration
- `uv run dossier db stamp head` — mark as current version

## Coding conventions

- Use type hints for all function signatures
- Follow PEP 8 style guidelines
- Use SQLModel for all data models
- Implement CLI commands as Click groups/commands
- Use FastAPI dependency injection for database sessions
- Use httpx for HTTP requests with proper error handling

## Running the governance gates

```sh
python governance/qm/project-seed/ci/run_workflows_locally.py
```

It executes the workflows' actual steps. It does not reproduce `uses:`
steps, the runner image, or secrets — say so when reporting, rather than
letting a local pass stand for a remote one.
