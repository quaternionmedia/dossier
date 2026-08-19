"""Turn a GitHub rate limit into an instruction instead of a traceback.

WHY THIS EXISTS. A fresh setup ran `dossier github sync` and got an
`httpx.HTTPStatusError` with a stack trace ending in `_request_with_retry`.
Every frame of it was accurate and none of it said the two things a reader
needs: that unauthenticated GitHub allows sixty requests an hour, and that a
token raises it to five thousand.

The limit is not a defect and cannot be fixed in code. What can be fixed is
that the program reported it as a crash.

WHAT COUNTS AS THIS ERROR. The parser raises `HTTPStatusError` for rate limits
and for other statuses alike, so the text is matched rather than the type. A
match that is too broad would swallow a real HTTP failure and tell somebody to
set a token that would not help, so it looks for the phrase the parser itself
writes.
"""

from __future__ import annotations

import os
import re

RATE_LIMIT_MARKER = "rate limit exceeded"

# Unauthenticated GitHub allows this many requests an hour; a token allows the
# larger figure. Both are GitHub's published limits and are named here so the
# advice can state what the token buys rather than just asking for one.
ANONYMOUS_PER_HOUR = 60
AUTHENTICATED_PER_HOUR = 5000


def is_rate_limit(error: BaseException) -> bool:
    return RATE_LIMIT_MARKER in str(error).lower()


def seconds_until_reset(error: BaseException) -> int | None:
    match = re.search(r"resets in\s+(\d+)", str(error), re.I)
    return int(match.group(1)) if match else None


def has_token(env: dict[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get("GITHUB_TOKEN") or env.get("GH_TOKEN"))


def advice(error: BaseException, env: dict[str, str] | None = None) -> str:
    """What to tell somebody whose sync stopped.

    Two different situations wear the same error. Without a token the fix is to
    set one and the sync becomes possible; with a token the limit is real and
    the only remedy is to wait, so saying "set a token" there would be advice
    that cannot work.
    """
    seconds = seconds_until_reset(error)
    when = ""
    if seconds is not None:
        minutes = max(1, round(seconds / 60))
        when = f" It resets in about {minutes} minute(s)."

    if has_token(env):
        return (
            "GitHub's rate limit for your token is used up." + when +
            "\nNothing is wrong with the sync: it stops here and resumes when "
            "you run it again. Already-synced repositories are kept."
        )
    return (
        "GitHub's rate limit for unauthenticated requests is used up." + when +
        f"\nUnauthenticated requests are limited to {ANONYMOUS_PER_HOUR} an hour; "
        f"with a token the limit is {AUTHENTICATED_PER_HOUR}."
        "\n\nSet one and run the same command again:"
        "\n    export GITHUB_TOKEN=$(gh auth token)      # if you use the gh CLI"
        "\n    export GITHUB_TOKEN=<a personal access token>"
        "\n\nAlready-synced repositories are kept, so a re-run continues rather "
        "than starting over."
    )
