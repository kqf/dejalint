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

BODY = """
    total = 0
    for x in xs:
        total += x * x
    return total
"""


@pytest.fixture
def src(tmp_path: Path) -> Path:
    (tmp_path / "a.py").write_text(f"def squares(xs):{BODY}")
    (tmp_path / "b.py").write_text(
        f'def other(xs):\n    """Docstring is ignored."""{BODY}\n'
        "class squares:\n    pass\n"
    )
    (tmp_path / "c.py").write_text("def unique():\n    return 1\n")
    return tmp_path


def test_check(src: Path):
    a, b = src / "a.py", src / "b.py"
    assert list(by_line(check([src], Config()))) == [
        f"{b}:1:1: DJL001 Duplicate function body 'other' (first at {a}:1)",
        f"{b}:8:1: DJL002 Duplicate name 'squares' (first at {a}:1)",
    ]


def test_clean(src: Path):
    assert check([src / "c.py"], Config()) == []


@pytest.mark.parametrize(
    "header",
    [
        "def squares(xs):  # noqa: DJL001",
        "def squares(xs):\n    # noqa: E501, DJL001",
    ],
)
def test_noqa(src: Path, header: str):
    a, b = src / "a.py", src / "b.py"
    # Suppressing the first occurrence also silences its copy
    a.write_text(f"{header}{BODY}")
    assert list(by_line(check([src], Config()))) == [
        f"{b}:8:1: DJL002 Duplicate name 'squares' (first at {a}:1)",
    ]


def test_noqa_other_code(src: Path):
    (src / "a.py").write_text(f"def squares(xs):  # noqa: DJL002{BODY}")
    codes = [v.code for v in check([src], Config())]
    assert codes == ["DJL001"]


def assignments(path: Path, tree: ast.Module, config: Config):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            yield ast.unparse(node.targets[0]), node


def test_standalone_rule(tmp_path: Path):
    py = tmp_path / "a.py"
    py.write_text("x = 1\ny = (\n    2\n)  # noqa: TST001\nx = 3\n")
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


def test_by_rule(src: Path):
    a, b = src / "a.py", src / "b.py"
    assert list(by_rule(check([src], Config()))) == [
        "DJL001:",
        f"  {b}:1:1: Duplicate function body 'other' (first at {a}:1)",
        "DJL002:",
        f"  {b}:8:1: Duplicate name 'squares' (first at {a}:1)",
    ]


def test_find_pyproject(tmp_path: Path):
    nested = tmp_path / "pkg" / "sub"
    nested.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    assert find_pyproject(nested) == tmp_path / "pyproject.toml"


def test_load_config(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.dejalint]\npaths = ["src"]\nmin-nodes = 3\nformat = "rule"\n'
    )
    assert load_config(pyproject, ArgumentParser().error) == {
        "paths": [tmp_path / "src"],
        "min_nodes": 3,
        "format": "rule",
    }
    assert load_config(None, ArgumentParser().error) == {}


def test_load_config_unknown(tmp_path: Path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.dejalint]\nfoo = 1\n")
    on_error = ArgumentParser().error
    with pytest.raises(SystemExit):
        load_config(pyproject, on_error)
    assert "unknown [tool.dejalint] options: foo" in capsys.readouterr().err


def test_main_invalid_format(src, monkeypatch):
    (src / "pyproject.toml").write_text('[tool.dejalint]\nformat = "xml"\n')
    monkeypatch.chdir(src)
    with pytest.raises(SystemExit):
        main([])
