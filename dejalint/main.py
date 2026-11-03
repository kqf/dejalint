import argparse
import ast
import copy
import sys
import tomllib
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import Any, NoReturn

# Rules register themselves in RULES on import
from dejalint import (  # noqa: F401
    duplicate_bodies,
    duplicate_names,
    error_swallowing,
    near_duplicate_bodies,
    recursion,
)
from dejalint.core import RULES, Config, Rule


def find_pyproject(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def load_config(
    pyproject: Path | None,
    error: Callable[[str], NoReturn],
) -> dict[str, Any]:
    if pyproject is None:
        return {}
    with pyproject.open("rb") as f:
        section = tomllib.load(f).get("tool", {}).get("dejalint", {})

    # Accept both `min-nodes` and `min_nodes`
    options = {k.replace("-", "_"): v for k, v in section.items()}
    if unknown := options.keys() - {f.name for f in fields(Config)}:
        error(
            f"{pyproject}: unknown [tool.dejalint] options: "
            + ", ".join(sorted(unknown))
        )
    if "paths" in options:
        # Paths in the config are relative to the pyproject.toml location
        options["paths"] = [pyproject.parent / p for p in options["paths"]]
    return options


@dataclass(frozen=True, order=True)
class Violation:
    path: Path
    line: int
    col: int
    code: str
    message: str


def suppressed(lines: list[str], node: ast.stmt, r: Rule) -> bool:
    first, last = r.noqa(node)
    return any(r.code in line for line in lines[first - 1 : last])


def iter_files(paths: list[Path]) -> list[Path]:
    def relative(path):
        for py in sorted(path.rglob("*.py")):
            if not any(p.startswith(".") for p in py.relative_to(path).parts):
                yield py

    files = []
    for path in paths:
        if not path.is_dir():
            files.append(path)
            continue
        files.extend(relative(path))
    return files


def check(
    paths: list[Path],
    config: Config,
    rules: list[Rule] = RULES,
) -> list[Violation]:
    groups = defaultdict(list)
    for py in iter_files(paths):
        source = py.read_text()
        tree = ast.parse(source, str(py))
        lines = source.splitlines()
        for r in rules:
            for key, node in r.keys(py, tree, config):
                # Suppressed nodes are left out of the comparison entirely
                if not suppressed(lines, node, r):
                    groups[r, key].append((py, node))

    violations = [
        Violation(py, node.lineno, node.col_offset + 1, r.code, message)
        for (r, key), locs in groups.items()
        for py, node, message in r.report(key, locs)
    ]
    return sorted(violations)


def by_line(violations: list[Violation]) -> Iterator[str]:
    for v in violations:
        yield f"{v.path}:{v.line}:{v.col}: {v.code} {v.message}"


def by_rule(violations: list[Violation]) -> Iterator[str]:
    code = attrgetter("code")
    for name, group in groupby(sorted(violations, key=code), key=code):
        yield f"{name}:"
        for v in group:
            yield f"  {v.path}:{v.line}:{v.col}: {v.message}"


FORMATTERS = {
    "line": by_line,
    "rule": by_rule,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dejalint",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # Unset options don't override values from pyproject.toml
        argument_default=argparse.SUPPRESS,
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--min-nodes", type=int)
    parser.add_argument("--format", choices=FORMATTERS)
    args = parser.parse_args(argv)

    options = load_config(find_pyproject(Path.cwd()), parser.error)
    config = Config(**{**options, **vars(args)})
    if config.format not in FORMATTERS:
        parser.error(f"unknown format {config.format!r}")

    violations = check(config.paths, config)
    for line in FORMATTERS[config.format](violations):
        print(line)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
