"""Disk-status documents, in the shape `ci/disk_status.py` writes them.

Shared because two categories need them: the store tests read these documents
and the view tests render what the store loaded. One test file importing
another put a fixture's home wherever it happened to be written first, and the
import broke the moment the suite was organised.
"""

from __future__ import annotations

import json
from pathlib import Path


def document(
    tmp_path: Path,
    generated_at: str = "2026-08-11T00:00:00Z",
    volumes=None,
    targets=None,
    name: str = "disk-status.json",
) -> Path:
    """A disk status document, in the shape ci/disk_status.py writes."""
    payload = {
        "schema": 1,
        "generated_at": generated_at,
        "generator": {"tool": "ci/disk_status.py", "policy": "ci/disk-policy.yaml"},
        "reading": {"staleness_budget_hours": 6},
        "totals": {
            "volumes_critical": 1,
            "volumes_warn": 0,
            "volumes_unknown": 0,
            "targets_measured": 1,
            "targets_unknown": 0,
            "reclaimable_bytes": {
                "refetched": 100, "rebuilt": 0, "destructive": 0
            },
        },
        "volumes": volumes if volumes is not None else [
            {
                "path": "C:\\", "total_bytes": 1000, "used_bytes": 900,
                "free_bytes": 100, "free_ratio": 0.1, "state": "warn",
                "severity": "critical", "thresholds_fired": ["under the floor"],
            }
        ],
        "targets": targets if targets is not None else [
            {
                "name": "cache", "title": "A cache", "kind": "directory_contents",
                "safety": "refetched", "owner": "something",
                "measured": {
                    "bytes": 500, "files": 5, "units_total": 1, "unreadable": 0,
                    "units": [{"path": "C:/cache/big", "bytes": 500}],
                },
            }
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def unknown_target(name: str = "cache", reason: str = "daemon not running") -> dict:
    return {
        "name": name, "title": "A cache", "kind": "command",
        "safety": "rebuilt", "owner": "something",
        "measured": {"unknown": reason},
    }


def measured_target(name: str = "cache", size: int = 500) -> dict:
    return {
        "name": name, "title": "A cache", "kind": "directory_contents",
        "safety": "refetched", "owner": "something",
        "measured": {
            "bytes": size, "files": 1, "units_total": 1, "unreadable": 0,
            "units": [{"path": f"C:/{name}", "bytes": size}],
        },
    }


