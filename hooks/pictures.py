"""Record every narrative while the site builds.

**THIS IS WHAT MAKES THE PICTURES DISPOSABLE.** Every screenshot used to be
force-added past a `.gitignore` wildcard by hand, and that file's own comment
said the cost out loud: *"a regenerated one is invisible until somebody
remembers"*. A picture nobody regenerates goes stale in silence -- which is how
this repository shipped a picture of a deleted tab for eight months, and how
thirty-three pictures of one screen went out under eleven names.

Recording them here means the pictures a reader sees were made from the
application at the commit being built. There is nothing to remember.

**A BUILD THAT CANNOT DRAW SAYS SO AND STOPS.** An earlier instinct was to
carry on and let the pages ship with broken images, on the grounds that a docs
build should not fail over a picture. That is exactly backwards: a missing
image is visible to every reader and invisible to whoever built it, and the
build is the last place it can be caught cheaply.

WHAT IT CANNOT SEE. Whether a narrative is worth showing, or whether its steps
are in the right order. It records what `dossier.narratives` declares.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger("mkdocs.hooks.pictures")


def on_pre_build(config, **kwargs) -> None:
    """Draw the narratives before mkdocs copies `docs/` into the site.

    `on_pre_build` and not `on_files`: the files have to exist before mkdocs
    takes its inventory, or the pictures are written into a directory the build
    has already finished reading.
    """
    from dossier.narratives import NARRATIVES, record

    root = Path(config["docs_dir"]).parent

    async def draw() -> None:
        for narrative in NARRATIVES:
            written = await record(narrative, root=root)
            log.info("recorded %s (%s frames) -> %s", narrative.name,
                     len(narrative.steps), written)

    try:
        asyncio.run(draw())
    except Exception as error:                          # noqa: BLE001
        # Re-raised rather than logged and swallowed. A build that carried on
        # would publish pages whose images are missing, and the person who ran
        # it would see a green build.
        raise RuntimeError(
            f"the narrative pictures could not be recorded, so the site would "
            f"ship with broken images: {error}") from error
