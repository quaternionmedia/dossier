#!/usr/bin/env python3
"""
Lint for mojibake and ASCII issues in text files.

Default mode flags common mojibake characters (e.g., "â", "Ã", "ð", "ï", "�").
Use --strict to flag any non-ASCII characters.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


DEFAULT_EXTS = {
    ".py",
    ".md",
    ".toml",
    ".ini",
    ".txt",
    ".yml",
    ".yaml",
    ".json",
    ".css",
    ".scss",
}

IGNORE_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
}

MOJIBAKE_CHARS = {"â", "Ã", "ð", "ï", "�"}


def iter_files(paths: list[Path], exts: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            if path.suffix in exts:
                files.append(path)
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*"):
            if candidate.is_dir():
                if candidate.name in IGNORE_DIRS:
                    # Skip ignored directories
                    for _ in []:
                        pass
                continue
            if candidate.suffix in exts:
                files.append(candidate)
    return files


def find_issues(text: str, strict: bool) -> list[tuple[int, int, str]]:
    issues: list[tuple[int, int, str]] = []
    lines = text.splitlines()
    if strict:
        for line_no, line in enumerate(lines, start=1):
            for col, ch in enumerate(line, start=1):
                if ord(ch) > 127:
                    issues.append((line_no, col, ch))
    else:
        for line_no, line in enumerate(lines, start=1):
            for col, ch in enumerate(line, start=1):
                if ch in MOJIBAKE_CHARS:
                    issues.append((line_no, col, ch))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint for mojibake/ASCII issues.")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Paths to scan (default: current directory).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Flag any non-ASCII characters.",
    )
    parser.add_argument(
        "--ext",
        action="append",
        default=[],
        help="File extension to include (repeatable).",
    )
    args = parser.parse_args()

    exts = set(DEFAULT_EXTS)
    for ext in args.ext:
        if not ext.startswith("."):
            ext = "." + ext
        exts.add(ext)

    paths = [Path(p) for p in args.paths]
    files = iter_files(paths, exts)
    files.sort()

    total_issues = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        issues = find_issues(text, strict=args.strict)
        if not issues:
            continue
        total_issues += len(issues)
        print(f"{path}")
        for line_no, col, ch in issues[:200]:
            escaped = ch.encode("unicode_escape").decode("ascii")
            print(f"  L{line_no}:C{col} {escaped}")
        if len(issues) > 200:
            print(f"  ... {len(issues) - 200} more")

    if total_issues:
        print(f"Found {total_issues} issue(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
