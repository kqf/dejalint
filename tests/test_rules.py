import ast
from pathlib import Path

import pytest

from dejalint.main import RULES, Config, Rule, by_line, check, each, statement


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
