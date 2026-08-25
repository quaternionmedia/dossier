"""Project and git workflows, as recipes somebody can run.

**EVERY ONE OF THESE HAS A HUMAN IN IT, AND THE RECIPE SAYS WHERE.** That is the
whole shape: a workflow that could run unattended end to end would not need
writing down, and one whose human step is implicit is how a person ends up
approving nine things having read seven. So a `Step` is either a command or a
gate, the gate carries what the person is deciding, and a workflow with no gate
at all has to say why -- `test_every_workflow_says_where_the_person_is`.

**AND THEY COMPOSE.** Each names what it follows and what it feeds, because the
common failure is not getting one workflow wrong; it is doing three in the wrong
order -- pushing a branch onto a pull request's base, which merges it, and then
closing the pull request into a silent no-op.

WHAT THIS IS NOT. Automation. Nothing here runs a workflow for you: the page and
`dossier cookbook` print them, and a person types them. A runner would have to
decide what to do at each gate, and deciding at the gate is the one thing the
gate is for.

WHAT THIS CANNOT DO. Know whether a step is safe *here*. The commands are the
ones this organisation uses, and the corpus they belong to is the authority on
what they mean -- `governance/qm/handbook/async-contract.md` and the records
under `governance/qm/records/`. Where a recipe restates a rule, it names the
document, so the two can be checked against each other rather than drifting.
"""

from __future__ import annotations

from dataclasses import dataclass

# A workflow that is written down but not yet worked through end to end. Marked
# rather than omitted: a cookbook that showed only the finished recipes would
# read as the whole of what a person needs, and the gap is the useful part.
STUB = "stub"
WORKED = "worked through"


@dataclass(frozen=True)
class Step:
    """One line of a recipe: something to run, or something to decide."""

    does: str
    """What this step is for, in words."""

    command: str = ""
    """The line to type. Empty makes this a gate."""

    in_project: str = ""
    """The same step inside a project repository, where `qm` is not installed.

    **THE CLI IS THE CORPUS REPOSITORY'S, AND A FORK DOES NOT GET IT.** A fork
    runs the seed scripts in place, out of `governance/qm/project-seed/ci/`,
    and installs nothing -- so a recipe that only gave the `uv run qm` form
    would be a command that does not exist for most of the people reading it.
    Empty means the command is the same in both.
    """

    says: str = ""
    """What you should see, or what to look for in what you see."""

    decides: str = ""
    """What the person is deciding here. Gates only, and required of them."""

    @property
    def is_gate(self) -> bool:
        return not self.command


@dataclass(frozen=True)
class Workflow:
    """One repeatable thing, with the person marked."""

    name: str
    intent: str
    """One line: what you are trying to achieve, not what you are typing."""

    steps: tuple[Step, ...]
    follows: tuple[str, ...] = ()
    feeds: tuple[str, ...] = ()
    state: str = WORKED
    cannot: str = ""
    """What this workflow does not do, where somebody would assume it does."""

    why_no_gate: str = ""
    """Required when there is no gate. Reading is not the same as deciding."""

    @property
    def gates(self) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.is_gate)


def _keys(action: str) -> str:
    """The keys that reach `action`, read from the menu.

    **THE RECIPE HAD THE WRONG ONES.** It said `m 8 6 6`, which opens the Sweep
    tab; `m 6 4` runs the review the step is describing. Two acts, two routes,
    and a recipe is read by somebody about to type what it says.
    """
    from dossier.rad.index import keystroke

    found = keystroke(action)
    return " ".join(f"`{key}`" for key in found.split()) if found else "(unwired)"


WORKFLOWS: tuple[Workflow, ...] = (
    Workflow(
        name="Start a slice",
        intent="Begin one piece of work on a branch cut from a base you have "
               "actually looked at.",
        steps=(
            Step(does="Find out whether your pull request slot is free",
                 command="uv run qm slot --repo <owner>/<name>",
                 in_project="gh pr list --repo <owner>/<name> --author @me",
                 says="One open pull request per repository per contributor. "
                      "A second one is a sequencing problem, not a bandwidth "
                      "one."),
            Step(does="See what else is in flight in this clone",
                 command="git status --short && git branch --show-current",
                 says="A dirty tree you did not dirty means another session "
                      "is working here. Reconcile before you write."),
            Step(does="Take the base you are branching from",
                 command="git checkout main && git pull --ff-only",
                 says="`--ff-only` refuses rather than merging behind your "
                      "back."),
            Step(does="Cut the branch",
                 command="git checkout -b <kind>/<slug>",
                 says="`evolve/` for org work, `perspective/<date>-<slug>`, "
                      "`project/<name>`, or `fix/` and `chore/` in a project "
                      "repository."),
        ),
        feeds=("Check what your branch carries", "Run the gates locally"),
        why_no_gate="Nothing is decided here and nothing leaves the machine. "
                    "The slot check is a reading; acting on what it says is "
                    "the next workflow's gate.",
        cannot="Tell you whether the work is worth doing, or whether somebody "
               "else has already started it. `dossier show deltas` is the "
               "reading for the second one.",
    ),
    Workflow(
        name="Check what your branch carries",
        intent="Find out what is actually on the branch before anybody reads a "
               "diff that says something else.",
        steps=(
            Step(does="Ask what the branch holds",
                 command="uv run qm branch --base main --head <branch>",
                 in_project="python governance/qm/project-seed/ci/check_pr_base.py --base main --head <branch>",
                 says="The merge-base, the commit and file counts, the "
                      "authors, and any commits that also live on another "
                      "branch."),
            Step(does="Read the merge-base against the base tip",
                 decides="Whether the branch was cut from where you think. A "
                         "branch cut from the wrong parent passes every other "
                         "check -- its tests are green and its lint is clean, "
                         "because those measure the branch and not where it "
                         "came from."),
            Step(does="Put the output in the pull request body",
                 command="uv run qm branch --base main --head <branch> "
                         "> body-branch.txt",
                 in_project="python governance/qm/project-seed/ci/"
                            "check_pr_base.py --base main --head <branch>",
                 says="A reader who can see the base does not have to trust "
                      "the title."),
        ),
        follows=("Start a slice",),
        feeds=("Open the pull request",),
        cannot="Tell you the change is correct. It answers where the branch "
               "came from, which is the question the green checks do not ask.",
    ),
    Workflow(
        name="Run the gates locally",
        intent="Run what CI runs, before calling anything ready.",
        steps=(
            Step(does="List the gates and what each one cannot see",
                 command="uv run qm gates",
                 in_project="cat governance/qm/ci/gate-registry.yaml",
                 says="A gate's blind spot is part of the gate."),
            Step(does="Run the workflows' real steps",
                 command="uv run --extra preflight qm preflight",
                 in_project="python governance/qm/project-seed/ci/run_workflows_locally.py",
                 says="Reading a workflow and running the commands you think "
                      "it contains are not the same thing, and the difference "
                      "is where false green claims come from."),
            Step(does="Read what failed, and why",
                 decides="Whether a failure is a defect or a difference "
                         "between this machine and the runner. Say which you "
                         "established -- an exit code reported without that "
                         "is a number, not a finding."),
        ),
        follows=("Start a slice",),
        feeds=("Open the pull request",),
        cannot="Reproduce every step. Some need the runner's environment, and "
               "the command says which those are rather than skipping them "
               "quietly.",
    ),
    Workflow(
        name="Open the pull request",
        intent="Put the work where the gates run and the diff stays readable.",
        steps=(
            Step(does="Push the branch",
                 command="git push -u origin <branch>"),
            Step(does="Open it, with the branch report in the body",
                 command="gh pr create --base main --head <branch> "
                         "--body-file <file>",
                 says="From a file. A body passed inline runs backticks as "
                      "command substitution and mangles itself."),
            Step(does="Assign the person who asked for the work",
                 command="gh pr edit <n> --add-assignee <login>",
                 says="Never request a review. Reviewers are named at the tag "
                      "-- governance/qm/handbook/async-contract.md section 2."),
            Step(does="Wait for the checks",
                 command="gh pr checks <n> --watch"),
        ),
        follows=("Check what your branch carries", "Run the gates locally"),
        feeds=("Merge your own green pull request",),
        why_no_gate="A pull request states decisions rather than asking "
                    "questions, so by the time one is open the deciding has "
                    "happened. Settle uncertainties in the session and wait.",
        cannot="Make the work reviewed. The pull request is an audit record; "
               "the human gates are ratification and the version tag.",
    ),
    Workflow(
        name="Merge your own green pull request",
        intent="Land the work yourself once every gate is green.",
        steps=(
            Step(does="Confirm every check passed",
                 command="gh pr checks <n>"),
            Step(does="Merge and delete the branch",
                 command="gh pr merge <n> --merge --delete-branch"),
            Step(does="Return to a clean base",
                 command="git checkout main && git pull --ff-only"),
        ),
        follows=("Open the pull request",),
        feeds=("Cut a version tag", "Propagate main into a project branch"),
        why_no_gate="`main` is not a claim, so merging into it is not a "
                    "release -- governance/qm/records/"
                    "DRAFT-version-tags-are-claims.md section 4. Keeping "
                    "`main` clean is what makes cutting a tag cheap. Waiting "
                    "for a second person here is waiting at a gate that is "
                    "not one.",
        cannot="Be undone tidily. Closing a pull request is a git operation: "
               "pushing a branch onto a pull request's base merges it, and a "
               "later close is a silent no-op.",
    ),
    Workflow(
        name="Cut a version tag",
        intent="Say, as a person, that this is what a project ships.",
        steps=(
            Step(does="Read what is on the base",
                 command="uv run qm branch --base main --head main",
                 in_project="git log --oneline $(git describe --tags --abbrev=0)..main",
                 says="What went in since the last tag."),
            Step(does="Test it against its real runtime",
                 decides="Whether you have run it, not whether CI has. A tag "
                         "asserts a human reviewed the change set, tested it "
                         "against its real runtime, and validation passed."),
            Step(does="Name the reviewer",
                 decides="Who reviewed it. Reviewers are named here and "
                         "nowhere earlier."),
            Step(does="Cut it",
                 command="git tag -a v<x.y.z> -m <message> && git push --tags"),
        ),
        follows=("Merge your own green pull request",),
        state=STUB,
        cannot="Be delegated. This and ratification are the two human gates in "
               "the corpus, and a tool cutting one would be the tool making "
               "the claim.",
    ),
    Workflow(
        name="Sweep one dependency across the org",
        intent="Make one change everywhere it is needed, as one piece of work "
               "rather than twenty that look alike.",
        steps=(
            Step(does="See what is shared, widest first",
                 command="dossier sweep",
                 says="There is no such thing as the package to sweep. The "
                      "widest-shared one is where a panel starts when nobody "
                      "has said."),
            Step(does="See what a sweep of one would touch",
                 command="dossier sweep <package>",
                 says="Each repository's share, and its shape: mechanical, or "
                      "waiting on a person. The target version is derived "
                      "from the shares, never typed."),
            Step(does="Open the review",
                 command="dossier dashboard",
                 says=f"Then {_keys('sweep.review')}. The panel groups the "
                      f"shares into batches, each of which is one identical "
                      f"edit."),
            Step(does="Approve a batch",
                 decides="One batch at a time, and only while every edit in it "
                         "is identical. A batch that is not uniform is two "
                         "decisions, and approving it as one is a person "
                         "approving nine things having read seven."),
        ),
        feeds=("Start a slice",),
        state=STUB,
        cannot="Open the pull requests. It works out the shape of each share; "
               "something else does the edit, and the queue is work waiting on "
               "a person rather than a failure list.",
    ),
    Workflow(
        name="Get a repository onto this machine",
        intent="Close the gap between what the database knows about and what "
               "this disk actually has.",
        steps=(
            Step(does="See what is indexed and not here",
                 command="dossier clone",
                 says="Lists and stops. A clone is a network fetch and a write "
                      "to your disk, so acting is asked for rather than "
                      "assumed."),
            Step(does="Decide how many you want",
                 decides="Whether you need all of them. A repository with no "
                         "clone here is a repository nobody needed on this "
                         "machine, which is an ordinary state and usually the "
                         "right one -- so this is a question about disk and "
                         "minutes, not about tidiness."),
            Step(does="Clone one, or all of them",
                 command="dossier clone <owner>/<name>       # or --all",
                 says="`--all` asks before it starts and names where they "
                      "land. Each result carries git's own words, because only "
                      "git can say whether a failure was a missing repository, "
                      "a missing credential or a full disk."),
            Step(does="Read what the clones now answer",
                 command="dossier show branches",
                 says="Branch hygiene reports `unknown` for a repository with "
                      "no clone. Those become real answers."),
        ),
        feeds=("Retire a branch safely",),
        cannot="Know whether you have the right to clone something. "
               "Authentication is git's, and a private repository this "
               "database learned about through an authenticated sync still "
               "refuses at the network if this machine has no credentials.",
    ),
    Workflow(
        name="Retire a branch safely",
        intent="Delete what is spent without deleting the only copy of "
               "something.",
        steps=(
            Step(does="Read what only this machine holds",
                 command="dossier show branches",
                 says="The sync reading, then the clones. A branch with "
                      "commits on no remote is the only copy of something; a "
                      "merged one is a label over history somebody already "
                      "has."),
            Step(does="Decide, per branch",
                 decides="Whether work reported at risk is wanted. git knows "
                         "a commit is unique and cannot know the change is "
                         "redundant -- three branches read this way in one "
                         "repository and all three were in fact spent."),
            Step(does="Delete the ones two opinions agree on",
                 command="git branch -d <branch>",
                 says="`-d` refuses a branch that is not merged. Reach for "
                      "`-D` only after the reading above, and never as the "
                      "first attempt."),
        ),
        feeds=("Start a slice",),
        cannot="See a commit that is in no branch at all. Reachable only from "
               "the reflog is a real way to lose work and not one a branch "
               "listing finds.",
    ),
    Workflow(
        name="Reconcile a shared clone",
        intent="Pick up work another session left in the tree you are about to "
               "write in.",
        steps=(
            Step(does="See what is uncommitted, and whose it is",
                 command="git status --short && git log --oneline -5"),
            Step(does="See whether the branch exists on the remote",
                 command="git log --oneline @{u}.. 2>/dev/null || "
                         "echo 'no upstream'",
                 says="No upstream means every commit here is in one place."),
            Step(does="Decide what to do with what you found",
                 decides="Whether it is yours to commit, to leave, or to ask "
                         "about. Committing another session's half-finished "
                         "work under your message is how the audit record "
                         "stops being one."),
        ),
        follows=("Start a slice",),
        state=STUB,
        cannot="Tell you which session made it. The tree records what changed "
               "and not who was running.",
    ),
    Workflow(
        name="Propagate main into a project branch",
        intent="Move org-level work down to a project without moving the "
               "project's decisions up.",
        steps=(
            Step(does="Branch from the project branch, not from main",
                 command="git checkout project/<name> && "
                         "git checkout -b propagate/<name>-<date>"),
            Step(does="Take main into it",
                 command="git merge main"),
            Step(does="Open it against the project branch",
                 command="gh pr create --base project/<name> "
                         "--head propagate/<name>-<date>",
                 says="Never the other direction. `project/<name>` takes "
                      "changes in and never out; merging it into main would "
                      "move one project's decisions into the org namespace."),
            Step(does="Read what the merge brought, before it lands",
                 decides="Whether anything in it belongs to a different "
                         "project. A propagation carries everything on main, "
                         "and the branch it lands on is pinned by a "
                         "downstream submodule -- so what goes in cannot be "
                         "rebased back out afterwards."),
        ),
        follows=("Merge your own green pull request",),
        state=STUB,
        cannot="Be rebased afterwards. A downstream submodule pins the tip, so "
               "the merge stays a merge.",
    ),
)

BY_NAME = {workflow.name: workflow for workflow in WORKFLOWS}


def as_markdown() -> str:
    """The committed page, generated from `WORKFLOWS`.

    Regenerated and compared by the test suite, so this function and
    `docs/cookbook.md` cannot disagree -- editing the page by hand is a failing
    test rather than a silent divergence, which is the only reason a reader can
    trust it after a command changes.
    """
    worked = [w for w in WORKFLOWS if w.state == WORKED]
    stubs = [w for w in WORKFLOWS if w.state == STUB]
    gated = [w for w in WORKFLOWS if w.gates]

    lines = [
        "<!-- Generated from dossier.cookbook.WORKFLOWS by "
        "`dossier cookbook --write docs/cookbook.md`.",
        "     Edit the workflows there, not this page: the test suite "
        "regenerates it and",
        "     compares, so a hand edit here fails the suite. -->",
        "",
        "# Workflows \u2014 a cookbook",
        "",
        "> **Short, repeatable, and with the person marked.** Every workflow "
        "here has a",
        "> human in it somewhere, and the recipe says where \u2014 because a "
        "workflow whose",
        "> human step is implicit is how somebody ends up approving nine "
        "things having",
        "> read seven.",
        ">",
        "> They compose. The common failure is not getting one wrong; it is "
        "doing three",
        "> in the wrong order.",
        "",
        "The same recipes are available where the work happens:",
        "",
        "```sh",
        "dossier cookbook",
        "dossier cookbook --name 'Start a slice'",
        "```",
        "",
        "## \u26a1 TL;DR \u2014 one slice, start to finish",
        "",
        "```bash",
        "gh pr list --repo <owner>/<name> --author @me   # is the slot free?",
        "git checkout main && git pull --ff-only         # a base you looked at",
        "git checkout -b fix/<slug>                      # cut the branch",
        "#   ... do the work ...",
        "python governance/qm/project-seed/ci/check_pr_base.py \\",
        "    --base main --head fix/<slug>               # what does it carry?",
        "python governance/qm/project-seed/ci/run_workflows_locally.py",
        "gh pr create --base main --body-file body.md",
        "gh pr checks <n> --watch",
        "gh pr merge <n> --merge --delete-branch         # you merge it",
        "```",
        "",
        "**That is the whole loop.** The tag is the next gate, and it is a "
        "person's.",
        "",
        "**These are the project-repository forms**, which run the seed scripts "
        "in place. In the corpus repository itself the same steps are "
        "`uv run qm slot`, `uv run qm branch` and "
        "`uv run --extra preflight qm preflight` -- the CLI exists there and "
        "nowhere else, and every recipe below gives both.",
        "",
        "## How to read a recipe",
        "",
        "- **Intent** is what you are trying to achieve, not what you are "
        "typing.",
        "- A step with a command is something to run. A step with no command "
        "is a **gate**, and it says what you are deciding.",
        "- **Follows** and **feeds** are how they compose.",
        "- **Cannot** is what the workflow does not do, where somebody would "
        "assume it does.",
        "",
        f"There are **{len(WORKFLOWS)}** workflows here, "
        f"**{len(gated)}** of which stop for a person. "
        f"**{len(stubs)}** are sketches \u2014 written down, not yet worked "
        "through end to end. They are marked, because a cookbook showing only "
        "the finished recipes would read as the whole of what a person needs.",
        "",
    ]

    for section, found in (("Worked through", worked), ("Sketches", stubs)):
        if not found:
            continue
        lines += ["## " + section, ""]
        for workflow in found:
            lines += _one(workflow)
    return "\n".join(lines) + "\n"


def _one(workflow: Workflow) -> list[str]:
    lines = [f"### {workflow.name}", "", f"**{workflow.intent}**", ""]
    for index, step in enumerate(workflow.steps, start=1):
        if step.is_gate:
            lines += [f"{index}. \U0001f9cd **{step.does}**", ""]
            if step.says:
                lines += [f"   {step.says}", ""]
            lines += [f"   > **You decide:** {step.decides}", ""]
            continue
        lines += [f"{index}. {step.does}", "", "   ```sh",
                  f"   {step.command}", "   ```", ""]
        if step.in_project:
            lines += ["   In a project repository, where `qm` is not "
                      "installed:", "", "   ```sh", f"   {step.in_project}",
                      "   ```", ""]
        if step.says:
            lines += [f"   {step.says}", ""]
    if workflow.follows:
        lines += ["**Follows:** " + ", ".join(workflow.follows) + "  "]
    if workflow.feeds:
        lines += ["**Feeds:** " + ", ".join(workflow.feeds) + "  "]
    if workflow.why_no_gate:
        lines += ["", f"**No gate, and why:** {workflow.why_no_gate}"]
    if workflow.cannot:
        lines += ["", f"**Cannot:** {workflow.cannot}"]
    lines += [""]
    return lines
