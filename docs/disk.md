<!-- Generated from dossier.disk.COOKBOOK by `dossier disk cookbook --write docs/disk.md`.
     Edit the recipes there, not this page: tests/test_disk.py regenerates it and
     compares, so a hand edit here fails the suite. -->

# Disk — a cookbook

Recipes for keeping this workstation off the floor. Every command below runs the
corpus's own disk tooling; dossier measures nothing and decides nothing here.

The same recipes are available where the work happens:

```sh
dossier disk cookbook
```

## How the pieces fit

| Artifact | Lives in | Holds |
|---|---|---|
| `ci/disk-policy.yaml` | the corpus, committed | every place the tooling may free space, and what it costs to get each one back |
| `ci/disk_status.py` | the corpus | measures the policy against this host; deletes nothing |
| `ci/disk_dashboard.py` | the corpus | renders the document; runs no commands |
| `ci/disk_reclaim.py` | the corpus | acts, and only on what the policy names |
| `~/.dossier/disk-status.json` | this machine, never committed | the measurement, with its own age and reading instructions inside it |

**Safety is the cost of recovery, not a guess at risk.** Three tiers: `refetched`
(the owning tool downloads it again, unprompted), `rebuilt` (a command you run),
`destructive` (nothing comes back). They are a ratchet — permitting one permits
every cheaper one — so no invocation empties the recycle bin while sparing a
download cache.

## Recipes

### Am I about to run out?

```sh
dossier disk check
```

Before a build, a container pull, or anything that writes a lot. It writes no document and takes about a second.

> Exits 2 when a volume is critical and 1 when one is low or unreadable, so it works in front of `&&` or as a scheduled task.

### What is actually eating the disk?

```sh
dossier disk status
```

Once check says something. Measures every target in the corpus policy and prints the agent view, largest first.

> The document lands in ~/.dossier/disk-status.json -- outside every repository, because it describes this machine and no other.

### See it as a page rather than a table

```sh
dossier disk status --html
```

When you want to hand somebody the picture, or read the thresholds and tiers with their explanations attached.

### Free the space that costs nothing

```sh
dossier disk reclaim
```

Always run this first. It is a dry run: it prints what it would remove and removes nothing.

> Add --apply when the plan looks right. The default tier is `refetched` -- caches the owning tool downloads again by itself.

### Free one specific thing

```sh
dossier disk reclaim --target nvidia-ota-artifacts --apply
```

When one target dominates and you would rather not touch the rest. Target names come from `dossier disk status`.

> An unknown name is an error rather than a silent no-op, because a typo that quietly does nothing reads as a clean machine.

### I need N gigabytes before a build

```sh
dossier disk reclaim --until-free 60 --apply
```

When there is a number you have to hit. Stops as soon as the volume is at or above it rather than clearing everything.

### Go past the free tier

```sh
dossier disk reclaim --allow rebuilt --apply
```

When the cheap tier was not enough. Adds browser binaries, node_modules and virtual environments.

> Costs an explicit `uv sync` / `npm ci` / `playwright install` in each project afterwards. Do not reach for it before going offline. The tiers are a ratchet: this permits `refetched` too, and there is no way to permit an expensive tier while excluding a cheap one.

### Add something the policy does not know about

```sh
$EDITOR <corpus>/ci/disk-policy.yaml
```

When you catch yourself deleting something by hand twice.

> Every target carries what it costs to get the bytes back, and an entry without that classification is refused rather than assumed. It is a reviewed change in the corpus, so the next person inherits the reasoning instead of rediscovering it.

### It says the checkout has no disk tooling

```sh
dossier disk status --corpus-dir ../qm
```

When the vendored governance/qm is the checkout that was found.

> Expected, not broken. A project's vendored corpus is pinned to a branch cut from the corpus's main, and the tooling is not on main yet, so that path is empty by construction. Point at a corpus checkout that carries ci/. The default starts working on its own once the corpus change lands and this project's pin is bumped past it.

### A Windows console raises UnicodeEncodeError

```sh
$env:PYTHONIOENCODING = "utf-8"
```

Once per shell, before any of the above. The corpus tooling writes em dashes and this group passes its output through.

> Same prep as the governance commands, and for the same reason -- docs/governance.md carries the long version. A cp1252 console raises rather than mangling, so the failure is loud and looks like a bug in the tool.

### Docker's target says unknown

```sh
docker system df
```

When the daemon is stopped. An unmeasurable target is reported as unknown with its reason, never as empty.

> Pruning frees space inside the VHDX; it does not shrink the file, which only grows. Compacting it needs Docker stopped and is deliberately not automated.

## What binds anything added here

- **dossier computes no disk fact.** A figure this view wants and the document lacks is a change to the corpus generator, reviewed once, so every reader gets it.
- **The document is never committed, in either repository.** It describes one machine at one moment, and `dossier disk status` refuses a destination inside any git repository rather than trusting anyone to remember.
- **A dry run is the default on both sides of the boundary.** Neither the corpus reclaimer nor this wrapper can be configured to delete by default.
