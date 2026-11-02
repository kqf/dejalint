import ast
import copy
from collections.abc import Hashable
from pathlib import Path
from typing import cast

from dejalint.core import (
    Config,
    DefinitionNode,
    FunctionNode,
    Location,
    ReportFn,
    dump,
    duplicates,
    functions,
    rule,
    strip_docstring,
)


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
