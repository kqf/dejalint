import argparse
import ast
import sys
import tomllib
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass, field, fields
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import Any, NoReturn, cast

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
DefinitionNode = FunctionNode | ast.ClassDef


@dataclass
class Config:
    paths: list[Path] = field(default_factory=lambda: [Path()])
    min_nodes: int = 8
    format: str = "line"


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


# Yields (key, node) per file; nodes sharing a key are duplicates
KeyFn = Callable[
    [Path, ast.Module, Config], Iterable[tuple[Hashable, ast.stmt]]
]

# Returns the (first, last) lines where a noqa comment silences the node
NoqaFn = Callable[[ast.stmt], tuple[int, int]]


def header(node: ast.stmt) -> tuple[int, int]:
    # From the def line up to the first body statement
    if isinstance(node, DefinitionNode):
        return node.lineno, node.body[0].lineno
    return node.lineno, node.lineno


def statement(node: ast.stmt) -> tuple[int, int]:
    return node.lineno, node.end_lineno or node.lineno


@dataclass(frozen=True)
class Rule:
    code: str
    message: str
    keys: KeyFn
    # Off: every node is a violation on its own and its key is the name
    duplicates: bool = True
    noqa: NoqaFn = header


RULES: list[Rule] = []


def rule(
    code: str,
    message: str,
    duplicates: bool = True,
    noqa: NoqaFn = header,
) -> Callable[[KeyFn], KeyFn]:
    def register(fn: KeyFn) -> KeyFn:
        RULES.append(Rule(code, message, fn, duplicates, noqa))
        return fn

    return register


def strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        return body[1:]
    return body


def size(body: list[ast.stmt]) -> int:
    return sum(1 for stmt in body for _ in ast.walk(stmt))


@rule("DJL001", "Duplicate function body")
def duplicate_bodies(path: Path, tree: ast.Module, config: Config):
    for node in ast.walk(tree):
        if not isinstance(node, FunctionNode):
            continue
        body = strip_docstring(node.body)
        # Skip stubs and one-liners like `...` or `return x`
        if size(body) < config.min_nodes:
            continue
        yield ast.dump(ast.Module(body=body, type_ignores=[])), node


@rule("DJL002", "Duplicate name")
def duplicate_names(path: Path, tree: ast.Module, config: Config):
    for node in tree.body:
        if isinstance(node, DefinitionNode):
            yield node.name, node


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

    violations: list[Violation] = []
    for (r, key), locs in groups.items():
        if not r.duplicates:
            violations.extend(
                Violation(
                    py,
                    node.lineno,
                    node.col_offset + 1,
                    r.code,
                    r.message.format(key),
                )
                for py, node in locs
            )
            continue
        (fpy, fnode), *copies = locs
        for py, node in copies:
            # Duplicate rules compare definitions, which are named
            name = cast(DefinitionNode, node).name
            violations.append(
                Violation(
                    py,
                    node.lineno,
                    node.col_offset + 1,
                    r.code,
                    f"{r.message} '{name}' (first at {fpy}:{fnode.lineno})",
                )
            )
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
