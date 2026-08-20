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
| `8.8` | `m` `8` `8` | &nbsp;&nbsp;Overview | `view.overview` | yes |
| `8.6` | `m` `8` `6` | &nbsp;&nbsp;Deltas | `view.deltas` | yes |
| `8.2` | `m` `8` `2` | &nbsp;&nbsp;Governance | `view.governance` | yes |
| `8.4` | `m` `8` `4` | &nbsp;&nbsp;Disk | `view.disk` | yes |
| `8.9` | `m` `8` `9` | &nbsp;&nbsp;Details | `view.details` | yes |
| `6` | `m` `6` | Do | *opens a submenu* | yes |
| `6.8` | `m` `6` `8` | &nbsp;&nbsp;Advance phase | `delta.advance` | **not yet** |
| `6.6` | `m` `6` `6` | &nbsp;&nbsp;Add note | `delta.note` | **not yet** |
| `6.2` | `m` `6` `2` | &nbsp;&nbsp;Sync project | `project.sync` | yes |
| `2` | `m` `2` | Show | *opens a submenu* | yes |
| `2.8` | `m` `2` `8` | &nbsp;&nbsp;All | `filter.all` | **not yet** |
| `2.6` | `m` `2` `6` | &nbsp;&nbsp;Synced only | `filter.synced` | **not yet** |
| `2.2` | `m` `2` `2` | &nbsp;&nbsp;Drifting | `filter.drifting` | **not yet** |
| `4` | `m` `4` | Reach | *opens a submenu* | yes |
| `4.8` | `m` `4` `8` | &nbsp;&nbsp;Open in qmcp | `reach.qmcp` | **not yet** |
| `4.6` | `m` `4` `6` | &nbsp;&nbsp;Ingest deltas | `reach.ingest` | **not yet** |
| `4.2` | `m` `4` `2` | &nbsp;&nbsp;Reconcile | `reach.reconcile` | **not yet** |

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

A command marked **not yet** is in the menu and reachable; pressing it
reports that it is not applied rather than doing nothing quietly.

Not yet applied: `6.8` Advance phase, `6.6` Add note, `2.8` All, `2.6` Synced only, `2.2` Drifting, `4.8` Open in qmcp, `4.6` Ingest deltas, `4.2` Reconcile.
