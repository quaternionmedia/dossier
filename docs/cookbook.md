<!-- Generated from dossier.cookbook.WORKFLOWS by `dossier cookbook --write docs/cookbook.md`.
     Edit the workflows there, not this page: the test suite regenerates it and
     compares, so a hand edit here fails the suite. -->

# Workflows — a cookbook

> **Short, repeatable, and with the person marked.** Every workflow here has a
> human in it somewhere, and the recipe says where — because a workflow whose
> human step is implicit is how somebody ends up approving nine things having
> read seven.
>
> They compose. The common failure is not getting one wrong; it is doing three
> in the wrong order.

The same recipes are available where the work happens:

```sh
dossier cookbook
dossier cookbook --name 'Start a slice'
```

## ⚡ TL;DR — one slice, start to finish

```bash
gh pr list --repo <owner>/<name> --author @me   # is the slot free?
git checkout main && git pull --ff-only         # a base you looked at
git checkout -b fix/<slug>                      # cut the branch
#   ... do the work ...
python governance/qm/project-seed/ci/check_pr_base.py \
    --base main --head fix/<slug>               # what does it carry?
python governance/qm/project-seed/ci/run_workflows_locally.py
gh pr create --base main --body-file body.md
gh pr checks <n> --watch
gh pr merge <n> --merge --delete-branch         # you merge it
```

**That is the whole loop.** The tag is the next gate, and it is a person's.

**These are the project-repository forms**, which run the seed scripts in place. In the corpus repository itself the same steps are `uv run qm slot`, `uv run qm branch` and `uv run --extra preflight qm preflight` -- the CLI exists there and nowhere else, and every recipe below gives both.

## How to read a recipe

- **Intent** is what you are trying to achieve, not what you are typing.
- A step with a command is something to run. A step with no command is a **gate**, and it says what you are deciding.
- **Follows** and **feeds** are how they compose.
- **Cannot** is what the workflow does not do, where somebody would assume it does.

There are **11** workflows here, **8** of which stop for a person. **4** are sketches — written down, not yet worked through end to end. They are marked, because a cookbook showing only the finished recipes would read as the whole of what a person needs.

## Worked through

### Start a slice

**Begin one piece of work on a branch cut from a base you have actually looked at.**

1. Find out whether your pull request slot is free

   ```sh
   uv run qm slot --repo <owner>/<name>
   ```

   In a project repository, where `qm` is not installed:

   ```sh
   gh pr list --repo <owner>/<name> --author @me
   ```

   One open pull request per repository per contributor. A second one is a sequencing problem, not a bandwidth one.

2. See what else is in flight in this clone

   ```sh
   git status --short && git branch --show-current
   ```

   A dirty tree you did not dirty means another session is working here. Reconcile before you write.

3. Take the base you are branching from

   ```sh
   git checkout main && git pull --ff-only
   ```

   `--ff-only` refuses rather than merging behind your back.

4. Cut the branch

   ```sh
   git checkout -b <kind>/<slug>
   ```

   `evolve/` for org work, `perspective/<date>-<slug>`, `project/<name>`, or `fix/` and `chore/` in a project repository.

**Feeds:** Check what your branch carries, Run the gates locally  

**No gate, and why:** Nothing is decided here and nothing leaves the machine. The slot check is a reading; acting on what it says is the next workflow's gate.

**Cannot:** Tell you whether the work is worth doing, or whether somebody else has already started it. `dossier show deltas` is the reading for the second one.

### Check what your branch carries

**Find out what is actually on the branch before anybody reads a diff that says something else.**

1. Ask what the branch holds

   ```sh
   uv run qm branch --base main --head <branch>
   ```

   In a project repository, where `qm` is not installed:

   ```sh
   python governance/qm/project-seed/ci/check_pr_base.py --base main --head <branch>
   ```

   The merge-base, the commit and file counts, the authors, and any commits that also live on another branch.

2. 🧍 **Read the merge-base against the base tip**

   > **You decide:** Whether the branch was cut from where you think. A branch cut from the wrong parent passes every other check -- its tests are green and its lint is clean, because those measure the branch and not where it came from.

3. Put the output in the pull request body

   ```sh
   uv run qm branch --base main --head <branch> > body-branch.txt
   ```

   In a project repository, where `qm` is not installed:

   ```sh
   python governance/qm/project-seed/ci/check_pr_base.py --base main --head <branch>
   ```

   A reader who can see the base does not have to trust the title.

**Follows:** Start a slice  
**Feeds:** Open the pull request  

**Cannot:** Tell you the change is correct. It answers where the branch came from, which is the question the green checks do not ask.

### Run the gates locally

**Run what CI runs, before calling anything ready.**

1. List the gates and what each one cannot see

   ```sh
   uv run qm gates
   ```

   In a project repository, where `qm` is not installed:

   ```sh
   cat governance/qm/ci/gate-registry.yaml
   ```

   A gate's blind spot is part of the gate.

2. Run the workflows' real steps

   ```sh
   uv run --extra preflight qm preflight
   ```

   In a project repository, where `qm` is not installed:

   ```sh
   python governance/qm/project-seed/ci/run_workflows_locally.py
   ```

   Reading a workflow and running the commands you think it contains are not the same thing, and the difference is where false green claims come from.

3. 🧍 **Read what failed, and why**

   > **You decide:** Whether a failure is a defect or a difference between this machine and the runner. Say which you established -- an exit code reported without that is a number, not a finding.

**Follows:** Start a slice  
**Feeds:** Open the pull request  

**Cannot:** Reproduce every step. Some need the runner's environment, and the command says which those are rather than skipping them quietly.

### Open the pull request

**Put the work where the gates run and the diff stays readable.**

1. Push the branch

   ```sh
   git push -u origin <branch>
   ```

2. Open it, with the branch report in the body

   ```sh
   gh pr create --base main --head <branch> --body-file <file>
   ```

   From a file. A body passed inline runs backticks as command substitution and mangles itself.

3. Assign the person who asked for the work

   ```sh
   gh pr edit <n> --add-assignee <login>
   ```

   Never request a review. Reviewers are named at the tag -- governance/qm/handbook/async-contract.md section 2.

4. Wait for the checks

   ```sh
   gh pr checks <n> --watch
   ```

**Follows:** Check what your branch carries, Run the gates locally  
**Feeds:** Merge your own green pull request  

**No gate, and why:** A pull request states decisions rather than asking questions, so by the time one is open the deciding has happened. Settle uncertainties in the session and wait.

**Cannot:** Make the work reviewed. The pull request is an audit record; the human gates are ratification and the version tag.

### Merge your own green pull request

**Land the work yourself once every gate is green.**

1. Confirm every check passed

   ```sh
   gh pr checks <n>
   ```

2. Merge and delete the branch

   ```sh
   gh pr merge <n> --merge --delete-branch
   ```

3. Return to a clean base

   ```sh
   git checkout main && git pull --ff-only
   ```

**Follows:** Open the pull request  
**Feeds:** Cut a version tag, Propagate main into a project branch  

**No gate, and why:** `main` is not a claim, so merging into it is not a release -- governance/qm/records/DRAFT-version-tags-are-claims.md section 4. Keeping `main` clean is what makes cutting a tag cheap. Waiting for a second person here is waiting at a gate that is not one.

**Cannot:** Be undone tidily. Closing a pull request is a git operation: pushing a branch onto a pull request's base merges it, and a later close is a silent no-op.

### Get a repository onto this machine

**Close the gap between what the database knows about and what this disk actually has.**

1. See what is indexed and not here

   ```sh
   dossier clone
   ```

   Lists and stops. A clone is a network fetch and a write to your disk, so acting is asked for rather than assumed.

2. 🧍 **Decide how many you want**

   > **You decide:** Whether you need all of them. A repository with no clone here is a repository nobody needed on this machine, which is an ordinary state and usually the right one -- so this is a question about disk and minutes, not about tidiness.

3. Clone one, or all of them

   ```sh
   dossier clone <owner>/<name>       # or --all
   ```

   `--all` asks before it starts and names where they land. Each result carries git's own words, because only git can say whether a failure was a missing repository, a missing credential or a full disk.

4. Read what the clones now answer

   ```sh
   dossier show branches
   ```

   Branch hygiene reports `unknown` for a repository with no clone. Those become real answers.

**Feeds:** Retire a branch safely  

**Cannot:** Know whether you have the right to clone something. Authentication is git's, and a private repository this database learned about through an authenticated sync still refuses at the network if this machine has no credentials.

### Retire a branch safely

**Delete what is spent without deleting the only copy of something.**

1. Read what only this machine holds

   ```sh
   dossier show branches
   ```

   The sync reading, then the clones. A branch with commits on no remote is the only copy of something; a merged one is a label over history somebody already has.

2. 🧍 **Decide, per branch**

   > **You decide:** Whether work reported at risk is wanted. git knows a commit is unique and cannot know the change is redundant -- three branches read this way in one repository and all three were in fact spent.

3. Delete the ones two opinions agree on

   ```sh
   git branch -d <branch>
   ```

   `-d` refuses a branch that is not merged. Reach for `-D` only after the reading above, and never as the first attempt.

**Feeds:** Start a slice  

**Cannot:** See a commit that is in no branch at all. Reachable only from the reflog is a real way to lose work and not one a branch listing finds.

## Sketches

### Cut a version tag

**Say, as a person, that this is what a project ships.**

1. Read what is on the base

   ```sh
   uv run qm branch --base main --head main
   ```

   In a project repository, where `qm` is not installed:

   ```sh
   git log --oneline $(git describe --tags --abbrev=0)..main
   ```

   What went in since the last tag.

2. 🧍 **Test it against its real runtime**

   > **You decide:** Whether you have run it, not whether CI has. A tag asserts a human reviewed the change set, tested it against its real runtime, and validation passed.

3. 🧍 **Name the reviewer**

   > **You decide:** Who reviewed it. Reviewers are named here and nowhere earlier.

4. Cut it

   ```sh
   git tag -a v<x.y.z> -m <message> && git push --tags
   ```

**Follows:** Merge your own green pull request  

**Cannot:** Be delegated. This and ratification are the two human gates in the corpus, and a tool cutting one would be the tool making the claim.

### Sweep one dependency across the org

**Make one change everywhere it is needed, as one piece of work rather than twenty that look alike.**

1. See what is shared, widest first

   ```sh
   dossier sweep
   ```

   There is no such thing as the package to sweep. The widest-shared one is where a panel starts when nobody has said.

2. See what a sweep of one would touch

   ```sh
   dossier sweep <package>
   ```

   Each repository's share, and its shape: mechanical, or waiting on a person. The target version is derived from the shares, never typed.

3. Open the review

   ```sh
   dossier dashboard
   ```

   Then `m` `6` `4`. The panel groups the shares into batches, each of which is one identical edit.

4. 🧍 **Approve a batch**

   > **You decide:** One batch at a time, and only while every edit in it is identical. A batch that is not uniform is two decisions, and approving it as one is a person approving nine things having read seven.

**Feeds:** Start a slice  

**Cannot:** Open the pull requests. It works out the shape of each share; something else does the edit, and the queue is work waiting on a person rather than a failure list.

### Reconcile a shared clone

**Pick up work another session left in the tree you are about to write in.**

1. See what is uncommitted, and whose it is

   ```sh
   git status --short && git log --oneline -5
   ```

2. See whether the branch exists on the remote

   ```sh
   git log --oneline @{u}.. 2>/dev/null || echo 'no upstream'
   ```

   No upstream means every commit here is in one place.

3. 🧍 **Decide what to do with what you found**

   > **You decide:** Whether it is yours to commit, to leave, or to ask about. Committing another session's half-finished work under your message is how the audit record stops being one.

**Follows:** Start a slice  

**Cannot:** Tell you which session made it. The tree records what changed and not who was running.

### Propagate main into a project branch

**Move org-level work down to a project without moving the project's decisions up.**

1. Branch from the project branch, not from main

   ```sh
   git checkout project/<name> && git checkout -b propagate/<name>-<date>
   ```

2. Take main into it

   ```sh
   git merge main
   ```

3. Open it against the project branch

   ```sh
   gh pr create --base project/<name> --head propagate/<name>-<date>
   ```

   Never the other direction. `project/<name>` takes changes in and never out; merging it into main would move one project's decisions into the org namespace.

4. 🧍 **Read what the merge brought, before it lands**

   > **You decide:** Whether anything in it belongs to a different project. A propagation carries everything on main, and the branch it lands on is pinned by a downstream submodule -- so what goes in cannot be rebased back out afterwards.

**Follows:** Merge your own green pull request  

**Cannot:** Be rebased afterwards. A downstream submodule pins the tip, so the merge stays a merge.

