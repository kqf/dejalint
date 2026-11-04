import ast
from pathlib import Path

import pytest

from dejalint.core import Rule, each, statement
from dejalint.main import RULES, Config, by_line, check


def report(path: Path, rules: list[Rule] = RULES) -> list[str]:
    return list(by_line(check([path], Config(), rules)))


@pytest.mark.parametrize(
    "code, message",
    [
        ("DJL001", "1:1: DJL001 Duplicate function body 'other'"),
        ("DJL002", "8:1: DJL002 Duplicate name 'squares'"),
    ],
)
def test_rule(
    src: Path, original: Path, duplicate: Path, code: str, message: str
):
    rules = [r for r in RULES if r.code == code]
    assert report(src, rules) == [
        f"{duplicate}:{message} (first at {original}:1)"
    ]


@pytest.mark.usefixtures("duplicate")
def test_near_duplicate(src: Path, original: Path):
    # Exact copies are reported by DJL001 only
    renamed = src / "d.py"
    renamed.write_text(
        """\
def sum_squares(values):
    acc = 0
    for v in values:
        acc += v * v
    return acc


def reversed_squares(xs):
    total = 0
    for x in reversed(xs):
        total += x * x
    return total
"""
    )
    rules = [r for r in RULES if r.code == "DJL004"]
    assert report(src, rules) == [
        (
            f"{renamed}:1:1: DJL004 Near-duplicate function body "
            f"'sum_squares' (first at {original}:1)"
        )
    ]


def test_clean(unique: Path):
    assert report(unique) == []


@pytest.mark.parametrize(
    "header, codes",
    [
        ("def squares(xs):  # noqa: DJL001", ["DJL002"]),
        ("def squares(xs):\n    # noqa: E501, DJL001", ["DJL002"]),
        ("def squares(xs):  # noqa: DJL002", ["DJL001"]),
    ],
)
@pytest.mark.usefixtures("duplicate")
def test_noqa(src: Path, original: Path, body: str, header: str, codes):
    # Suppressing the first occurrence also silences its copy
    original.write_text(f"{header}{body}")
    assert [v.code for v in check([src], Config())] == codes


def assignments(path: Path, tree: ast.Module, config: Config):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            yield ast.unparse(node.targets[0]), node


def test_standalone_rule(tmp_path: Path):
    py = tmp_path / "a.py"
    py.write_text(
        """\
x = 1
y = (
    2
)  # noqa: TST001
x = 3
"""
    )
    rule = Rule("TST001", assignments, each("Assignment '{}'"), statement)
    assert report(py, [rule]) == [
        f"{py}:1:1: TST001 Assignment 'x'",
        f"{py}:5:1: TST001 Assignment 'x'",
    ]


def test_recursion(tmp_path: Path):
    py = tmp_path / "a.py"
    py.write_text(
        """\
def fact(n):
    return 1 if n < 2 else n * fact(n - 1)


class Tree:
    def walk(self):
        return [self.walk()]

    def size(self):  # noqa: DJL003
        return self.size()

    def flat(self):
        return walk()
"""
    )
    rules = [r for r in RULES if r.code == "DJL003"]
    assert report(py, rules) == [
        f"{py}:1:1: DJL003 Recursive function 'fact'",
        f"{py}:6:5: DJL003 Recursive function 'walk'",
    ]


def test_error_swallowing(tmp_path: Path):
    py = tmp_path / "a.py"
    py.write_text(
        """\
import logging

logger = logging.getLogger(__name__)


def load(paths):
    for path in paths:
        try:
            read(path)
        except Exception as e:
            logger.exception("failed %s: %s", path, e)
            continue
        try:
            read(path)
        except:
            print("oops")
        try:
            read(path)
        except (OSError, BaseException):
            logging.error("failed", exc_info=True)
            return None
        try:
            read(path)
        except Exception:  # noqa: DJL005
            logger.warning("ignored")
        try:
            read(path)
        except Exception:
            pass
        try:
            read(path)
        except ValueError:
            logger.error("bad value")
        try:
            read(path)
        except Exception:
            logger.error("failed")
            raise
        try:
            read(path)
        except Exception:
            logger.error("failed")
            return fallback()
"""
    )
    rules = [r for r in RULES if r.code == "DJL005"]
    message = "DJL005 Exception logged and swallowed in"
    assert report(py, rules) == [
        f"{py}:10:9: {message} 'except Exception'",
        f"{py}:15:9: {message} 'except'",
        f"{py}:19:9: {message} 'except (OSError, BaseException)'",
    ]


def test_pass_through(tmp_path: Path):
    py = tmp_path / "a.py"
    py.write_text(
        """\
def get_user(id):
    return fetch_user(id)


def search(query, /, page, *, size):
    \"\"\"Docstring is ignored.\"\"\"
    return client.search(query, page=page, size=size)


async def load(*args, **kwargs):
    return await fetch(*args, **kwargs)


class Repo(Base):
    def get(self, id):
        return self._db.get(id)

    def put(self, key, value):
        return super().put(key, value)

    def close(self):
        return self._db.close()

    def find(self, id):  # noqa: DJL006
        return self._db.find(id)


def swapped(a, b):
    return f(b, a)


def extra(a):
    return f(a, 1)


def partial(a, b):
    return f(a)


def default(a=1):
    return f(a)


def computed(a):
    return f(a + 1)


def main():
    return run()


@property
def decorated(a):
    return f(a)


def collides(a, *args):
    return f(a=a, *args)
"""
    )
    rules = [r for r in RULES if r.code == "DJL006"]
    message = "DJL006 Pass-through wrapper"
    assert report(py, rules) == [
        f"{py}:1:1: {message} 'get_user'",
        f"{py}:5:1: {message} 'search'",
        f"{py}:10:1: {message} 'load'",
        f"{py}:15:5: {message} 'get'",
        f"{py}:18:5: {message} 'put'",
    ]
