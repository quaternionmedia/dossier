# 05 — A project made of projects

Everything on this page runs. It is executed by the ordinary test command, so
an example that stops being true fails the build rather than sitting here
misleading somebody.

The examples are **this workspace**, not invented ones. That is deliberate: a
page built from fixtures demonstrates the code, and a page built from the real
thing demonstrates the organisation. It also means this page goes stale when the
workspace changes, which is the page working rather than the page breaking.

## The thing being composed

Six repositories embed the constitution as a submodule at `governance/qm`:

    >>> PARTS = ("dossier", "qmcp", "rad", "alfred", "apothecary", "datum")
    >>> len(PARTS)
    6

None of them contains the others. They are not a hierarchy and they are not
independent, which is exactly the case `part-of` alone cannot describe --
`governance/qm/records/DRAFT-deltas-compose.md` is why there are five relations
and not one.

    >>> from dossier.composition import RELATIONS
    >>> sorted(RELATIONS)
    ['blocks', 'crosses', 'derived-from', 'part-of', 'same-as']

## Stating it

Each repository's work is `part-of` the org's, and each is `derived-from` the
corpus it pins. Both are true at once and they say different things: closing the
org's delta requires closing the parts, while `derived-from` records that a
strand came out of the corpus and **both continue**.

    >>> from dossier.composition import Edge
    >>> ORG = "quaternionmedia/qm/delta/the-workspace"
    >>> CORPUS = "quaternionmedia/qm/delta/constitution"
    >>> edges = []
    >>> for part in PARTS:
    ...     here = f"quaternionmedia/{part}/delta/the-work"
    ...     edges.append(Edge(here, "part-of", ORG))
    ...     edges.append(Edge(here, "derived-from", CORPUS))

What the org is made of:

    >>> from dossier.composition import parts_of
    >>> made_of, stopped_early = parts_of(ORG, edges)
    >>> len(made_of)
    6
    >>> stopped_early
    False

`stopped_early` is the second value for a reason. The walk is depth-bounded,
because the graph is allowed to contain cycles and an unbounded walk over one is
a hang -- and a hang in a dashboard reads as a broken tool rather than as deep
work. A caller that dropped this flag would show a short list as if it were a
complete one.

    >>> from dossier.composition import DEPTH
    >>> DEPTH
    12

## The seam is not a part

`dossier` and `qmcp` are the human-in-the-loop pair. The harness runs things and
the panel shows them, they meet over HTTP, and **neither contains the other**.
Saying `part-of` here would be the easy mistake: it would claim that closing one
requires closing the other, and it would put a repository inside a repository
that does not hold it.

    >>> edges.append(Edge("quaternionmedia/dossier/delta/the-work",
    ...                   "crosses",
    ...                   "quaternionmedia/qmcp/delta/the-work"))
    >>> RELATIONS["crosses"]
    'both must happen, they interact at one point, and neither contains the other'

`crosses` is symmetric, and that is a property of what it means rather than a
convenience -- there is no direction in which one of them is the crosser.

    >>> from dossier.composition import SYMMETRIC
    >>> "crosses" in SYMMETRIC
    True

## What has no inverse, and why that matters here

    >>> from dossier.composition import INVERSES
    >>> INVERSES["part-of"]
    'contains'
    >>> INVERSES["derived-from"] is None
    True

A composed project reads `part-of` backwards freely: the org **contains** its
repositories. It cannot read `derived-from` backwards, because the corpus is not
"the origin of" anything in a sense the corpus has to carry. A page that invented
the inverse would have the constitution asserting a relationship to six
repositories that nobody wrote down.

## A cycle is reported, never broken

The workspace has a real one. The corpus governs the panel; the panel pins the
corpus; the corpus's roster names the panel.

    >>> knot = [
    ...     Edge(CORPUS, "blocks", "quaternionmedia/dossier/delta/the-work"),
    ...     Edge("quaternionmedia/dossier/delta/the-work", "blocks",
    ...          "quaternionmedia/qm/delta/the-roster"),
    ...     Edge("quaternionmedia/qm/delta/the-roster", "blocks", CORPUS),
    ... ]
    >>> from dossier.composition import tangles
    >>> found = tangles(knot)
    >>> len(found)
    1
    >>> len(found[0].addresses)
    3

`only` says what the knot is made of, because a cycle of `blocks` and a cycle of
`same-as` are different findings a reader should not have to reconstruct:

    >>> found[0].only
    'blocks'

Nothing was deleted to produce that answer:

    >>> "Nothing here has been changed." in __import__(
    ...     "dossier.composition", fromlist=["x"]).render_tangles(found)
    True

## The vocabulary is closed

A sixth relation is a change to a record, not a change to a string. That is what
stops a typo becoming a category:

    >>> from dossier.composition import check_relation
    >>> check_relation("part-of") is None
    True
    >>> print(check_relation("contains"))
    'contains' is not a relation. The five are: blocks, crosses, derived-from, part-of, same-as. Adding a sixth is a change to governance/qm/records/DRAFT-deltas-compose.md, not to a string.

`contains` is the interesting rejection: it is a real inverse in `INVERSES`, and
it is still not something anybody may *state*. One direction is written down and
the other is read off it, so the two can never disagree.

## What this page cannot show you

Whether the six repositories agree about anything. They pin the corpus at six
different commits, and this page's addresses are the same whatever those commits
are. `tests/e2e/test_workspace_composition.py` reads the real pins when the
sibling clones are present and says so when they are not -- because an address
denotes without existing, and that is the property that lets this page be
written at all.
