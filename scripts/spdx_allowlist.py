#!/usr/bin/env python3
"""Generate the licence allowlist from SPDX's own data.

    uv run --with spdx-license-list python scripts/spdx_allowlist.py --write

**GENERATED, NEVER HAND-COMPILED**, which is the rule the record already
applies to the licence report itself. The allowlist this replaced held nine
identifiers typed in by hand against a criterion -- section 1's "OSI-approved
or FSF-free" -- that admits a hundred and eighty-two. Every honest dependency
outside those nine failed the gate and needed an individual adjudication, and
the list was wrong in the other direction too: it admitted `PSF-2.0`, which is
on neither list.

**THE OUTPUT IS COMMITTED, NOT COMPUTED AT RUN TIME.** Reading SPDX live would
mean the gate's verdict changed when a package updated, with no governance act
anywhere -- and section 4 is explicit that allowlist changes are amendments to
the record. So this writes a file with its provenance in it, regenerating
produces a diff, and a human ratifies the diff. That is the same shape as every
other generated document in this estate.

**WHAT IT ENCODES, AND WHAT IT DELIBERATELY DOES NOT.** Section 1 admits
OSI-approved *or* FSF-free, so this is the union of `osi_approved` and
`fsf_libre`. Deprecated identifiers are excluded: a deprecated id is one SPDX
asks people to stop writing, and admitting it would keep a spelling alive that
the ecosystem is retiring.

It encodes membership of two lists. It makes no judgement about whether a
licence is *suitable* -- section 1 already settled that copyleft is acceptable
and source-available is not, and a licence that is OSI-approved is admitted by
the record whether or not anybody likes it.

WHAT THIS CANNOT SEE. Whether SPDX is right. It is the authority this record
points at, and a licence it mislabels is mislabelled here too.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWLIST = HERE / "allowlist.json"


def build() -> dict:
    """The identifiers section 1 admits, with where they came from."""
    import spdx_license_list

    licences = spdx_license_list.LICENSES
    osi, fsf = [], []
    for identifier, licence in licences.items():
        if licence.deprecated_id:
            continue
        if licence.osi_approved:
            osi.append(identifier)
        if licence.fsf_libre:
            fsf.append(identifier)

    admitted = sorted(set(osi) | set(fsf))
    return {
        # Provenance, so a reader can tell what this is a copy of and when.
        # A generated file without it is a list somebody has to take on trust.
        "source": "spdx-license-list (SPDX License List data)",
        "criterion": (
            "records/DRAFT-open-license-exclusion-and-upstream-remediation.md "
            "section 1: OSI-approved or FSF-free, deprecated identifiers "
            "excluded"),
        "generated_on": date.today().isoformat(),
        "spdx_licences_considered": len(licences),
        "osi_approved": len(osi),
        "fsf_libre": len(fsf),
        "admitted": admitted,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true",
                        help="write scripts/allowlist.json")
    parser.add_argument("--check", action="store_true",
                        help="refuse if the committed file is not what this "
                             "would generate")
    args = parser.parse_args(argv)

    fresh = build()

    if args.check:
        if not ALLOWLIST.is_file():
            print(f"{ALLOWLIST.name} is missing. Run with --write.")
            return 1
        held = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
        # The date is not compared: regenerating on a different day is not a
        # change to what is admitted, and comparing it would make this fail
        # every day for no reason.
        if held.get("admitted") != fresh["admitted"]:
            added = sorted(set(fresh["admitted"]) - set(held.get("admitted", [])))
            gone = sorted(set(held.get("admitted", [])) - set(fresh["admitted"]))
            print("the committed allowlist is not what SPDX now says:")
            if added:
                print(f"  SPDX added: {', '.join(added)}")
            if gone:
                print(f"  SPDX no longer admits: {', '.join(gone)}")
            print("Regenerate with --write, and put the diff through the "
                  "record: allowlist changes are amendments.")
            return 1
        print(f"allowlist: {len(held['admitted'])} identifier(s), matching SPDX.")
        return 0

    if args.write:
        ALLOWLIST.write_text(json.dumps(fresh, indent=2) + "\n",
                             encoding="utf-8")
        print(f"wrote {ALLOWLIST.name}: {len(fresh['admitted'])} identifier(s) "
              f"({fresh['osi_approved']} OSI-approved, {fresh['fsf_libre']} "
              f"FSF-libre, union of both)")
        return 0

    print(f"{len(fresh['admitted'])} identifier(s) would be admitted. "
          f"--write to record them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
