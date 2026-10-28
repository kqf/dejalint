import ast
from argparse import ArgumentParser
from pathlib import Path

import pytest

from dejalint.main import (
    Config,
    Rule,
    by_line,
    by_rule,
    check,
    each,
    find_pyproject,
    load_config,
    main,
    statement,
)


@pytest.fixture
def body() -> str:
    return """
    total = 0
    for x in xs:
        total += x * x
    return total
"""


@pytest.fixture
def original(tmp_path: Path, body) -> Path:
    opath = tmp_path / "a.py"
    opath.write_text(f"def squares(xs):{body}")
    return opath


@pytest.fixture
def duplicate(tmp_path: Path, body) -> Path:
    opath = tmp_path / "b.py"
    opath.write_text(
        f'''\
def other(xs):
    """Docstring is ignored."""{body}
class squares:
    pass
'''
    )
    return opath


def unique(tmp_path: Path) -> Path:
    opath = tmp_path / "c.py"
    opath.write_text(
        """\
def unique():
    return 1
"""
    )
    return opath


@pytest.fixture
def src(tmp_path: Path) -> Path:
    return tmp_path


def test_check(src: Path, original: Path, duplicate: Path):
    assert list(by_line(check([src], Config()))) == [
        (
            f"{duplicate}:1:1: DJL001 Duplicate function body 'other' "
            f"(first at {original}:1)"
        ),
        (
            f"{duplicate}:8:1: DJL002 Duplicate name 'squares' "
            f"(first at {original}:1)"
        ),
    ]


def test_clean(src: Path):
    assert check([src / "c.py"], Config()) == []


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


def test_noqa_other_code(src: Path, original: Path):
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


def test_by_rule(src: Path, original: Path, duplicate: Path):
    assert list(by_rule(check([src], Config()))) == [
        "DJL001:",
        (
            f"  {duplicate}:1:1: Duplicate function body 'other' "
            f"(first at {original}:1)"
        ),
        "DJL002:",
        f"  {duplicate}:8:1: Duplicate name 'squares' (first at {original}:1)",
    ]


def test_find_pyproject(tmp_path: Path):
    nested = tmp_path / "pkg" / "sub"
    nested.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    assert find_pyproject(nested) == tmp_path / "pyproject.toml"


def test_load_config(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """\
[tool.dejalint]
paths = ["src"]
min-nodes = 3
format = "rule"
"""
    )
    assert load_config(pyproject, ArgumentParser().error) == {
        "paths": [tmp_path / "src"],
        "min_nodes": 3,
        "format": "rule",
    }
    assert load_config(None, ArgumentParser().error) == {}


def test_load_config_unknown(tmp_path: Path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """\
[tool.dejalint]
foo = 1
"""
    )
    on_error = ArgumentParser().error
    with pytest.raises(SystemExit):
        load_config(pyproject, on_error)
    assert "unknown [tool.dejalint] options: foo" in capsys.readouterr().err


def test_main_invalid_format(src, monkeypatch):
    (src / "pyproject.toml").write_text(
        """\
[tool.dejalint]
format = "xml"
"""
    )
    monkeypatch.chdir(src)
    with pytest.raises(SystemExit):
        main([])
