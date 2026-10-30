from argparse import ArgumentParser
from pathlib import Path

import pytest

from dejalint.main import find_pyproject, load_config, main


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
