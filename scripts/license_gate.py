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
from pathlib import Path

# OSI-approved identifiers cleared for this project. Extending this list is an
# amendment to the org record, not a local edit -- see the module docstring.
# **THE ALLOWLIST IS GENERATED, NOT TYPED HERE.** `scripts/allowlist.json` is
# written by `scripts/spdx_allowlist.py` from SPDX's own data: the union of
# `osi_approved` and `fsf_libre`, deprecated identifiers excluded, which is
# exactly what the record's section 1 admits.
#
# It replaced nine identifiers written in by hand, and the hand-kept list was
# wrong in both directions. Too narrow: section 1 admits a hundred and
# eighty-two, so every honest dependency outside the nine failed and needed an
# individual adjudication. Too wide: it held `PSF-2.0`, which SPDX marks
# neither OSI-approved nor FSF-libre, so the gate was admitting an identifier
# the record does not.
#
# Read at import rather than embedded, so the file and the gate cannot drift.
def _admitted() -> frozenset[str]:
    import json

    path = Path(__file__).resolve().parent / "allowlist.json"
    if not path.is_file():
        raise SystemExit(
            f"{path.name} is missing. It is generated:\n"
            f"  uv run --with spdx-license-list python "
            f"scripts/spdx_allowlist.py --write")
    return frozenset(json.loads(path.read_text(encoding="utf-8"))["admitted"])


ALLOWLIST = _admitted()

# Observed spellings that are not SPDX identifiers, mapped to the identifier
# they mean. Anything absent from here and from ALLOWLIST is UNRESOLVED, which
# fails. Add a row only when the package's own licence text has been read --
# guessing here is how a gate starts passing things nobody checked.
SPELLINGS = {
    "apache software license": "Apache-2.0",
    "bsd license": "BSD-3-Clause",
    "mit license": "MIT",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    # **READ BEFORE IT WAS ADDED, WHICH IS THE RULE ABOVE.** `typing_extensions`
    # declares `PSF-2.0`, an identifier on neither list, and ships the full
    # Python licence stack: PSF License Version 2, followed by the BeOpen,
    # CNRI and CWI agreements. That composite is what SPDX calls `Python-2.0`,
    # which is both OSI-approved and FSF-libre. `PSF-2.0` names one clause of
    # it.
    #
    # So this is a spelling, not an exception: the package is honest and its
    # metadata is imprecise, which is the case the record's section 4 describes
    # when it says a gate comparing raw strings fails honest packages.
    "psf-2.0": "Python-2.0",
    "python software foundation license": "Python-2.0",
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


def runtime_closure() -> set[str] | None:
    """Every distribution reachable from this project's runtime dependencies.

    **SECTION 1 BINDS A DEPLOYED RUNTIME PATH, AND THE ENVIRONMENT IS NOT ONE.**
    Reading `metadata.distributions()` scans the whole virtualenv -- pytest,
    ruff, the docs toolchain -- which passed for a long time only because those
    happened to be MIT or BSD. The risk the record is about is a clause in
    somebody else's contract embedded in *our stack*: a library that draws
    documentation on a developer's machine is not in anything shipped, and if
    it relicensed tomorrow nothing deployed would change.

    Returns `None` when the closure cannot be established -- an unreadable
    manifest, a dependency not installed. **A closure nobody could compute is
    not an empty one**, and the caller falls back to scanning everything rather
    than quietly checking a smaller set than it claims.

    WHAT IT CANNOT SEE. A dependency imported at runtime and declared nowhere.
    That is a packaging defect rather than a licence one, and this reports the
    manifest it was given.
    """
    import tomllib

    manifest = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not manifest.is_file():
        return None
    try:
        declared_deps = tomllib.loads(
            manifest.read_text(encoding="utf-8"))["project"]["dependencies"]
    except (KeyError, ValueError):
        return None

    from packaging.requirements import Requirement

    def parse(raw: str):
        try:
            return Requirement(raw)
        except Exception:                              # noqa: BLE001
            return None

    seen: set[str] = set()
    queue: list[tuple[str, bool]] = []
    for raw in declared_deps:
        parsed = parse(raw)
        if parsed is None:
            return None
        queue.append((parsed.name.lower().replace("_", "-"), False))

    while queue:
        name, gated = queue.pop()
        if not name or name in seen:
            continue
        try:
            requires = metadata.requires(name) or []
        except metadata.PackageNotFoundError:
            # **A GATED REQUIREMENT THAT IS ABSENT IS NOT A HOLE.**
            # `importlib-metadata`, `exceptiongroup` and `tomli` are all
            # declared for older interpreters and correctly not installed on
            # this one. Treating them as a broken closure made the gate fall
            # back to scanning the whole environment, which is the thing this
            # function exists to stop.
            #
            # An *ungated* requirement that is missing is a real hole, and the
            # closure is refused rather than quietly shrunk.
            if gated:
                continue
            return None
        seen.add(name)
        for raw in requires:
            parsed = parse(raw)
            if parsed is None:
                return None
            marker = parsed.marker
            # An extra's dependencies arrive only when the extra is asked for,
            # and nothing here asks for one.
            if marker is not None and "extra" in str(marker):
                continue
            applies = marker is None or marker.evaluate()
            if not applies:
                continue
            queue.append((parsed.name.lower().replace("_", "-"),
                          marker is not None))
    return seen


def collect(runtime_only: bool = True) -> list[dict[str, str]]:
    """Every distribution the gate judges, and what it declares.

    `runtime_only` narrows to `runtime_closure()`. When that cannot be
    computed the whole environment is scanned instead, which is the safe
    direction: it reports more than the record binds rather than less.
    """
    closure = runtime_closure() if runtime_only else None
    rows = []
    for dist in metadata.distributions():
        if closure is not None:
            name = (dist.metadata.get("Name") or "").lower().replace("_", "-")
            if name not in closure:
                continue
        name = dist.metadata.get("Name") or "<unnamed>"
        raw = declared(dist)  # noqa: E501
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
    # **COPYLEFT IS ADMITTED, AND THIS IS WHERE THAT IS ASSERTED.** Section 1
    # says so outright -- "copyleft is explicitly acceptable and contractually
    # handled, never technically avoided" -- and the hand-kept allowlist did
    # avoid it technically, by holding nine permissive identifiers and nothing
    # else. This case failed the day the allowlist started encoding what the
    # record actually admits, which is how the gap was found.
    ("GPL-3.0-or-later", "GPL-3.0-or-later", False),
    ("AGPL-3.0-only", "AGPL-3.0-only", False),
    # Permissive, widely used, and on neither list. Being reasonable is not the
    # criterion: section 1 names two lists, and `MIT-CMU` is in neither.
    ("MIT-CMU", UNRESOLVED, True),
    # `PSF-2.0` is on neither list *as an identifier*, and the package
    # declaring it ships the full Python licence stack, which is `Python-2.0`
    # and is on both. Normalising it is reading the text, not making an
    # exception -- and this asserts the difference: it resolves, and it
    # resolves to the licence the file actually contains.
    ("PSF-2.0", "Python-2.0", False),
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
