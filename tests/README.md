# The suite, and what each part is for

Four categories, because a flat directory of thirty files hid two things: which
tests were slow, and which ones were checking the system rather than a model of
it.

| directory | subject | speed |
|---|---|---|
| `core/` | parsing, syncing, the read models, the CLI surface | fast |
| `db/` | schema, migrations, health, maintenance | fast |
| `ui/` | the Textual app, the ring, the panels | medium |
| `e2e/` | the real console script, as a process, in an empty directory | slow |

`walkthrough/` at the repository root is executed by the same command and is
not a category here: its pages are the onboarding documentation, and they run
so they cannot drift.

## Why `e2e/` exists, and what it is allowed to do

Every failure reported against this project reached `main` with the suite
green. The reason is the same each time: the tests built their own fixtures and
patched their own internals, so they exercised a model of the system. The
database that broke was the one the CLI *chooses*, in the directory the person
happened to stand in, created by the startup path no unit test ran.

So `e2e/` runs the real console script as a subprocess in a directory with
nothing in it. **It patches nothing.** The only thing injected is
`DOSSIER_HOME`, so a run cannot touch the operator's own state — which is not a
convenience, it is the one isolation the category is permitted.

There are deliberately few of them. Their job is the class of failure that
exists only between the parts.

## Rules the failures produced

**Do not count directories to find a file.** `Path(__file__).parent.parent` is
a count of the distance between a test and the repository root; organising the
suite moved every test one level and broke tests that had nothing to do with
the change. Use the `repo_root` fixture, or `tests.structural.repo_root()`.

**Do not import one test file from another.** Shared builders go in a module
of their own — `tests/disk_documents.py` is the example. A fixture living in
whichever test file needed it first breaks the moment the suite is organised.

**Assert what a reader would see, not that the code ran.** A test that checked
`styles.background.a == 0` passed while the dashboard was completely hidden.
Where the subject is a rendered thing, read the render.

**A tolerated failure is a defect with a comment on it.** `assert exit_code in
[0, 1]` carried a note blaming the test environment for two months. The cause
was real: alembic binds `sys.stdout` as a default argument at import, so the
second command in one process wrote to the first one's closed stream.
