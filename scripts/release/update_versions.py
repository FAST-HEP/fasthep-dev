from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_data import (  # noqa: E402
    PINNED_LAST,
    ReleasePlan,
    load_release_plan,
    validate_pin_readiness,
)


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
    parser.add_argument("--package")
    args = parser.parse_args()

    root = Path.cwd()
    plan: ReleasePlan = load_release_plan(args.release_file)
    if args.package is not None and args.package not in plan.packages:
        raise SystemExit(
            f"Unknown package {args.package!r}, expected one of {sorted(plan.packages)}"
        )
    dist_versions = {spec.dist.lower(): spec.version for spec in plan.packages.values()}
    selected = [args.package] if args.package else list(plan.order)

    updates: dict[Path, Change] = {}
    for key in selected:
        path = root / key / "pyproject.toml"
        _queue_update(
            updates,
            path=path,
            description="package version",
            after=_update_package_version_text(
                path, _current_text(updates, path), plan.packages[key].version
            ),
        )

    for key in PINNED_LAST:
        if args.package is not None and args.package != key:
            continue
        if not args.dry_run:
            readiness_errors = validate_pin_readiness(plan, root, key)
            if readiness_errors:
                for error in readiness_errors:
                    print(error, file=sys.stderr)
                raise SystemExit(1)
        path = root / key / "pyproject.toml"
        _queue_update(
            updates,
            path=path,
            description="FAST-HEP dependency pins",
            after=_update_dependency_pins_text(_current_text(updates, path), dist_versions),
        )
        if key == "workshop":
            pixi_path = root / "workshop" / "pixi.toml"
            if pixi_path.exists():
                _queue_update(
                    updates,
                    path=pixi_path,
                    description="workshop pixi.toml FAST-HEP pins",
                    after=_update_pixi_pins_text(_current_text(updates, pixi_path), dist_versions),
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

    if not args.dry_run:
        _assert_project_names_safe(
            [change.path for change in changes if change.path.name == "pyproject.toml"]
        )

    return 0


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

    if "version" in set(project.get("dynamic") or []):
        return text

    print("warning: no static project.version found; leaving version unchanged", file=sys.stderr)
    return text


def _update_dependency_pins_text(text: str, dist_versions: dict[str, str]) -> str:
    parsed = tomllib.loads(text)
    ranges = _dependency_array_ranges(text, parsed)
    if not ranges:
        return text

    pieces: list[str] = []
    cursor = 0
    for start, end in ranges:
        pieces.append(text[cursor:start])
        pieces.append(_pin_dependency_array_text(text[start:end], dist_versions))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def _update_pixi_pins_text(text: str, dist_versions: dict[str, str]) -> str:
    bounds = _section_bounds(text).get("feature.released.pypi-dependencies")
    if bounds is None:
        return text

    start, end = bounds
    section = text[start:end]
    for dist, version in dist_versions.items():
        escaped = re.escape(dist)
        section = re.sub(
            rf'(?mi)^({escaped}) = "[^"]*"$',
            rf'\1 = "=={version}"',
            section,
        )
        section = re.sub(
            rf'(?mi)^({escaped}) = \{{version = "[^"]*"\}}$',
            rf'\1 = {{version = "=={version}"}}',
            section,
        )
    return text[:start] + section + text[end:]


def _dependency_array_ranges(
    text: str,
    parsed: dict[str, Any],
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    section_bounds = _section_bounds(text)

    project = parsed.get("project")
    if isinstance(project, dict) and isinstance(project.get("dependencies"), list):
        bounds = section_bounds.get("project")
        if bounds is not None:
            found = _array_value_range(text, *bounds, key="dependencies")
            if found is not None:
                ranges.append(found)

    optional = (project or {}).get("optional-dependencies") if isinstance(project, dict) else None
    if isinstance(optional, dict):
        bounds = section_bounds.get("project.optional-dependencies")
        if bounds is not None:
            for key, value in optional.items():
                if isinstance(value, list):
                    found = _array_value_range(text, *bounds, key=str(key))
                    if found is not None:
                        ranges.append(found)

    return sorted(ranges)


def _section_bounds(text: str) -> dict[str, tuple[int, int]]:
    headers = list(re.finditer(r"(?m)^\[([^\]]+)\]\s*$", text))
    bounds: dict[str, tuple[int, int]] = {}
    for index, header in enumerate(headers):
        start = header.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        bounds[header.group(1)] = (start, end)
    return bounds


def _array_value_range(
    text: str,
    section_start: int,
    section_end: int,
    *,
    key: str,
) -> tuple[int, int] | None:
    section = text[section_start:section_end]
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\[", section)
    if match is None:
        return None
    array_start = section_start + match.start()
    bracket_start = section_start + match.end() - 1
    array_end = _matching_bracket_offset(text, bracket_start)
    if array_end > section_end:
        raise SystemExit(f"dependency array '{key}' extends beyond its TOML section")
    return array_start, array_end


def _matching_bracket_offset(text: str, bracket_start: int) -> int:
    in_string = False
    escaped = False
    depth = 0
    for index in range(bracket_start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index + 1
    raise SystemExit("unterminated TOML dependency array")


def _pin_dependency_array_text(
    array_text: str,
    dist_versions: dict[str, str],
) -> str:
    return re.sub(
        r'"((?:[^"\\]|\\.)*)"',
        lambda match: _pin_dependency_match(match, dist_versions),
        array_text,
    )


def _pin_dependency_match(
    match: re.Match[str],
    dist_versions: dict[str, str],
) -> str:
    raw = match.group(1)
    dependency = bytes(raw, "utf-8").decode("unicode_escape")
    updated = _pin_dependency_string(dependency, dist_versions)
    if updated == dependency:
        return match.group(0)
    return '"' + updated.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _pin_dependency_string(
    dependency: str,
    dist_versions: dict[str, str],
) -> str:
    try:
        requirement = Requirement(dependency)
    except InvalidRequirement:
        return dependency
    version = dist_versions.get(requirement.name.lower())
    if version is None or requirement.url:
        return dependency

    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    marker = f"; {requirement.marker}" if requirement.marker else ""
    return f"{requirement.name}{extras} == {version}{marker}"


def _assert_project_names_safe(paths: list[Path]) -> None:
    operators = ("==", ">=", "<=", "~=", "!=")
    for path in paths:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        project = data.get("project") or {}
        name = project.get("name") if isinstance(project, dict) else None
        if isinstance(name, str) and any(operator in name for operator in operators):
            raise SystemExit(f"{path}: unsafe project.name after update: {name!r}")


if __name__ == "__main__":
    raise SystemExit(main())
