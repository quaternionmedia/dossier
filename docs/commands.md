# What dossier can be asked to do

**Generated. Do not edit.** Every number is computed from the menu --
`dossier.rad.palette`, `dossier.rad.numpad` and `dossier.views` -- and
regenerating rides the ordinary test command.

## The number is the keystroke

`8.8.9` is not a name somebody gave to Languages. It is the keys: `8` is **Go**, `8` is **Repositories**, and the last one is **Languages** itself. Press `m` to open the ring, then the digits -- so Languages is `m` `8` `8` `9`, from anywhere in the application.

`5` is the centre. It backs out one level, or closes the ring, at every
depth -- so it is never an item and no number contains it. Arrows and
`wasd` move the highlight if you would rather look than type.

## Contents

- **`8`  Go**
  - **`8.8`  Repositories**
    - `8.8.8`  Overview -- `m` `8` `8` `8`
      Every repository in one reading, with what needs attention first.
      `dossier overview`
    - `8.8.6`  Details -- `m` `8` `8` `6`
      One repository's own facts: description, owner, when it last synced.
      `dossier projects show`
    - `8.8.2`  Dossier -- `m` `8` `8` `2`
      The repository as a document, and the projects it is composed of.
      `dossier export show`
    - `8.8.4`  Documentation -- `m` `8` `8` `4`
      Every documentation section parsed out of the repository.
      `dossier query`
    - `8.8.9`  Languages -- `m` `8` `8` `9`
      What the repository is written in, by share of its bytes.
      `dossier show languages`
  - **`8.6`  Work**
    - `8.6.8`  On deck -- `m` `8` `6` `8`
      Open deltas, and every open pull request no delta claims.
      `dossier show deltas`
    - `8.6.6`  Sweep -- `m` `8` `6` `6`
      What one dependency change would touch, and where it needs a person.
      `dossier sweep`
    - `8.6.2`  Issues -- `m` `8` `6` `2`
      Open issues, most recently updated first.
      `dossier show issues`
    - `8.6.4`  Outstanding -- `m` `8` `6` `4`
      Everything three readings noticed -- harness questions, repositories nothing has read lately, invocations that failed -- and what would settle each. Zero is a real answer, not an empty table.
      `dossier show waiting`
  - **`8.2`  Code**
    - `8.2.8`  Branches -- `m` `8` `2` `8`
      Branches from the sync, and what only the clones on this machine hold.
      `dossier show branches`
    - `8.2.6`  Dependencies -- `m` `8` `2` `6`
      What every repository declares, and what they share.
      `dossier show dependencies`
    - `8.2.2`  Contributors -- `m` `8` `2` `2`
      Who has committed where, by how many repositories they reach.
      `dossier show contributors`
    - `8.2.4`  Releases -- `m` `8` `2` `4`
      Tags that were cut, newest first. The one human gate a project has.
      `dossier show releases`
  - **`8.4`  Machine**
    - `8.4.8`  Governance -- `m` `8` `4` `8`
      Where every project stands against the corpus: current, drifted, unmeasured.
      `dossier governance show`
    - `8.4.6`  Disk -- `m` `8` `4` `6`
      What is eating this machine, and what it would take to get it back.
      `dossier disk status`
    - `8.4.2`  Topology -- `m` `8` `4` `2`
      How the harness, its projects and their deltas connect.
      `dossier topology`
    - `8.4.4`  Harness -- `m` `8` `4` `4`
      What the harness ran, when, and whether it finished.
      `dossier harness ingest`
    - `8.4.9`  Threads -- `m` `8` `4` `9`
      Every line of work in flight, most idle first.
      `dossier governance threads`
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

`dossier --help` reaches **79** leaf commands; **23**
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
  dossier index
  dossier init
  dossier parse
  dossier projects list
  dossier projects purge
  dossier projects rename
  dossier serve
  dossier show
  dossier test
  dossier trim
  dossier tui
  dossier view
```
