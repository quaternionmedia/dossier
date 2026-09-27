# The development loop

Iterating on dossier against a live harness means three processes on one
workstation, in three clones that cannot import each other. They agree by
convention — a port number written into two repositories, a database path
taken from the working directory — and a convention nobody checks is one that
has already drifted. It has: the panel looked on 8000 while the harness
served 3333, and the message said the thread archive was absent.

`dossier dev doctor` is the preflight. It reports what is missing by name and
exits non-zero, so a loop that cannot work says so before any work is done in
it rather than partway through.

## What the three are

| Role | Clone | Serves | Needed for |
|---|---|---|---|
| harness | `../qmcp` | `QMCP Server` | everything: `dossier harness ingest\|queue\|answer\|goal` |
| speech | `../joe` | `Joe API` | answering the harness queue by voice |
| panel | here | `Dossier API` | reading dossier over HTTP rather than in the terminal |

Only the harness is required. A doctor that reported a working setup as
broken because an optional process was down would be one nobody runs.

## The ports, and why they are these

`src/dossier/threads.py` declares the allocation, once, and everything else
reads it from there:

| What | Port | Moved by |
|---|---|---|
| harness | 3141 | `DOSSIER_HARNESS_PORT` |
| panel | 1618 | `DOSSIER_PORT` |
| maps | 2718 | `CODECARTO_PORT` |
| speech | 8000 | `JOE_PORT` |

Other sessions run on this workstation at the same time. Each variable moves
one process, so a second loop can be stood up beside the first without either
touching the other's ports — and `dossier dev doctor` prints what each
resolved to, so a moved port is visible rather than inferred.

Speech is on 8000 and the other three are not, which is deliberate: 8000 is
the port anything grabs, and it is the one the historical collision was
about. It is the first place to move when two loops are running.

## Asking what is listening

A 200 proves a server is there. It does not prove it is yours.

All three serve FastAPI and answer a health path identically, so the doctor
identifies each by its OpenAPI `info.title` — `QMCP Server`, `Joe API`,
`Dossier API`. A service answering on another's port is reported as `WRONG`
rather than as a pass, which is the case a reachability check cannot see and
the one that cost an afternoon.

## The database

The suite purges pattern-matching projects from whatever database the CLI
resolves, before and after every run — see the testing section of
`AGENTS.md`. Iterating means running the suite repeatedly, so a loop pointed
at the working database is not an unlikely accident; it is the normal path.

Point it somewhere else first:

```bash
export DOSSIER_DATABASE_URL="sqlite:///$PWD/dev.db"
```

The purge runs as a subprocess that inherits the environment, so this is
honoured. `dossier dev doctor` fails when it is unset and a real database is
present, and says how many project rows are at stake.

## Standing it up

Three terminals, plus the preflight:

```bash
# 1, in ../qmcp
uv run qmcp serve

# 2, in ../joe  — only for the voice path
uv run joe backend

# 3, here
export DOSSIER_DATABASE_URL="sqlite:///$PWD/dev.db"
uv run dossier dev doctor        # says what is missing, by name
uv run dossier harness queue     # what is waiting on a person
```

`dossier dev doctor --no-static` skips the checks that read source and need
nothing running, when only the wiring is in question.

## What it does not check

- **That the harness has anything in it.** A reachable, correctly identified,
  empty queue passes.
- **That speech works.** The doctor asks joe what it is, not whether it can
  hear. `vox doctor`, in the vox clone, checks a microphone and synthesis.
- **Whether a port is held by a process outside this loop.** A service on a
  port that answers nothing on `/openapi.json` is reported as not listening,
  which is true of the loop and understates what is going on there.
