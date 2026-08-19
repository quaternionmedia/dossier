# 03 — Before a pull request

The corpus asks for the gates to be run locally before a pull request is called
ready, and for the report to say what ran, what failed, and what could not be
reproduced. In a project fork there is no `qm` CLI: the seed scripts run in
place out of `governance/qm/project-seed/ci/`.

Remembering four script paths is how a check gets skipped, so there is a route:

    uv run dossier gates list
    uv run dossier gates run

## What the gates are, and what each one misses

Every gate declares what it cannot see. A gate whose blind spot is unstated
reads as broader coverage than it has:

    >>> from dossier.cli import GATES
    >>> for gate in GATES:
    ...     print(f"{gate['name']}: {gate['misses']}")
    tests: anything nobody wrote a test for
    workflows: `uses:` steps and the runner image; tag-triggered workflows
    branch provenance: whether the changes are correct
    one open pull request: runs against the host, so it needs a pushed branch
    tag claims: whether the review or the manual test actually happened

Two of them cannot run locally at all, and say so rather than passing quietly:

    >>> [gate["name"] for gate in GATES if not gate.get("local")]
    ['one open pull request', 'tag claims']

Each names the command it runs, so the route adds no third description of the
gate that could disagree with the other two:

    >>> print(GATES[1]["command"])
    python governance/qm/project-seed/ci/run_workflows_locally.py

## Running them

    uv run dossier gates run

It runs the installation health check, the test suite, the workflow runner and
the branch provenance check, then reports. A local pass is evidence and not
proof: `uses:` steps and the runner image are not reproduced.

## What a tag asserts

`main` is not a claim. Merging into it is not a release, and a green pull
request asserts nothing about a human having looked.

A version tag asserts three things at the tagged commit: a human reviewed the
change set, a human manually tested it against its real runtime, and
deterministic automated validation passed. The third is mechanical and this
repository checks it — the captured test run must contain no skip, no rerun and
no retry, because a test that skips contributes nothing to the claim.

Comment lines are stripped before looking, because `tag-claims.yml` names the
flag in prose explaining that it does *not* run the tests — a scan that matched
the comment would report the gate as wired by the file that says it is not:

    >>> from dossier.health import project_root
    >>> def wires_the_check(path):
    ...     lines = path.read_text(encoding="utf-8").splitlines()
    ...     return any("--test-output" in line for line in lines
    ...                if not line.lstrip().startswith("#"))
    >>> wired = [path.name
    ...          for path in sorted((project_root() / ".github/workflows").glob("*.yml"))
    ...          if wires_the_check(path)]
    >>> wired
    ['tag-determinism.yml']

The other two are a human's word, recorded in the tag's annotation where a
reader can find it. Nothing here verifies that the review happened; what it
verifies is that somebody wrote down that it did, against their name.

## The one-pull-request rule

One open pull request per repository, per contributor. It is a sequencing
constraint rather than a bandwidth one: two pull requests that must merge in an
order are a puzzle, and a green one frees its own slot in minutes.
