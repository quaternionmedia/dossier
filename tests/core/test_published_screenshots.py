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
        found |= {Path(m).name for m in
                  re.findall(r"[\w./-]*screenshots/([\w.-]+\.svg)", text)}
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


def test_every_picture_a_page_ships_is_committed():
    """An image the docs site cannot fetch is a broken page.

    Mutation: point the README at a screenshot that is generated but not
    force-added past `.gitignore` and this fails.
    """
    missing = sorted(_referenced() - _committed())
    assert not missing, f"referenced by a page, not committed: {missing}"


def test_every_committed_picture_is_one_a_page_ships():
    """The other direction. A committed screenshot nothing references is a
    file somebody has to decide about later with no way to know why it is
    there.

    Mutation: force-add a screenshot no page names and this fails.
    """
    orphans = sorted(_committed() - _referenced())
    assert not orphans, f"committed and referenced by nothing: {orphans}"


def test_every_committed_picture_is_one_the_suite_records():
    """A file nothing regenerates goes stale silently, which is the whole
    failure above.

    Either it is a tab shot the view registry names, or it is one of the
    recordings declared in `NOT_A_VIEW`. There is no third kind.

    Mutation: commit a screenshot with a name matching neither and this fails.
    """
    known = {view.name for view in views.VIEWS}
    unexplained = []
    for name in _committed():
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
