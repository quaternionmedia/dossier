# rad commands

**Generated. Do not edit.** Every number below is computed from
`dossier.rad.palette.resolve` and `dossier.rad.numpad.place` -- the same
two things the ring itself is built from. Regenerate by running the test
suite.

## The number is the route

`6.2` is not a name somebody gave to sync. It is the keys: `6` opens **Do**,
`2` is the third thing under it. Press `m` to open the ring, then the digits.
So sync is **`m` `6` `2`** -- three keys, from anywhere in the application.

```
    7  8  9
    4  5  6
    1  2  3
```

`5` is the centre. It backs out one level, or closes the ring,
at every level and every depth -- so it is never an item and there is no
`6.5`. Arrow keys and `wasd` move the highlight if you would
rather look than type; the digits are the fast path and both arrive at the
same cell.

## Every command

| # | keys | what | action | wired |
|---|---|---|---|---|
| `8` | `m` `8` | Go | *opens a submenu* | yes |
| `8.8` | `m` `8` `8` | &nbsp;&nbsp;Repositories | *opens a submenu* | yes |
| `8.8.8` | `m` `8` `8` `8` | &nbsp;&nbsp;&nbsp;&nbsp;Overview | `view.overview` | yes |
| `8.8.6` | `m` `8` `8` `6` | &nbsp;&nbsp;&nbsp;&nbsp;Details | `view.details` | yes |
| `8.8.2` | `m` `8` `8` `2` | &nbsp;&nbsp;&nbsp;&nbsp;Dossier | `view.dossier` | yes |
| `8.8.4` | `m` `8` `8` `4` | &nbsp;&nbsp;&nbsp;&nbsp;Documentation | `view.docs` | yes |
| `8.8.9` | `m` `8` `8` `9` | &nbsp;&nbsp;&nbsp;&nbsp;Languages | `view.languages` | yes |
| `8.6` | `m` `8` `6` | &nbsp;&nbsp;Work | *opens a submenu* | yes |
| `8.6.8` | `m` `8` `6` `8` | &nbsp;&nbsp;&nbsp;&nbsp;On deck | `view.deltas` | yes |
| `8.6.6` | `m` `8` `6` `6` | &nbsp;&nbsp;&nbsp;&nbsp;Sweep | `view.sweep` | yes |
| `8.6.2` | `m` `8` `6` `2` | &nbsp;&nbsp;&nbsp;&nbsp;Issues | `view.issues` | yes |
| `8.6.4` | `m` `8` `6` `4` | &nbsp;&nbsp;&nbsp;&nbsp;Waiting | `view.waiting` | yes |
| `8.2` | `m` `8` `2` | &nbsp;&nbsp;Code | *opens a submenu* | yes |
| `8.2.8` | `m` `8` `2` `8` | &nbsp;&nbsp;&nbsp;&nbsp;Branches | `view.branches` | yes |
| `8.2.6` | `m` `8` `2` `6` | &nbsp;&nbsp;&nbsp;&nbsp;Dependencies | `view.dependencies` | yes |
| `8.2.2` | `m` `8` `2` `2` | &nbsp;&nbsp;&nbsp;&nbsp;Contributors | `view.contributors` | yes |
| `8.2.4` | `m` `8` `2` `4` | &nbsp;&nbsp;&nbsp;&nbsp;Releases | `view.releases` | yes |
| `8.4` | `m` `8` `4` | &nbsp;&nbsp;Machine | *opens a submenu* | yes |
| `8.4.8` | `m` `8` `4` `8` | &nbsp;&nbsp;&nbsp;&nbsp;Governance | `view.governance` | yes |
| `8.4.6` | `m` `8` `4` `6` | &nbsp;&nbsp;&nbsp;&nbsp;Disk | `view.disk` | yes |
| `8.4.2` | `m` `8` `4` `2` | &nbsp;&nbsp;&nbsp;&nbsp;Topology | `view.topology` | yes |
| `8.4.4` | `m` `8` `4` `4` | &nbsp;&nbsp;&nbsp;&nbsp;Harness | `view.harness` | yes |
| `8.4.9` | `m` `8` `4` `9` | &nbsp;&nbsp;&nbsp;&nbsp;Threads | `view.threads` | yes |
| `6` | `m` `6` | Do | *opens a submenu* | yes |
| `6.8` | `m` `6` `8` | &nbsp;&nbsp;Advance phase | `delta.advance` | yes |
| `6.6` | `m` `6` `6` | &nbsp;&nbsp;Add note | `delta.note` | yes |
| `6.2` | `m` `6` `2` | &nbsp;&nbsp;Sync project | `project.sync` | yes |
| `6.4` | `m` `6` `4` | &nbsp;&nbsp;Sweep a dependency | `sweep.review` | yes |
| `2` | `m` `2` | Show | *opens a submenu* | yes |
| `2.8` | `m` `2` `8` | &nbsp;&nbsp;All | `filter.all` | yes |
| `2.6` | `m` `2` `6` | &nbsp;&nbsp;Synced only | `filter.synced` | yes |
| `2.2` | `m` `2` `2` | &nbsp;&nbsp;Drifting | `filter.drifting` | yes |
| `4` | `m` `4` | Reach | *opens a submenu* | yes |
| `4.8` | `m` `4` `8` | &nbsp;&nbsp;Open in qmcp | `reach.qmcp` | **not yet** |
| `4.6` | `m` `4` `6` | &nbsp;&nbsp;Ingest deltas | `reach.ingest` | yes |
| `4.2` | `m` `4` `2` | &nbsp;&nbsp;Reconcile | `reach.reconcile` | yes |
| `4.4` | `m` `4` `4` | &nbsp;&nbsp;Read conversation | `reach.read` | yes |
| `4.9` | `m` `4` `9` | &nbsp;&nbsp;Clone what is absent | `reach.clone` | yes |

## `6.2` -- making the view current

Press `m` `6` `2`. It refreshes what is on screen, and it always says
what it did.

**The tab decides what gets refreshed, not the selection.** On the
overview that is every repository the overview is scoped to -- the app
selects a repository on start-up, and scoping the organisation's
refresh to it would refresh one repository nobody chose. On a
repository tab it is that repository.

**Stale means older than 30 days**, the same threshold
the overview's attention list already sorts on. Never-synced is not
stale -- it is its own state, it has no age, and it is fetched first.
Repositories that are already current are not refetched.

**Above 5 repositories it asks first.** The first press
states what it would fetch; press `6` `2` again to go ahead. Going
anywhere else in the menu cancels it. Below that it just runs, so
the common case stays three keys.

**Some views a sync cannot help**, and it says which rather than
reporting nothing to do:

- `tab-deltas` -- deltas arrive by ingest, not by sync -- see Reach > Ingest deltas
- `tab-disk` -- read from disk at the moment you look
- `tab-docs` -- documents are read from disk
- `tab-harness` -- the harness reports about itself; dossier does not fetch it
- `tab-threads` -- the thread archive is the harness's, reached over HTTP
- `tab-waiting` -- questions are raised by a harness run, not fetched

## `4.6` -- putting an export into the archive

Conversations are not fetched. Somebody asks the service for an export,
waits for the mail, and downloads it -- that is a human step by
construction, and this organisation would want it to be one anyway.
What follows is everything after the download.

1. Press `m` `4` `6`. The archive opens with the cursor already in the
   path field -- you do not have to find it.
2. Type or paste the path to the export. Either the `conversations.json`
   itself or the folder holding it; surrounding double quotes are
   stripped, so Windows' *Copy as path* pastes straight in.
3. Press Enter. The button beside the field does the same thing and is
   there for a mouse -- neither is the real one.

**The panel does not write the archive.** It asks the harness to unpack
the export, because the harness owns it. If nothing is listening, the
refusal names the address it tried and the command that starts one --
not a silent failure and not a stack trace.

**The count is refreshed before it is reported**, so the number in the
message and the rows on the screen are one reading rather than two.

**`m` `6` `2` will not help here.** The archive is one of the views a
sync does not feed: it is the harness's, reached over HTTP, and syncing
GitHub would not change a row of it. Pressing sync on that tab says so
rather than reporting nothing to do.

**A command marked not yet is greyed out and cannot be chosen.** Its
cell is still there and still numbered -- dropping it would renumber
every command after it, and these numbers are written down. The digit
is refused, arrows and diagonals step over it, and a verb whose every
child is unavailable is greyed too rather than opening onto a level of
dead cells. It is drawn with a dotted border as well as a dimmer ink,
so the state survives a theme with no dim colour and a terminal that
approximates.

Not yet applied: `4.8` Open in qmcp.
