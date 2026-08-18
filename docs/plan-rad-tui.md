# Plan — a rad ring in the terminal, and messaging through it

**Written 2026-08-18, before any of it is built.** Every figure here was true at
`dossier` `main` `fe893b1`, `qmcp` `main` after #25, `qm` `main` `065d8eb`, and
`rad` at its `v0.5.0` vectors. Re-derive before quoting one.

This is a plan, not a decision record. What it records is a shape agreed with
the operator and the reasoning behind it, so the build can be picked up cold and
so the parts nobody has justified are visible as such.

---

## What this is for

Three surfaces exist and none of them shares an interaction model: dossier's TUI
(8,351 lines, 14 tabs, 11 modals, 34 bindings), qmcp's dashboard, and rad's web
reference implementation. The end state is one interaction contract across all
of them, with **messaging carried as rad intents**.

## The finding that makes a terminal ring possible

rad is not a pointer widget with a keyboard fallback bolted on. Its own
accessibility topic states the pointer-free path as foundational — *arrows
rotate the highlight, Enter commits, Escape backs out; pointer never required* —
and the drag-through submenu has a keyboard equivalent in the contract.

**So a Textual ring is not a reduced rad. It is rad's keyboard path, rendered as
a ring.** What a terminal cannot express is commit by crossing the outer rim
under a finger, and the pointer half of the input taxonomy. It *can* meter the
cost — see *Measuring the interaction* below, where rad turns out to count a
keystroke as an input already. Cases a terminal cannot express are named rather
than skipped — see *Conformance*.

## The division of ownership, which is rad's and not ours to redraw

| owns | party |
|---|---|
| geometry, state machine, committing band, hit resolution | **rad** |
| menu **content** for a context | **the host** |
| **applying** an intent to application state | **the host** |
| the scene, its coordinates, its lifecycle | **the host** |

`createSession({ resolve, onIntent, onEffect?, geometry? })` is the whole inbound
API. rad never reaches the host's scene, and the record is explicit that this is
a property of the surface rather than a promise about discipline.

## The durable palette, which is the part worth getting right

The operator's instruction was to **collapse the wedges into cross-app durable
generic palettes** — stable menus that mean the same thing on every platform and
in every host.

So the top level is four verbs, fixed, identical in dossier, in qmcp and on the
web:

| wedge | means | dossier fills it with | qmcp fills it with |
|---|---|---|---|
| **Go** | move to a context | the old tabs: Deltas, Governance, Disk, Details | invocations, tools, human loop |
| **Do** | act on what is selected | advance a phase, sync, add a note, link | invoke a tool, replay, export deltas |
| **Show** | change what is listed | synced only, by language, starred, drifting | by tool, by status, failures only |
| **Reach** | cross into another system | open this address in qmcp, ingest, reconcile | open this address in dossier |

**The shape is the contract; the children are the host's.** That is exactly
rad's division — content belongs to the host — and it is what makes the menu
learnable once rather than per application. A fifth top-level verb is a change
to the contract and needs a reason, not a pull request.

**Every wedge commits an address.** `Reach` is only coherent because
`owner/repo/kind/id` already names the same row in both systems.

## Stages

Each is usable alone and testable alone. Nothing later is a prerequisite for
something earlier being worth having.

### 1. The intent envelope

One message schema: what happened, to which address, at what cost, on whose
clock. Emitted and consumed by both dashboards. No UI. This is the messaging
layer, and it is where "implement messaging through rad" actually lives.

*Done:* both dashboards can emit and ingest an intent, and the schema is
versioned the way the delta payload is.

### 2. `rad-tui` — one centered pop-over ring

**Built inside dossier with a clean seam, extracted when qmcp needs it.** The
operator chose this over putting a Python surface in `rad` or standing up a
fourth repository; the risk it accepts is that "extract later" never happens,
and the seam is the mitigation. It takes no Textual widget in its public
surface, so extraction is a move rather than a rewrite.

One menu, centered, pop-over — not per-node, not per-panel.

*Done:* a ring opens over the dashboard, arrows rotate, Enter commits, Escape
backs out, and every commit produces an intent.

### 3. Palettes replace tab navigation

The 14 tabs become content returned by `resolve(context)`. The command palette
is the naming route, the ring the navigating one. **The data layer is untouched
— this is navigation, not deletion**: every view the tabs reached is still
reachable, through `Go` rather than through a tab strip.

**This is a replacement.** Tab navigation goes; the views stay. That removes a
discoverable surface, and the command palette is the mitigation — one that is
not yet proven, and is listed below as unsettled for that reason.

### 4. Cross-open

Each dashboard opens the other, as a `Reach` intent rather than a shell-out.

### 5. The demo corpus

64 non-archived, non-fork public repositories. **Fetch on demand with a warm-up
protocol** that batches imports for a first run or a bulk refresh, triggerable
from the API and from the dashboards. Existing synced data is kept; the work is
surfacing it cohesively, not re-fetching it.

Analysis is three layers: **code facts** read from the working tree, **governance
posture** (adoption, pin age, whether tests gate, tag status), and **deltas and
activity**.

## Conformance

`rad/conformance/vectors.json` holds 47 cases across 12 topics. The Textual
implementation is held to **the same cases**, not to its own — the pattern
already used for the address grammar, where two implementations are kept honest
by one set of vectors and neither imports the other.

**Cases a terminal cannot express are reported, never skipped silently.** A skip
is an absent test that has announced itself, and by standing direction a skip
blocks a tag. The pointer-specific cases will be listed explicitly, with the
reason, so the gap is a stated boundary rather than a green run.

## Measuring the interaction, which rad already defines

rad's metrics record defines one **input** as *"one pointer down…up envelope"*
**or** *"one keystroke"*, and measures IPA at **L3 — committed intents** —
precisely so it is *"comparable across platforms by construction"*. There is
already a keyboard budget. **A terminal meters IPA natively**, and a parallel
measure would be a second definition of a number rad already defines.

**IPA = inputs from idle to committed intent**, and its inverse, actions per
input, is the second figure tracked. Both are reported.

**All five levels are metered and reconciled at L3**, as rad requires: L0 raw
terminal key events, L1 recognized keys, L2 state-machine transitions, L3
committed intents. Metering only the top would give a correct IPA and forfeit
the reconciliation that makes the number trustworthy — and figures that cannot
sit beside the web implementation's are figures nobody can act on.

**The keyboard budget is `≤ 1 + ⌈N/2⌉ + 1`.** rad calls a verb over budget a
*resolver design error* — restructure the menu, do not relax the number — which
constrains how many children each of Go/Do/Show/Reach may carry. **Measured and
reported, not enforced as a build failure**, while the palette is still
settling. It is visible pressure rather than a gate; making it a gate is a later
decision and should be taken deliberately.

## Settled

- **The ring replaces tab navigation.** Stage 3 is a replacement, not a
  coexistence. The tabs' underlying views remain as views; what goes is
  navigating by tab.
- **qmcp's dashboard stays a CLI.** No ring there. `Reach` works across the two
  regardless, because it commits an address rather than a screen.
- **The clock is stubbed.** The intent envelope carries its timing fields from
  the start so that quantized commit is a later implementation rather than a
  schema version, and nothing schedules against a beat grid yet. Stubbing it now
  is cheaper than retrofitting it; pretending it works would be worse than
  either.

## What this plan still does not settle

- **Whether the IPA budget becomes a gate.** Reported now; enforcing it is a
  decision for when the palette has stopped moving.
- **What the ring costs a reader who never learns it.** Replacing tab navigation
  removes a discoverable surface. The command palette is the mitigation and is
  not yet proven to be one.
