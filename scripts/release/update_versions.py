from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_DISTS = {
    "flow": "fasthep-flow",
    "carpenter": "fasthep-carpenter",
    "curator": "fasthep-curator",
    "render": "fasthep-render",
    "cli": "fasthep-cli",
    "toolbench": "fasthep-toolbench",
    "workshop": "fasthep-workshop",
    "fasthep": "fasthep",
}

DEPENDENCY_KEYS = {
    "flow",
    "carpenter",
    "curator",
    "render",
    "cli",
    "toolbench",
    "workshop",
}


@dataclass(frozen=True, slots=True)
class Change:
    path: Path
    before: str
    after: str
    descriptions: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(description="Update FAST-HEP release versions.")
    parser.add_argument("release_file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--package", choices=sorted(PACKAGE_DISTS))
    args = parser.parse_args()

    root = Path.cwd()
    plan = _read_release(args.release_file)
    versions: dict[str, str] = dict(plan["packages"])
    selected = [args.package] if args.package else list(plan["order"])

    updates: dict[Path, Change] = {}
    for key in selected:
        path = root / key / "pyproject.toml"
        _queue_update(
            updates,
            path=path,
            description="package version",
            after=_update_package_version_text(path, _current_text(updates, path), versions[key]),
        )

    if args.package is None or args.package == "fasthep":
        path = root / "fasthep" / "pyproject.toml"
        _queue_update(
            updates,
            path=path,
            description="FAST-HEP dependency pins",
            after=_update_dependency_pins_text(_current_text(updates, path), versions),
        )
    if args.package is None or args.package == "workshop":
        path = root / "workshop" / "pyproject.toml"
        _queue_update(
            updates,
            path=path,
            description="FAST-HEP dependency pins",
            after=_update_dependency_pins_text(_current_text(updates, path), versions),
        )

    changes = list(updates.values())
    if not changes:
        print("No version changes needed.")
        return 0

    for change in changes:
        descriptions = ", ".join(change.descriptions)
        print(f"{'Would update' if args.dry_run else 'Updating'} {change.path}: {descriptions}")
        if not args.dry_run:
            change.path.write_text(change.after, encoding="utf-8")

    return 0


def _read_release(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("packages"), dict):
        raise SystemExit("releases.json must contain a packages object")
    if not isinstance(data.get("order"), list):
        raise SystemExit("releases.json must contain an order list")
    return data


def _current_text(updates: dict[Path, Change], path: Path) -> str:
    existing = updates.get(path)
    if existing is not None:
        return existing.after
    return path.read_text(encoding="utf-8")


def _queue_update(
    updates: dict[Path, Change],
    *,
    path: Path,
    description: str,
    after: str,
) -> None:
    current = updates.get(path)
    before = current.before if current is not None else path.read_text(encoding="utf-8")
    if before == after:
        return
    descriptions = list(current.descriptions) if current is not None else []
    if description not in descriptions:
        descriptions.append(description)
    updates[path] = Change(
        path=path,
        before=before,
        after=after,
        descriptions=descriptions,
    )


def _update_package_version_text(path: Path, text: str, version: str) -> str:
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"Could not parse {path}: {exc}") from exc

    project = parsed.get("project") or {}
    if isinstance(project, dict) and project.get("version") is not None:
        updated = re.sub(
            r'(?m)^version\s*=\s*"[^"]+"',
            f'version = "{version}"',
            text,
            count=1,
        )
        return updated

    return _set_hatch_fallback_version(text, version)


def _set_hatch_fallback_version(text: str, version: str) -> str:
    if re.search(r"(?m)^fallback_version\s*=", text):
        return re.sub(
            r'(?m)^fallback_version\s*=\s*"[^"]+"',
            f'fallback_version = "{version}"',
            text,
            count=1,
        )

    hatch_version_header = re.search(r"(?m)^\[tool\.hatch\.version\]\s*$", text)
    if hatch_version_header:
        insert_at = _next_table_offset(text, hatch_version_header.end())
        block = f'\n[tool.hatch.version.raw-options]\nfallback_version = "{version}"\n'
        return text[:insert_at].rstrip() + block + text[insert_at:]

    hatch_inline = re.search(r"(?m)^version\.source\s*=\s*\"vcs\"\s*$", text)
    if hatch_inline:
        insert_at = _next_table_offset(text, hatch_inline.end())
        block = f'\n[tool.hatch.version.raw-options]\nfallback_version = "{version}"\n'
        return text[:insert_at].rstrip() + block + text[insert_at:]

    print("warning: no Hatch VCS version block found; leaving version unchanged", file=sys.stderr)
    return text


def _next_table_offset(text: str, start: int) -> int:
    match = re.search(r"(?m)^\[[^\n]+\]\s*$", text[start:])
    if match is None:
        return len(text)
    return start + match.start()


def _update_dependency_pins_text(text: str, versions: dict[str, str]) -> str:
    updated = text
    for key in DEPENDENCY_KEYS:
        dist = PACKAGE_DISTS[key]
        if key not in versions:
            continue
        version = versions[key]
        updated = _pin_dependency(updated, dist, version)
    return updated


def _pin_dependency(text: str, dist: str, version: str) -> str:
    pattern = re.compile(
        rf'("{re.escape(dist)})(?:\s*(?:==|>=)\s*[^"]+)?(")',
    )
    return pattern.sub(rf'\1 == {version}\2', text)


if __name__ == "__main__":
    raise SystemExit(main())
