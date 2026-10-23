import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
DefinitionNode = FunctionNode | ast.ClassDef


def strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        return body[1:]
    return body


def size(body: list[ast.stmt]) -> int:
    return sum(1 for stmt in body for _ in ast.walk(stmt))


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


def report(code: str, message: str, groups: dict) -> list[str]:
    errors: list[str] = []
    for locs in groups.values():
        first, *copies = locs
        where = f"{first[0]}:{first[1].lineno}"
        errors.extend(
            f"{py}:{node.lineno}:{node.col_offset + 1}: {code} "
            f"{message} '{node.name}' (first at {where})"
            for py, node in copies
        )
    return errors


def check(paths: list[Path], min_nodes: int) -> list[str]:
    bodies = defaultdict(list)
    names = defaultdict(list)
    for py in iter_files(paths):
        tree = ast.parse(py.read_text(), str(py))
        for bnode in tree.body:
            if isinstance(bnode, DefinitionNode):
                names[bnode.name].append((py, bnode))

        for tnode in ast.walk(tree):
            if not isinstance(tnode, FunctionNode):
                continue
            body = strip_docstring(tnode.body)
            # Skip stubs and one-liners like `...` or `return x`
            if size(body) < min_nodes:
                continue
            key = ast.dump(ast.Module(body=body, type_ignores=[]))
            bodies[key].append((py, tnode))
    return sorted(
        report("DJL001", "Duplicate function body", bodies)
        + report("DJL002", "Duplicate name", names)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dejalint",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path()])
    parser.add_argument("--min-nodes", type=int, default=8)
    args = parser.parse_args()

    errors = check(args.paths, args.min_nodes)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
