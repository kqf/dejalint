import ast
from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
DefinitionNode = FunctionNode | ast.ClassDef


@dataclass
class Config:
    paths: list[Path] = field(default_factory=lambda: [Path()])
    min_nodes: int = 8
    format: str = "line"


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
