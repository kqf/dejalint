import ast
from collections.abc import Iterator
from pathlib import Path

from dejalint.core import Config, FunctionNode, each, rule


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
