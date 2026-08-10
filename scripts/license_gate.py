#!/usr/bin/env python3
"""Dependency-licence gate for dossier.

The open-license record's section 4, wired along the one runtime path this
project presents: a Python package ecosystem. dossier builds no container
image, so the SBOM-per-image obligation does not arise; if that changes, this
gate stays and an SBOM gate is added beside it rather than replacing it.

Three things that clause requires and that a naive checker skips:

* The report is **generated**, never hand-compiled. It reads the metadata of
  what is actually installed, via importlib.metadata, rather than parsing a
  manifest and hoping the environment matches it.
* Declarations are **normalized to SPDX identifiers before comparison**. The
  same licence reaches this script in several spellings -- `MIT` and
  `MIT License`, `Apache-2.0` and `Apache Software License` -- and a gate
  comparing raw strings against an allowlist fails honest packages.
* An **unresolvable or absent declaration is a failure to investigate, never
  a pass**. That is the whole reason UNRESOLVED exists below rather than a
  fallback to "probably fine".

A licence the FSF recognises as free but OSI has not reviewed is permitted by
the record's section 1 and absent from this allowlist, so it fails here. That
failure is correct: it is the signal to adjudicate at org level, which is an
amendment to the record adding the identifier, never a local exception.

Run the gate:      python scripts/license_gate.py
Prove it can fail: python scripts/license_gate.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import metadata

# OSI-approved identifiers cleared for this project. Extending this list is an
# amendment to the org record, not a local edit -- see the module docstring.
ALLOWLIST = {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC0-1.0",
    "ISC",
    "MIT",
    "MPL-2.0",
    "PSF-2.0",
    "Python-2.0",
}

# Observed spellings that are not SPDX identifiers, mapped to the identifier
# they mean. Anything absent from here and from ALLOWLIST is UNRESOLVED, which
# fails. Add a row only when the package's own licence text has been read --
# guessing here is how a gate starts passing things nobody checked.
SPELLINGS = {
    "apache software license": "Apache-2.0",
    "bsd license": "BSD-3-Clause",
    "mit license": "MIT",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "python software foundation license": "PSF-2.0",
    "the unlicense (unlicense)": "Unlicense",
}

UNRESOLVED = "UNRESOLVED"


def normalize(declaration: str | None) -> str:
    """Map a raw licence declaration onto an SPDX identifier.

    Returns UNRESOLVED rather than guessing. A compound expression is kept
    whole when every operand resolves, so `MIT AND Python-2.0` stays a single
    auditable string instead of silently collapsing to its first half.
    """
    if not declaration:
        return UNRESOLVED
    raw = declaration.strip()
    if not raw or raw.lower() in {"unknown", "none"}:
        return UNRESOLVED
    if " AND " in raw or " OR " in raw:
        parts = [normalize(p) for p in raw.replace(" OR ", " AND ").split(" AND ")]
        return raw if all(p != UNRESOLVED for p in parts) else UNRESOLVED
    if raw in ALLOWLIST:
        return raw
    return SPELLINGS.get(raw.lower(), UNRESOLVED)


def declared(dist: metadata.Distribution) -> str | None:
    """Read a distribution's licence, newest metadata field first.

    License-Expression is already SPDX. License is free text. The classifier
    is the deprecated path an ecosystem still permits, and the record requires
    reading it rather than treating its absence from the modern field as null.
    """
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    plain = meta.get("License")
    if plain and len(plain) < 60 and "\n" not in plain:
        return plain
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.rsplit(" :: ", 1)[-1]
    return None


def collect() -> list[dict[str, str]]:
    rows = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or "<unnamed>"
        raw = declared(dist)
        rows.append(
            {
                "name": name,
                "version": dist.version,
                "declared": raw or "",
                "spdx": normalize(raw),
            }
        )
    return sorted(rows, key=lambda r: r["name"].lower())


def evaluate(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Every row whose identifier is not wholly inside the allowlist."""
    bad = []
    for row in rows:
        spdx = row["spdx"]
        if spdx == UNRESOLVED:
            bad.append(row)
            continue
        operands = spdx.replace(" OR ", " AND ").split(" AND ")
        if any(op.strip() not in ALLOWLIST for op in operands):
            bad.append(row)
    return bad


SELFTEST_CASES = [
    # (declaration, expected identifier, expected to fail the gate)
    ("MIT", "MIT", False),
    ("MIT License", "MIT", False),
    ("Apache Software License", "Apache-2.0", False),
    ("BSD License", "BSD-3-Clause", False),
    ("MIT AND Python-2.0", "MIT AND Python-2.0", False),
    # The cases that must report bad. A gate only ever seen green has not been
    # tested; it has been watched.
    ("Business Source License 1.1", UNRESOLVED, True),
    ("SSPL-1.0", UNRESOLVED, True),
    ("Elastic License 2.0", UNRESOLVED, True),
    ("UNKNOWN", UNRESOLVED, True),
    ("", UNRESOLVED, True),
    (None, UNRESOLVED, True),
    # Resolvable, OSI-approved, and still outside this project's allowlist:
    # the adjudication case the record describes, which must fail rather than
    # pass quietly.
    ("GPL-3.0-or-later", UNRESOLVED, True),
]


def selftest() -> int:
    failures = 0
    for declaration, expected, should_fail in SELFTEST_CASES:
        got = normalize(declaration)
        row = [{"name": "fixture", "version": "0", "declared": "", "spdx": got}]
        rejected = bool(evaluate(row))
        if got != expected or rejected != should_fail:
            failures += 1
            print(
                f"  FAIL {declaration!r}: identifier {got!r} (want {expected!r}), "
                f"rejected={rejected} (want {should_fail})"
            )
    total = len(SELFTEST_CASES)
    if failures:
        print(f"license gate selftest: {failures}/{total} case(s) failed")
        return 1
    print(f"license gate selftest: {total}/{total} cases pass, "
          f"{sum(1 for c in SELFTEST_CASES if c[2])} of them reporting bad")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", metavar="PATH", help="write the report here")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the normalizer against fixtures, including ones that must fail",
    )
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    rows = collect()
    if not rows:
        # An empty scan is the failure mode this corpus keeps finding: a check
        # that is green because its query returned nothing.
        print("license gate: no distributions found -- refusing to report a pass")
        return 1

    bad = evaluate(rows)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"scanned": rows, "rejected": bad}, handle, indent=2)

    print(f"license gate: {len(rows)} distribution(s) scanned")
    if bad:
        print(f"license gate: {len(bad)} outside the allowlist or unresolvable\n")
        for row in bad:
            shown = row["declared"] or "<no declaration>"
            print(f"  {row['name']} {row['version']}: {shown} -> {row['spdx']}")
        print(
            "\nAn unresolvable declaration is a failure to investigate, never a "
            "pass. An OSI licence outside the allowlist is adjudicated by "
            "amending the org record, never by a local exception."
        )
        return 1

    used = sorted({r["spdx"] for r in rows})
    print(f"license gate: clean. Identifiers in use: {', '.join(used)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
