import argparse
import ast
import copy
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

Location = tuple[Path, ast.stmt]

# Turns the nodes sharing a key into (path, node, message) violations
ReportFn = Callable[
    [Hashable, list[Location]], Iterable[tuple[Path, ast.stmt, str]]
]


def duplicates(message: str) -> ReportFn:
    # Every node after the first is a copy of it
    def report(key: Hashable, locs: list[Location]):
        (fpy, fnode), *copies = locs
        for py, node in copies:
            # Duplicate rules compare definitions, which are named
            name = cast(DefinitionNode, node).name
            first = f"{fpy}:{fnode.lineno}"
            yield py, node, f"{message} '{name}' (first at {first})"

    return report


def each(message: str) -> ReportFn:
    # Every node is a violation on its own, `message` is formatted with the key
    def report(key: Hashable, locs: list[Location]):
        for py, node in locs:
            yield py, node, message.format(key)

    return report


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
    keys: KeyFn
    report: ReportFn
    noqa: NoqaFn = header


RULES: list[Rule] = []


def rule(
    code: str,
    report: ReportFn,
    noqa: NoqaFn = header,
) -> Callable[[KeyFn], KeyFn]:
    def register(fn: KeyFn) -> KeyFn:
        RULES.append(Rule(code, fn, report, noqa))
        return fn

    return register


def strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        return body[1:]
    return body


def size(body: list[ast.stmt]) -> int:
    return sum(1 for stmt in body for _ in ast.walk(stmt))


def dump(body: list[ast.stmt]) -> str:
    return ast.dump(ast.Module(body=body, type_ignores=[]))


def functions(tree: ast.Module, config: Config) -> Iterator[FunctionNode]:
    for node in ast.walk(tree):
        if not isinstance(node, FunctionNode):
            continue
        # Skip stubs and one-liners like `...` or `return x`
        if size(strip_docstring(node.body)) >= config.min_nodes:
            yield node


@rule("DJL001", duplicates("Duplicate function body"))
def duplicate_bodies(path: Path, tree: ast.Module, config: Config):
    for node in functions(tree, config):
        yield dump(strip_docstring(node.body)), node


def binding(node: ast.AST) -> str | None:
    # The attribute that holds the name a node binds or refers to
    if isinstance(node, ast.arg):
        return "arg"
    if isinstance(node, ast.Name):
        return "id"

    # sourcery skip: assign-if-exp, reintroduce-else
    if isinstance(node, ast.ExceptHandler | DefinitionNode):
        return "name"

    return None


def anonymize(node: FunctionNode) -> list[ast.stmt]:
    # Locals are renamed in order of appearance, globals are kept as is
    node = copy.deepcopy(node)
    shared = {
        name
        for child in ast.walk(node)
        if isinstance(child, ast.Global | ast.Nonlocal)
        for name in child.names
    }
    names: dict[str, str] = {}
    for child in ast.walk(node):
        attr = binding(child)
        if child is node or attr is None:
            continue
        # Only bindings introduce locals, loads may refer to globals
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            continue
        name = getattr(child, attr)
        if name is not None and name not in shared:
            names.setdefault(name, f"_{len(names)}")

    for child in ast.walk(node):
        if child is not node and (attr := binding(child)):
            name = getattr(child, attr)
            setattr(child, attr, names.get(name, name))
    return strip_docstring(node.body)


def inexact(message: str) -> ReportFn:
    report = duplicates(message)

    # Exact copies are left to DJL001
    def skip_exact(key: Hashable, locs: list[Location]):
        seen, unique = set(), []
        for py, node in locs:
            exact = dump(strip_docstring(cast(FunctionNode, node).body))
            if exact not in seen:
                seen.add(exact)
                unique.append((py, node))
        return report(key, unique)

    return skip_exact


@rule("DJL004", inexact("Near-duplicate function body"))
def near_duplicate_bodies(path: Path, tree: ast.Module, config: Config):
    for node in functions(tree, config):
        yield dump(anonymize(node)), node


@rule("DJL002", duplicates("Duplicate name"))
def duplicate_names(path: Path, tree: ast.Module, config: Config):
    for node in tree.body:
        if isinstance(node, DefinitionNode):
            yield node.name, node


def calls(node: FunctionNode) -> Iterator[str]:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            yield func.id
        # Methods recurse through self.name() or cls.name()
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in {"self", "cls"}
        ):
            yield func.attr


@rule("DJL003", each("Recursive function '{}'"))
def recursion(path: Path, tree: ast.Module, config: Config):
    for node in ast.walk(tree):
        if isinstance(node, FunctionNode) and node.name in calls(node):
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
