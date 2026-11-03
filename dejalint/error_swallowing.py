import ast
from pathlib import Path

from dejalint.core import Config, each, rule

BLIND = {"Exception", "BaseException"}

LOGGING = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "log",
    "print_exc",
    "print_exception",
}


def blind(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    types = (
        handler.type.elts
        if isinstance(handler.type, ast.Tuple)
        else [handler.type]
    )
    return any(isinstance(t, ast.Name) and t.id in BLIND for t in types)


def logs(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    if isinstance(func, ast.Name):
        return func.id == "print"
    return isinstance(func, ast.Attribute) and func.attr in LOGGING


def carries_on(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass | ast.Continue):
        return True
    # Both `return` and `return None`
    return isinstance(stmt, ast.Return) and (
        stmt.value is None
        or isinstance(stmt.value, ast.Constant)
        and stmt.value.value is None
    )


def swallows(handler: ast.ExceptHandler) -> bool:
    *calls, last = handler.body
    if carries_on(last):
        # A lone `pass` or `continue` is S110/S112 territory
        return bool(calls) and all(map(logs, calls))
    return all(map(logs, handler.body))


@rule("DJL005", each("Exception logged and swallowed in '{}'"))
def error_swallowing(path: Path, tree: ast.Module, config: Config):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ExceptHandler)
            and blind(node)
            and swallows(node)
        ):
            clause = ast.unparse(node.type) if node.type else ""
            yield f"except {clause}".strip(), node
