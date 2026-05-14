#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_PACKAGES = (
    "fasthep-flow",
    "fasthep-carpenter",
    "fasthep-curator",
    "fasthep-render",
    "fasthep-cli",
    "fasthep-workshop",
    "fasthep",
)

PYTHON_PACKAGE_HINTS = {
    "fasthep-flow": "hepflow",
    "fasthep-carpenter": "fasthep_carpenter",
    "fasthep-curator": "fasthep_curator",
    "fasthep-render": "fasthep_render",
    "fasthep-cli": "fasthep_cli",
    "fasthep": "fasthep",
}


@dataclass
class PythonModuleSummary:
    module: str
    path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def discover_packages(root: Path) -> list[Path]:
    packages: list[Path] = []
    for name in DEFAULT_PACKAGES:
        path = root / name
        if path.exists():
            packages.append(path)

    seen = {p.resolve() for p in packages}
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if path.resolve() in seen:
            continue
        if path.name.startswith("fasthep-"):
            packages.append(path)

    return packages


def module_name_from_path(path: Path, package_root: Path) -> str | None:
    src = package_root / "src"
    try:
        rel_path = path.relative_to(src)
    except ValueError:
        return None

    if rel_path.name == "__init__.py":
        parts = rel_path.parent.parts
    else:
        parts = rel_path.with_suffix("").parts

    if not parts:
        return None
    return ".".join(parts)


def summarise_python_module(
    path: Path,
    package_root: Path,
    workspace_root: Path,
) -> PythonModuleSummary | None:
    module = module_name_from_path(path, package_root)
    if module is None:
        return None

    try:
        tree = ast.parse(read_text(path))
    except SyntaxError:
        return PythonModuleSummary(module=module, path=rel(path, workspace_root))

    classes: list[str] = []
    functions: list[str] = []
    constants: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    constants.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id.isupper():
                constants.append(target.id)

    if not classes and not functions and not constants:
        return None

    return PythonModuleSummary(
        module=module,
        path=rel(path, workspace_root),
        classes=classes,
        functions=functions,
        constants=constants,
    )


def collect_python_symbols(
    package_root: Path,
    workspace_root: Path,
) -> list[PythonModuleSummary]:
    src = package_root / "src"
    if not src.exists():
        return []

    summaries: list[PythonModuleSummary] = []
    for path in sorted(src.rglob("*.py")):
        if path.name == "_version.py":
            continue
        summary = summarise_python_module(path, package_root, workspace_root)
        if summary is not None:
            summaries.append(summary)
    return summaries


def simple_yaml_load(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        return yaml.safe_load(read_text(path))
    except Exception:
        return None


def extract_registry_entries(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        return {}

    registry = data.get("registry")
    if not isinstance(registry, dict):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for section, entries in registry.items():
        if isinstance(entries, dict):
            out[section] = dict(entries)
    return out


def collect_profiles(package_root: Path, workspace_root: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for path in sorted(package_root.rglob("profiles/*.yaml")):
        data = simple_yaml_load(path)
        profiles.append(
            {
                "path": rel(path, workspace_root),
                "name": path.stem,
                "registry_sections": sorted(extract_registry_entries(data)),
                "has_execution_hooks": isinstance(data, dict)
                and "execution_hooks" in data,
            }
        )
    return profiles


def collect_registry_index(
    packages: list[Path],
    workspace_root: Path,
) -> dict[str, dict[str, dict[str, Any]]]:
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for package_root in packages:
        package_name = package_root.name
        for path in sorted(package_root.rglob("profiles/*.yaml")):
            data = simple_yaml_load(path)
            registry_entries = extract_registry_entries(data)
            for section, entries in registry_entries.items():
                section_index = index.setdefault(section, {})
                for name, entry in entries.items():
                    section_index[str(name)] = {
                        "package": package_name,
                        "profile": rel(path, workspace_root),
                        "entry": entry,
                    }
    return index


def parse_pixi_tasks(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    text = read_text(path)
    tasks: dict[str, str] = {}

    try:
        import tomllib

        data = tomllib.loads(text)
        raw_tasks = data.get("tasks", {})
        if isinstance(raw_tasks, dict):
            for name, value in raw_tasks.items():
                if isinstance(value, str):
                    tasks[name] = value
                elif isinstance(value, dict):
                    if "cmd" in value:
                        tasks[name] = str(value["cmd"])
                    elif "depends-on" in value:
                        tasks[name] = "depends-on: " + ", ".join(
                            map(str, value["depends-on"])
                        )
                    else:
                        tasks[name] = json.dumps(value, sort_keys=True)
            return tasks
    except Exception:
        pass

    in_tasks = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_tasks = stripped == "[tasks]"
            continue
        if not in_tasks or not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"([A-Za-z0-9_-]+)\s*=\s*(.+)", stripped)
        if match:
            tasks[match.group(1)] = match.group(2).strip().strip('"')
    return tasks


def collect_tests(package_root: Path, workspace_root: Path) -> list[dict[str, Any]]:
    tests_root = package_root / "tests"
    if not tests_root.exists():
        return []

    tests: list[dict[str, Any]] = []
    for path in sorted(tests_root.rglob("test_*.py")):
        names: list[str] = []
        try:
            tree = ast.parse(read_text(path))
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    names.append(node.name)
                elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    names.append(node.name)
        except SyntaxError:
            pass
        tests.append({"path": rel(path, workspace_root), "tests": names})
    return tests


def package_import_name(package_root: Path) -> str | None:
    pyproject = package_root / "pyproject.toml"
    if not pyproject.exists():
        return PYTHON_PACKAGE_HINTS.get(package_root.name)

    text = read_text(pyproject)
    match = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    distribution = match.group(1) if match else package_root.name

    hint = PYTHON_PACKAGE_HINTS.get(package_root.name)
    if hint:
        return hint

    return distribution.replace("-", "_")


def render_package_index(packages: list[Path], workspace_root: Path) -> str:
    lines = ["# Package index", ""]
    lines.append("| Package | Import namespace | Has src | Has tests | Has profiles |")
    lines.append("|---|---|---:|---:|---:|")
    for package_root in packages:
        import_name = package_import_name(package_root) or ""
        lines.append(
            "| {pkg} | `{imp}` | {src} | {tests} | {profiles} |".format(
                pkg=package_root.name,
                imp=import_name,
                src="yes" if (package_root / "src").exists() else "no",
                tests="yes" if (package_root / "tests").exists() else "no",
                profiles="yes"
                if list(package_root.rglob("profiles/*.yaml"))
                else "no",
            )
        )
    lines.append("")
    lines.append("Generated by `tools/repo_index.py`.")
    lines.append("")
    return "\n".join(lines)


def render_symbol_index(symbols_by_package: dict[str, list[PythonModuleSummary]]) -> str:
    lines = ["# Symbol index", ""]
    for package, summaries in symbols_by_package.items():
        if not summaries:
            continue
        lines.append(f"## {package}")
        lines.append("")
        for summary in summaries:
            lines.append(f"### `{summary.module}`")
            lines.append(f"- path: `{summary.path}`")
            if summary.classes:
                lines.append("- classes: " + ", ".join(f"`{x}`" for x in summary.classes))
            if summary.functions:
                lines.append(
                    "- functions: " + ", ".join(f"`{x}`" for x in summary.functions)
                )
            if summary.constants:
                lines.append(
                    "- constants: " + ", ".join(f"`{x}`" for x in summary.constants)
                )
            lines.append("")
    lines.append("Generated by `tools/repo_index.py`.")
    lines.append("")
    return "\n".join(lines)


def render_profile_index(profiles_by_package: dict[str, list[dict[str, Any]]]) -> str:
    lines = ["# Profile index", ""]
    for package, profiles in profiles_by_package.items():
        if not profiles:
            continue
        lines.append(f"## {package}")
        lines.append("")
        for profile in profiles:
            bits: list[str] = []
            if profile["registry_sections"]:
                bits.append("registry: " + ", ".join(profile["registry_sections"]))
            if profile["has_execution_hooks"]:
                bits.append("execution_hooks")
            suffix = f" ({'; '.join(bits)})" if bits else ""
            lines.append(f"- `{profile['name']}` — `{profile['path']}`{suffix}")
        lines.append("")
    lines.append("Generated by `tools/repo_index.py`.")
    lines.append("")
    return "\n".join(lines)


def render_command_index(tasks_by_package: dict[str, dict[str, str]]) -> str:
    lines = ["# Command index", ""]
    for package, tasks in tasks_by_package.items():
        if not tasks:
            continue
        lines.append(f"## {package}")
        lines.append("")
        for name, command in sorted(tasks.items()):
            lines.append(f"- `pixi run {name}`: `{command}`")
        lines.append("")
    lines.append("Generated by `tools/repo_index.py`.")
    lines.append("")
    return "\n".join(lines)


def render_test_index(tests_by_package: dict[str, list[dict[str, Any]]]) -> str:
    lines = ["# Test index", ""]
    for package, tests in tests_by_package.items():
        if not tests:
            continue
        lines.append(f"## {package}")
        lines.append("")
        for test_file in tests:
            lines.append(f"- `{test_file['path']}`")
            for name in test_file["tests"][:20]:
                lines.append(f"  - `{name}`")
            extra = len(test_file["tests"]) - 20
            if extra > 0:
                lines.append(f"  - ... +{extra} more")
        lines.append("")
    lines.append("Generated by `tools/repo_index.py`.")
    lines.append("")
    return "\n".join(lines)


def strip_registry_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {"value": entry}
    return {
        key: value
        for key, value in entry.items()
        if key in {"spec", "impl", "family", "kind", "events", "context_outputs"}
    }


def render_registry_index_yaml(index: dict[str, dict[str, dict[str, Any]]]) -> str:
    compact: dict[str, dict[str, Any]] = {}
    for section, entries in sorted(index.items()):
        compact[section] = {}
        for name, metadata in sorted(entries.items()):
            compact[section][name] = {
                "package": metadata["package"],
                "profile": metadata["profile"],
                **strip_registry_entry(metadata.get("entry")),
            }

    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_dump(compact, sort_keys=True)
    except Exception:
        return json.dumps(compact, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate compact FAST-HEP repo indexes.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Workspace root. Defaults to current working directory.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Defaults to <root>/.ai.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    outdir = (args.out or (root / ".ai")).resolve()
    packages = discover_packages(root)

    if not packages:
        print(f"No FAST-HEP packages found under {root}", file=sys.stderr)
        return 1

    symbols_by_package = {
        package.name: collect_python_symbols(package, root) for package in packages
    }
    profiles_by_package = {
        package.name: collect_profiles(package, root) for package in packages
    }
    tasks_by_package = {
        package.name: parse_pixi_tasks(package / "pixi.toml") for package in packages
    }
    tests_by_package = {package.name: collect_tests(package, root) for package in packages}
    registry_index = collect_registry_index(packages, root)

    write_text(outdir / "package-index.md", render_package_index(packages, root))
    write_text(outdir / "symbol-index.md", render_symbol_index(symbols_by_package))
    write_text(outdir / "profile-index.md", render_profile_index(profiles_by_package))
    write_text(outdir / "command-index.md", render_command_index(tasks_by_package))
    write_text(outdir / "test-index.md", render_test_index(tests_by_package))
    write_text(outdir / "registry-index.yaml", render_registry_index_yaml(registry_index))

    print(f"Wrote repository indexes to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
