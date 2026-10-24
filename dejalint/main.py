import argparse
import ast
import sys
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter
from pathlib import Path

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
DefinitionNode = FunctionNode | ast.ClassDef


@dataclass
class Config:
    min_nodes: int = 8


@dataclass(frozen=True, order=True)
class Violation:
    path: Path
    line: int
    col: int
    code: str
    message: str


# Yields (key, node) per file; nodes sharing a key are duplicates
KeyFn = Callable[
    [ast.Module, Config], Iterable[tuple[Hashable, DefinitionNode]]
]


@dataclass(frozen=True)
class Rule:
    code: str
    message: str
    keys: KeyFn


RULES: list[Rule] = []


def rule(code: str, message: str) -> Callable[[KeyFn], KeyFn]:
    def register(fn: KeyFn) -> KeyFn:
        RULES.append(Rule(code, message, fn))
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
def duplicate_bodies(tree: ast.Module, config: Config):
    for node in ast.walk(tree):
        if not isinstance(node, FunctionNode):
            continue
        body = strip_docstring(node.body)
        # Skip stubs and one-liners like `...` or `return x`
        if size(body) < config.min_nodes:
            continue
        yield ast.dump(ast.Module(body=body, type_ignores=[])), node


@rule("DJL002", "Duplicate name")
def duplicate_names(tree: ast.Module, config: Config):
    for node in tree.body:
        if isinstance(node, DefinitionNode):
            yield node.name, node


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
        tree = ast.parse(py.read_text(), str(py))
        for r in rules:
            for key, node in r.keys(tree, config):
                groups[r, key].append((py, node))

    violations: list[Violation] = []
    for (r, _), locs in groups.items():
        (fpy, fnode), *copies = locs
        violations.extend(
            Violation(
                py,
                node.lineno,
                node.col_offset + 1,
                r.code,
                f"{r.message} '{node.name}' (first at {fpy}:{fnode.lineno})",
            )
            for py, node in copies
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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dejalint",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path()])
    parser.add_argument("--min-nodes", type=int, default=8)
    parser.add_argument("--format", choices=FORMATTERS, default="line")
    args = parser.parse_args()

    violations = check(args.paths, Config(min_nodes=args.min_nodes))
    for line in FORMATTERS[args.format](violations):
        print(line)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
