import ast
from pathlib import Path

import pytest

from dejalint.main import RULES, Config, Rule, by_line, check, each, statement


def only(code: str) -> list[Rule]:
    return [r for r in RULES if r.code == code]


def test_djl001(src: Path, original: Path, duplicate: Path):
    assert list(by_line(check([src], Config(), only("DJL001")))) == [
        (
            f"{duplicate}:1:1: DJL001 Duplicate function body 'other' "
            f"(first at {original}:1)"
        ),
    ]


def test_djl002(src: Path, original: Path, duplicate: Path):
    assert list(by_line(check([src], Config(), only("DJL002")))) == [
        (
            f"{duplicate}:8:1: DJL002 Duplicate name 'squares' "
            f"(first at {original}:1)"
        ),
    ]


def test_clean(unique: Path):
    assert check([unique], Config()) == []


@pytest.mark.parametrize(
    "source",
    [
        """\
def squares(xs):  # noqa: DJL001
    total = 0
    for x in xs:
        total += x * x
    return total
""",
        """\
def squares(xs):
    # noqa: E501, DJL001
    total = 0
    for x in xs:
        total += x * x
    return total
""",
    ],
)
def test_noqa(src: Path, original: Path, duplicate: Path, source: str):
    # Suppressing the first occurrence also silences its copy
    original.write_text(source)
    assert list(by_line(check([src], Config()))) == [
        (
            f"{duplicate}:8:1: DJL002 Duplicate name 'squares' "
            f"(first at {original}:1)"
        ),
    ]


def test_noqa_other_code(src: Path, original: Path, duplicate: Path):
    original.write_text(
        """\
def squares(xs):  # noqa: DJL002
    total = 0
    for x in xs:
        total += x * x
    return total
"""
    )
    codes = [v.code for v in check([src], Config())]
    assert codes == ["DJL001"]


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
    standalone = Rule(
        "TST001",
        assignments,
        each("Assignment '{}'"),
        noqa=statement,
    )
    assert list(by_line(check([py], Config(), [standalone]))) == [
        f"{py}:1:1: TST001 Assignment 'x'",
        f"{py}:5:1: TST001 Assignment 'x'",
    ]
