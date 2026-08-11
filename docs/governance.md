# Governance Dashboard

Where every QM project stands against the constitution, and every line of work
in flight across the org — read from two documents the corpus generates.

dossier **renders** those documents. It does not decide governance, never
writes back to them, and never computes a governance fact they do not already
carry.

---

## Which repository do I run this in?

This is the question that wastes the most time, so it is first.

| Repository | What works there |
|---|---|
| **qm** (the corpus) | `dossier governance dashboard` with no flags — the documents are at the root, so the current directory wins. qm also renders them itself, with `python ci/harness_dashboard.py harness-status.json --format md` and `python ci/governance_render.py`. |
| **dossier** | The same command; resolution falls through to `../qm`. This is where the code lives and where its store belongs. |
| **any other project** | Only with `--corpus-dir` pointing at a corpus checkout. Nothing is generated or stored in a project, so there is nothing local to read. |

The store is `./dossier.db`, **per directory**. Run from two places and you get
two stores that will not agree; the command prints a note when the current
directory is not a dossier checkout.

## Where it finds the corpus

Both documents sit at the corpus root. With no `--corpus-dir`, three places are
tried in order and **the winner is printed**, because a resolution that stays
silent is how a reader ends up looking at a different repository than the one
they think they are:

1. the current directory — so this works with no flags from a corpus checkout
2. `governance/qm` — a project's vendored copy
3. `../qm` — a corpus checked out beside this one

A candidate carrying the documents beats one that merely looks like a corpus.

**A project's vendored copy does not carry them yet.** It is pinned to that
project's branch, cut from the corpus's `main`, and the documents are not on
`main` — so from a project checkout resolution normally falls through to `../qm`.
Once the corpus change adding them lands on `main` and the pin is bumped past
it, the vendored copy starts winning on its own.

To check a specific checkout by hand:

```sh
ls <corpus>/governance-status.yaml <corpus>/harness-status.json
```

## Prep, once

### Tell the database the new tables exist

The governance tables arrive in migration `005_governance`. There is a wrinkle:
every `dossier` command calls `init_db()`, which runs `create_all` and creates
any missing table **before** your subcommand runs. On a database that predates
this feature, the tables therefore already exist by the time you could run a
migration, and `dossier db upgrade` aborts with *table already exists*.

Stamp instead. It records the revision without re-running the DDL that
`create_all` has already applied:

```sh
dossier db stamp head
```

Confirm:

```sh
dossier db current      # expect 005_governance
```

Skip this on a database created after this feature landed — `create_all` builds
the tables and the stamp is the only thing missing, so running it anyway is
harmless and idempotent.

### On Windows, use UTF-8

Several commands print emoji, and a `cp1252` console raises
`UnicodeEncodeError` on them — `dossier db current` is one. Set the encoding
for the session:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

The `governance` commands are ASCII-only and do not need this, but the prep
step above does.

## Run it

One command does refresh → load → launch, opening on the Governance tab:

```sh
dossier governance dashboard
```

| Flag | Does |
|---|---|
| *(none)* | Find the corpus, regenerate both documents, load them, open the tab |
| `--no-refresh` | Skip the regeneration and read what is on disk. Instant, and the view still prints the documents' age, so it never hides staleness. |
| `--corpus-dir PATH` | Read a specific checkout instead of searching |
| `--offline` | Pass `--offline` to the governance generator during a refresh |
| `--no-load` | Open on what is already stored, reading no document |
| `--no-tui` | Print both tables instead of launching. Useful in a pipe or over ssh. |

**A refresh writes.** It runs the corpus's generators, which query the host for
every repository in the org — around 36 seconds across 109 — and rewrite two
committed files in that checkout. The command says so and names the directory;
that diff is yours to review and commit. Reach for `--no-refresh` when you only
want to look, or when you are offline.

A checkout without the generators cannot be refreshed — a project's vendored
copy has no `ci/` at all — and the command reports that as a skip and carries on
to the load, rather than failing.

### The same steps separately

Sometimes you want one of them:

```sh
dossier governance load       # read both documents into the store
dossier governance show       # where every project stands
dossier governance threads    # every line of work in flight
dossier dashboard             # then pick the Governance tab
```

`load` never refreshes — it reads what is on disk. Refreshing is the corpus's
own act, and `governance dashboard --refresh` is the only thing here that
triggers it.

Nothing polls and nothing refreshes on its own. The Governance tab is org-wide,
so it needs no project selected.

## How this links to the rest of dossier

The governance rows and dossier's own `Project` rows are stored independently,
and joined **at read time** on names — never as a stored foreign key. That is
deliberate: `github sync` empties and rebuilds the project tables on every run,
so a key pointing at them would take governance state with it.

The join is visible in both directions:

| Direction | Where | Shows |
|---|---|---|
| project → org | **Details** tab, per project | that project's phase, drift, evidence, slot and propagation, or that the corpus does not govern it |
| org → project | **IN DOSSIER** column, `governance show` and the Governance tab | whether this store has synced that repository at all |
| thread → PR | PR column in the threads table | dimmed when the store has not synced that pull request |

Matching is ranked, strongest first, and a weak match says so:

1. `slug` — `quaternionmedia/alfred`, an identity: one repository on one host
2. `repo name` — the project's `github_repo`
3. `name` — a bare name, safe inside one org and not across two
4. `trailing name` — the last segment of an `owner/repo` name

Anything below `slug` is rendered with the rule that made it, because a link and
a guess presented as a link are different things. `synced (name)` in the
coverage column, and "matched to this project by name, not by slug" in the
Details block.

**`not synced` is not a problem.** It means nobody has looked at that repository
in dossier — worth seeing beside its governance state, since an ungoverned
project nobody has synced is exactly the one that stays invisible.

## Reading the output

### `governance show`

```
 REPOSITORY               PHASE    CORPUS       SEED    SLOT   EVIDENCE
 qm                       n/a      -            -       ok     n/a
!alfred                   v0.0.1   62 behind    drift   ok     incomplete (submodule, ide, workflows, licensing)
?benchmark                v0.0.2   -            -       ok     unknown
```

| Column | Means |
|---|---|
| `!` | drift — behind the corpus, seed drift, or over the pull-request slot limit |
| `?` | unknown — nobody could measure it, which is **not** the same as compliant |
| PHASE | what a human entered in the corpus's roster. A claim, never evidence. |
| CORPUS | commits behind the corpus, or `current` |
| SEED | whether the project's `adr/` seed matches the corpus's |
| SLOT | `ok`, `over`, or `unknown` against one-open-PR-per-contributor |
| RELEASE | what a `v` tag asserts, beside what the default branch carries past it |
| EVIDENCE | what has actually landed on the project's default branch |

The gap between PHASE and EVIDENCE is the point of putting them side by side.

### `governance threads`

Every branch with work on it, most idle first so stalled work surfaces:

```
REPOSITORY       THREAD                     STAGE           DELTA               IDLE   PR
alfred           config                     ready STALLED   9c 10f +58/-44      22874h #113
qm               evolve/ci-tooling-fixes    draft           17c 60f +10490/-60  1h     #36
```

Stages are `local`, `pushed`, `draft`, `ready` — **observable states, not
progress**. Nothing here estimates completion: the corpus has no definition of
done a tool could read, and a percentage would be the most confidently wrong
thing this view could print.

### `main` is readiness; a `v` tag is governance

Merging asserts the work is ready to build on, and nothing more. A `v` tag
asserts what the version-tags record requires: a human reviewed it, a human
manually tested it against its real runtime, and its automated gate passed and
is deterministic. The RELEASE column is the gap between them.

| Reads | Means |
|---|---|
| `never tagged` | no `v` tag has ever existed; nothing has ever been asserted |
| `v0.2.0` | tagged, annotated, and the branch carries nothing beyond it |
| `v0.2.0 +37` | 37 commits of readiness waiting on governance |
| `v0.0.1 lightweight` | the tag carries no annotation, so it names neither the reviewer nor the manual test — a claim with nothing behind it |
| `unknown` | the tags could not be read, with the reason kept |

`never tagged` and a bare version both have nothing outstanding and mean
opposite things, so one is never rendered as the other.

### Three states that are deliberately not blank

- **`unknown`** is a value. It means the fact could not be established, and the
  document says why. Never read it as zero, empty, or compliant.
- **`-`** is a stated null: established, and the answer is nothing.
  `last_propagation` null means *never propagated*.
- **Age is always shown.** Every view prints how old its document is, and says
  when it is past the document's own staleness budget. A dashboard that looks
  live and is three days old is worse than one that admits its age, because the
  first stops people checking.

## When something looks wrong

| Symptom | Cause |
|---|---|
| `Nothing stored. Run: dossier governance load` — **and a new `dossier.db` appeared next to you** | You are in the wrong repository. Every command calls `init_db()`, which creates an empty `dossier.db` in the *current directory* before the subcommand runs, so running `dossier` in the corpus or in another project silently makes an empty database there and then truthfully reports it as empty. `cd` to the dossier checkout and delete the stray. This has already cost one person three repositories' worth of attempts. |
| `unavailable - the document is not at this path` | Nothing was found in any of the three search places. Pass `--corpus-dir` pointing at a corpus checkout that has them. |
| `skip refresh - ... nothing here to run` | That checkout has no `ci/`, so there are no generators to run. Expected for a project's vendored copy; the load still happens. |
| `no such column: governance_repository.…` | A database built by an older version of this feature. `dossier db stamp head` does not add columns — delete the local `dossier.db` and re-sync, or add the column by hand. |
| `Nothing stored. Run: dossier governance load` | `show` before `load`. |
| `harness-status.json has never been read` | Only one of the two documents loaded. This is distinct from "no threads in flight", and the message says which. |
| `UnicodeEncodeError` | Prep step 3. |
| A figure disagrees with the corpus | Compare against `ci/harness_dashboard.py --format md` in the corpus. The documents are the shared input, so a genuine disagreement is a bug in one reader — report which figure and which document `generated_at`. |

## What this view must never do

Three rules bind anything added here. Each exists because the obvious
alternative produces a table that looks right and is not.

1. **Never write back to a document.** They are generated. A renderer that
   edits its own input creates a second source of truth for the same fact.
2. **Never re-derive a governance fact.** A fact this view wants and the
   document lacks is a change to the generator in the corpus — reviewed once,
   so every reader gets it — not a computation here, which would be a second
   definition of a governance rule that can disagree with the first.
3. **Never render unknown as blank, and never as the healthy value.** A project
   nobody could measure must not look like a project measured and found
   compliant. This is the failure mode the whole design is written against.
