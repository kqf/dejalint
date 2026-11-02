import ast
from pathlib import Path

from dejalint.core import (
    Config,
    dump,
    duplicates,
    functions,
    rule,
    strip_docstring,
)


@rule("DJL001", duplicates("Duplicate function body"))
def duplicate_bodies(path: Path, tree: ast.Module, config: Config):
    for node in functions(tree, config):
        yield dump(strip_docstring(node.body)), node
