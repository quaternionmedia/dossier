# What dossier can be asked to do

**Generated. Do not edit.** Every number is computed from the menu --
`dossier.rad.palette`, `dossier.rad.numpad` and `dossier.views` -- and
regenerating rides the ordinary test command.

## The number is the keystroke

`8.9.8` is not a name somebody gave to Harness. It is the keys: `8` is **Go**, `9` is **Seams**, and the last one is **Harness** itself. Press `m` to open the ring, then the digits -- so Harness is `m` `8` `9` `8`, from anywhere in the application.

`5` is the centre. It backs out one level, or closes the ring, at every
depth -- so it is never an item and no number contains it. Arrows and
`wasd` move the highlight if you would rather look than type.

## Contents

- **`8`  Go**
  - **`8.8`  Triage**
    - `8.8.8`  Overview -- `m` `8` `8` `8`
      Every repository in one reading, with what needs attention first.
      `dossier overview`
    - `8.8.6`  Outstanding -- `m` `8` `8` `6`
      Everything three readings noticed -- harness questions, repositories nothing has read lately, invocations that failed -- and what would settle each. Zero is a real answer, not an empty table.
      `dossier show waiting`
    - `8.8.2`  Issues -- `m` `8` `8` `2`
      Open issues, most recently updated first.
      `dossier show issues`
  - **`8.6`  Plan**
    - `8.6.8`  On deck -- `m` `8` `6` `8`
      Open deltas, every open pull request no delta claims, and every line of work in flight -- the harness's threads, read over its seam.
      `dossier governance threads`
    - `8.6.6`  Sweep -- `m` `8` `6` `6`
      What one dependency change would touch and where it needs a person, and what a cleanup of this workstation would get back -- the two sweeps, one that spans the estate and one that spans the disk.
      `dossier sweep`
  - **`8.2`  Explore**
    - `8.2.8`  Dossier -- `m` `8` `2` `8`
      One repository in one reading: its own facts, the document and parts it is composed of, and the languages it is written in -- the consistent overview of a repository dossier holds.
      `dossier export show`
    - `8.2.6`  Documentation -- `m` `8` `2` `6`
      Every documentation section parsed out of the repository.
      `dossier query`
    - `8.2.2`  Branches -- `m` `8` `2` `2`
      Branches from the sync, and what only the clones on this machine hold.
      `dossier show branches`
    - `8.2.4`  Dependencies -- `m` `8` `2` `4`
      What every repository declares, and what they share.
      `dossier show dependencies`
    - `8.2.9`  Contributors -- `m` `8` `2` `9`
      Who has committed where, by how many repositories they reach.
      `dossier show contributors`
    - `8.2.3`  Releases -- `m` `8` `2` `3`
      Tags that were cut, newest first. The one human gate a project has.
      `dossier show releases`
  - **`8.4`  Health**
    - `8.4.8`  Governance -- `m` `8` `4` `8`
      Where every project stands against the corpus: current, drifted, unmeasured.
      `dossier governance show`
  - **`8.9`  Seams**
    - `8.9.8`  Harness -- `m` `8` `9` `8`
      What the harness ran, when, and whether it finished.
      `dossier harness ingest`
    - `8.9.6`  Topology -- `m` `8` `9` `6`
      How the harness, its projects and their deltas connect.
      `dossier topology`
    - `8.9.2`  Goals -- `m` `8` `9` `2`
      Send the harness a new goal, and read the plan it drafts.
      `dossier harness goal`
- **`6`  Do**
  - `6.8`  Advance phase -- `m` `6` `8`
    *in the application only*
  - `6.6`  Add note -- `m` `6` `6`
    *in the application only*
  - `6.2`  Sync project -- `m` `6` `2`
    `dossier github sync`
  - `6.4`  Sweep a dependency -- `m` `6` `4`
    `dossier sweep`
  - `6.9`  Add a project -- `m` `6` `9`
    `dossier projects add`
  - `6.3`  Remove a project -- `m` `6` `3`
    `dossier projects remove`
- **`2`  Show**
  - `2.8`  All -- `m` `2` `8`
    *in the application only*
  - `2.6`  Synced only -- `m` `2` `6`
    *in the application only*
  - `2.2`  Drifting -- `m` `2` `2`
    *in the application only*
- **`4`  Reach**
  - `4.8`  Open in qmcp -- `m` `4` `8`  *(not applied yet)*
    *in the application only*
  - `4.6`  Ingest deltas -- `m` `4` `6`
    `dossier deltas ingest`
  - `4.2`  Reconcile -- `m` `4` `2`
    *in the application only*
  - `4.4`  Read conversation -- `m` `4` `4`
    *in the application only*
  - `4.9`  Clone what is absent -- `m` `4` `9`
    `dossier clone`

## Outside the ring

`dossier --help` reaches **83** leaf commands; **20**
of them are named above beside the view they belong to. The rest are
not menu items and are not meant to be: the ring is for what somebody
does repeatedly, and a cell spent on a once-a-quarter migration is a
cell taken from something else.

```
  dossier capabilities
  dossier components add
  dossier components list
  dossier components remove
  dossier cookbook
  dossier dashboard
  dossier db backup
  dossier db current
  dossier db downgrade
  dossier db health
  dossier db history
  dossier db revision
  dossier db stamp
  dossier db upgrade
  dossier deltas compose
  dossier deltas compound
  dossier deltas from-prs
  dossier deltas prune
  dossier deltas prune-forks
  dossier deltas relate
  dossier deltas search
  dossier deltas tangles
  dossier dev clear
  dossier dev dump
  dossier dev purge
  dossier dev reset
  dossier dev seed
  dossier dev status
  dossier dev test
  dossier dev vacuum
  dossier disk check
  dossier disk cookbook
  dossier disk dashboard
  dossier disk delta
  dossier disk load
  dossier disk reclaim
  dossier disk reclaims
  dossier disk status
  dossier docs build
  dossier docs serve
  dossier export all
  dossier export dossier
  dossier gates list
  dossier gates run
  dossier github info
  dossier github search
  dossier github sync-org
  dossier github sync-user
  dossier governance dashboard
  dossier governance load
  dossier graph build
  dossier graph build-all
  dossier graph stats
  dossier harness answer
  dossier harness queue
  dossier index
  dossier init
  dossier numpad
  dossier parse
  dossier projects list
  dossier projects purge
  dossier projects rename
  dossier projects show
  dossier serve
  dossier show
  dossier test
  dossier trim
  dossier tui
  dossier view
```
