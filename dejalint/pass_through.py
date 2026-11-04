import ast
from collections.abc import Iterator
from pathlib import Path

from dejalint.core import Config, FunctionNode, each, rule, strip_docstring

RECEIVERS = {"self", "cls"}


def forwarded(node: FunctionNode) -> ast.Call | None:
    match strip_docstring(node.body):
        case [ast.Return(value=ast.Call() as call)]:
            return call
        case [ast.Return(value=ast.Await(value=ast.Call() as call))]:
            return call
    return None


def passed(call: ast.Call) -> list[str]:
    tokens = [
        f"*{ast.unparse(a.value)}"
        if isinstance(a, ast.Starred)
        else ast.unparse(a)
        for a in call.args
    ]
    for k in call.keywords:
        value = ast.unparse(k.value)
        tokens.append(f"{k.arg}={value}" if k.arg else f"**{value}")
    return tokens


def signatures(params: ast.arguments, skip: int) -> Iterator[list[str]]:
    # Every call that forwards the parameters exactly, in order
    positional = [a.arg for a in params.posonlyargs + params.args][skip:]
    posonly = max(len(params.posonlyargs) - skip, 0)
    keywords = [f"{a.arg}={a.arg}" for a in params.kwonlyargs]
    kwarg = [f"**{params.kwarg.arg}"] if params.kwarg else []
    if params.vararg:
        # Positionals passed by keyword would collide with *args
        star = [f"*{params.vararg.arg}"]
        yield positional + star + keywords + kwarg
        return
    for split in range(posonly, len(positional) + 1):
        by_name = [f"{p}={p}" for p in positional[split:]]
        yield positional[:split] + by_name + keywords + kwarg


def passes_through(node: FunctionNode) -> bool:
    params = node.args
    # Decorators and defaults give the wrapper a reason to exist
    if node.decorator_list or params.defaults or any(params.kw_defaults):
        return False
    if (call := forwarded(node)) is None:
        return False
    names = [a.arg for a in params.posonlyargs + params.args]
    receiver = bool(names) and names[0] in RECEIVERS
    tokens = passed(call)
    for skip in {0, int(receiver)}:
        # Wrappers that forward nothing, like `def main(): return run()`
        if len(names) - skip + len(params.kwonlyargs) == 0 and not (
            params.vararg or params.kwarg
        ):
            continue
        if tokens in signatures(params, skip):
            return True
    return False


@rule("DJL006", each("Pass-through wrapper '{}'"))
def pass_through(path: Path, tree: ast.Module, config: Config):
    for node in ast.walk(tree):
        if isinstance(node, FunctionNode) and passes_through(node):
            yield node.name, node
