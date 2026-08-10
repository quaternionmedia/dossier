# Governance Dashboard

Where every QM project stands against the constitution, and every line of work
in flight across the org — read from two documents the corpus generates.

dossier **renders** those documents. It does not decide governance, never
writes back to them, and never computes a governance fact they do not already
carry.

---

## Which repository do I run this in?

This is the question that wastes the most time, so it is first.

| Repository | What to run there |
|---|---|
| **dossier** | Everything on this page. `dossier governance …`, and the Governance tab in the dashboard. |
| **qm** (the corpus) | Nothing from this page — but qm renders its own documents: `python ci/harness_dashboard.py harness-status.json --format md` and `python ci/governance_render.py`. Those are the reference readers this view was built to replace. |
| **alfred, apothecary, any other project** | Nothing. The documents describe every project but are generated and stored only in the corpus, and dossier is the only reader. |

## Prep, once

### 1. A corpus checkout that actually has the documents

`governance-status.yaml` and `harness-status.json` sit at the corpus root. The
copy vendored at `governance/qm` is pinned to this project's own branch, which
is cut from the corpus's `main` — and **the documents are not on `main` yet**.
So the default path is empty by construction, and a bare `governance load`
fails on purpose rather than by accident.

Until that changes, point the loader at a corpus checkout on a branch that
carries them. Confirm before running:

```sh
ls ../qm/governance-status.yaml ../qm/harness-status.json
```

Both listed means that checkout works. Neither listed means it is on a branch
without them — the corpus branch adding `ci/` and the two documents has to be
checked out there.

Once the corpus change lands on `main` and this project's governance pin is
bumped past it, `--corpus-dir` stops being necessary and the default path
works.

### 2. Tell the database the new tables exist

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

### 3. On Windows, use UTF-8

Several commands print emoji, and a `cp1252` console raises
`UnicodeEncodeError` on them — `dossier db current` is one. Set the encoding
for the session:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

The `governance` commands are ASCII-only and do not need this, but the prep
step above does.

## Run it

```sh
dossier governance load --corpus-dir ../qm    # read both documents
dossier governance show                       # where every project stands
dossier governance threads                    # every line of work in flight
```

`load` reads; `show` and `threads` display what was read. Re-run `load` to pick
up regenerated documents — nothing polls, and nothing refreshes on its own.

For the dashboard, launch it and open the **Governance** tab:

```sh
dossier dashboard
```

The tab is org-wide, so it needs no project selected.

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
| `unavailable - the document is not at this path` | Prep step 1. The vendored pin does not carry the documents; pass `--corpus-dir`. |
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
