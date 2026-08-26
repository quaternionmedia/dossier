"""Every picture the docs ship is a picture of something that still exists.

**A SCREENSHOT OF A DELETED VIEW LOOKS EXACTLY LIKE A CURRENT ONE.** The README
shipped `tab_prs_desktop.svg` for eight months after the Pull Requests tab was
merged into On deck: the file was on disk, committed, and referenced, and
nothing regenerated it because the test that draws it no longer had a tab to
draw. Every signal said fine.

That is the artefact-you-did-not-create failure in its plainest form. The
picture is generated, the page is hand-written, and the only thing joining them
is a filename -- so the join is what has to be checked.

WHAT THIS CANNOT DO. Look at the image. A screenshot of the right tab showing
the wrong thing passes here, and no cheap check finds that. What it can do is
refuse a filename that names a view the application does not have.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from dossier import views

SHOTS = Path("docs/screenshots")
PAGES = [Path("README.md"), *sorted(Path("docs").glob("*.md"))]

# Recordings that are not one view: the ring at each depth, a modal, the
# content viewer. Named here because they have no registry to derive from, and
# a name that stops being recorded fails `test_every_shipped_picture_is_here`.
NOT_A_VIEW = frozenset({
    "rad_ring_top_level", "rad_ring_one_level_in", "rad_ring_two_levels_in",
    "dashboard_help", "dashboard_settings", "content_viewer_readme",
})


def _committed() -> set[str]:
    out = subprocess.run(["git", "ls-files", str(SHOTS)],
                         capture_output=True, text=True, encoding="utf-8")
    return {Path(line).name for line in out.stdout.splitlines() if line.strip()}


def _referenced() -> set[str]:
    found: set[str] = set()
    for page in PAGES:
        if not page.is_file():
            continue
        text = page.read_text(encoding="utf-8")
        # **`.svg` ONLY WAS A HOLE THE MOMENT THE GIFS ARRIVED.** The pattern
        # named one extension, so every narrative a page embedded was
        # referenced by nobody as far as these checks could tell.
        found |= {Path(m).name for m in
                  re.findall(r"[\w./-]*screenshots/([\w.-]+\.(?:svg|gif))",
                             text)}
    return found


def test_no_committed_picture_names_a_view_that_is_gone():
    """THE ONE THIS EXISTS FOR.

    `tab_prs_desktop.svg` outlived the Pull Requests tab by eight months.

    Mutation: commit a `tab_<something>_desktop.svg` for a view the registry
    does not hold and this fails.
    """
    known = {view.name for view in views.VIEWS}
    stale = []
    for name in _committed():
        match = re.fullmatch(r"tab_([a-z]+)_(compact|desktop|wide)\.svg", name)
        if match and match.group(1) not in known:
            stale.append(name)
    assert not stale, f"pictures of views that no longer exist: {stale}"


def _generated() -> set[str]:
    """Pictures the docs build records, so they need not be committed."""
    from dossier.narratives import NARRATIVES

    return {narrative.path.name for narrative in NARRATIVES}


def test_every_picture_a_page_ships_is_committed_or_generated():
    """An image nothing produces is a broken page.

    **TWO WAYS TO BE PRODUCED NOW, AND THE DIFFERENCE IS WHO BUILDS.** A
    picture is either committed -- the README's, because GitHub renders it and
    builds nothing -- or recorded by `mkdocs build` through
    `hooks/pictures.py`. Anything else is referenced by a page and made by
    nobody.

    Mutation: point a page at `screenshots/nothing.gif` and this fails.
    """
    missing = sorted(_referenced() - _committed() - _generated())
    assert not missing, (
        f"referenced by a page, and neither committed nor recorded by a "
        f"narrative: {missing}")


def test_every_committed_picture_is_one_a_page_ships():
    """A committed screenshot nothing references is a file somebody has to
    decide about later with no way to know why it is there.

    Mutation: force-add a screenshot no page names and this fails.
    """
    orphans = sorted(_committed() - _referenced())
    assert not orphans, f"committed and referenced by nothing: {orphans}"


def test_every_narrative_is_shown_somewhere():
    """A picture nobody embeds is a picture nobody looks at.

    The other direction of the same join: `shown_in` is a claim, and this is
    what makes it one that can be wrong.
    """
    from dossier.narratives import NARRATIVES

    referenced = _referenced()
    unshown = [n.name for n in NARRATIVES if n.path.name not in referenced]
    assert not unshown, f"recorded and embedded by no page: {unshown}"


def test_a_narrative_names_the_pages_that_embed_it():
    """`shown_in` and the pages must agree, or one of them is out of date."""
    from dossier.narratives import NARRATIVES

    wrong = []
    for narrative in NARRATIVES:
        for page in narrative.shown_in:
            text = Path(page).read_text(encoding="utf-8", errors="replace")
            if narrative.path.name not in text:
                wrong.append(f"{narrative.name} says it is shown in {page}, "
                             f"and that page does not embed it")
    assert not wrong, "\n".join(wrong)


def test_only_the_readme_s_narrative_is_committed():
    """**THE WHOLE POINT OF GENERATING THEM WHERE THEY ARE SERVED.**

    A committed picture is one somebody has to remember to regenerate, and the
    `.gitignore` comment this replaced said what that cost: a regenerated one
    is invisible until somebody remembers. Only the README's has to be in the
    tree, because GitHub builds nothing.
    """
    from dossier.narratives import NARRATIVES

    committed = _committed()
    for narrative in NARRATIVES:
        present = narrative.path.name in committed
        assert present == narrative.committed, (
            f"{narrative.name}: committed={present}, declared "
            f"committed={narrative.committed}")


def test_every_committed_picture_is_one_the_suite_records():
    """A file nothing regenerates goes stale silently, which is the whole
    failure above.

    Either it is a tab shot the view registry names, or it is one of the
    recordings declared in `NOT_A_VIEW`. There is no third kind.

    Mutation: commit a screenshot with a name matching neither and this fails.
    """
    known = {view.name for view in views.VIEWS}
    narratives = _generated()
    unexplained = []
    for name in _committed():
        # A committed narrative is regenerated by the test suite, which is what
        # makes a change to it show up in `git status` rather than waiting for
        # somebody to remember.
        if name in narratives:
            continue
        stem = name.removesuffix(".svg")
        if stem in NOT_A_VIEW:
            continue
        match = re.fullmatch(r"tab_([a-z]+)_(compact|desktop|wide)", stem)
        if match and match.group(1) in known:
            continue
        unexplained.append(name)
    assert not unexplained, (
        f"nothing regenerates these, so nothing will notice them going "
        f"stale: {unexplained}")


def test_the_declared_recordings_are_actually_recorded():
    """`NOT_A_VIEW` is a hand-kept list, so it gets the same treatment as any
    other: a name in it that nothing writes is a declaration guarding nothing.

    Only the committed ones are checked -- the rest are generated behind
    `--screenshots` and are absent on an ordinary run, which is a different
    fact from missing.
    """
    committed = _committed()
    for stem in NOT_A_VIEW:
        name = f"{stem}.svg"
        if name in committed:
            assert (SHOTS / name).is_file(), f"{name} is committed and not here"


# --- the generator that draws them ----------------------------------------------


def _generator() -> str:
    """The screenshot generator's source, with comments and docstrings removed.

    **STRIPPED, BECAUSE THE FIRST VERSION MATCHED ITS OWN EXPLANATION.** The
    generator carries a comment describing the `tab-projects` and `#main-tabs`
    defects, and a check reading the raw text found those words there and
    reported as broken the thing it was written to confirm was fixed. The same
    trap `governance/qm` item 10 records: a text scan matching the docstring
    that forbade the thing.

    Layout is preserved rather than tokenised. A token stream joined back
    together cannot be searched for a line of code, which the tokenising
    version could not do and passed nothing.
    """
    source = Path("tests/ui/test_tui.py").read_text(encoding="utf-8")
    source = re.sub(r'"""[\s\S]*?"""', "", source)
    return "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))


def test_the_generator_draws_every_view_the_registry_holds():
    """**THE ONE THAT MADE THIRTY-THREE PICTURES OF ONE SCREEN.**

    The tab list was written by hand. It held `tab-projects`, a tab the
    application had removed, and was missing eight views added since --
    Overview, Sweep, Outstanding, Governance, Disk, Topology, Harness and
    Threads. Deriving it from `views.VIEWS` is what stops a view being added
    and never drawn.

    Mutation: replacing the derivation with a literal list fails here.
    """
    source = _generator()

    assert "TABS = [(view.tab, view.title) for view in views.VIEWS]" in source, (
        "the screenshot generator no longer derives its tabs from the registry")
    assert '"tab-projects"' not in source, (
        "the generator names a tab the application does not have")


def test_the_generator_asserts_the_tab_it_asked_for():
    """A swallowed switch publishes a confident wrong picture.

    `query_one("#main-tabs")` raised `NoMatches` on the first line of the
    switch -- there is one `TabbedContent` here and it is `#project-tabs` --
    and `except Exception: pass` absorbed it, for every tab at every
    resolution. `tab_issues_desktop.svg`, `tab_contributors_desktop.svg` and
    `tab_deltas_desktop.svg` came out byte-identical, and the third is
    committed and shipped.

    P17: a bound that fires is reported, never absorbed.
    """
    source = _generator()

    assert '"#main-tabs"' not in source, (
        "the generator queries a container this application does not have")
    assert "wrong tab" in Path("tests/ui/test_tui.py").read_text(
        encoding="utf-8"), (
        "the generator no longer asserts that the switch took effect")


def test_the_committed_pictures_are_not_all_the_same_picture():
    """Two views drawn identically is the failure with no other symptom.

    Cheap, and it would have caught the whole class: the broken generator
    produced one image under eleven names.
    """
    import hashlib

    seen: dict[str, str] = {}
    for name in sorted(_committed()):
        if not re.fullmatch(r"tab_[a-z]+_(compact|desktop|wide)\.svg", name):
            continue
        digest = hashlib.sha256(
            (SHOTS / name).read_bytes()).hexdigest()
        if digest in seen:
            raise AssertionError(
                f"{name} and {seen[digest]} are the same image byte for byte; "
                f"at least one of them is a picture of the wrong view")
        seen[digest] = name
