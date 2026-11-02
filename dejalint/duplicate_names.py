import ast
from pathlib import Path

from dejalint.core import Config, DefinitionNode, duplicates, rule


@rule("DJL002", duplicates("Duplicate name"))
def duplicate_names(path: Path, tree: ast.Module, config: Config):
    for node in tree.body:
        if isinstance(node, DefinitionNode):
            yield node.name, node
