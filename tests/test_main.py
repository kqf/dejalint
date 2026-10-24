from pathlib import Path

import pytest

from dejalint.main import Config, by_line, by_rule, check

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


def test_by_rule(src: Path):
    a, b = src / "a.py", src / "b.py"
    assert list(by_rule(check([src], Config()))) == [
        "DJL001:",
        f"  {b}:1:1: Duplicate function body 'other' (first at {a}:1)",
        "DJL002:",
        f"  {b}:8:1: Duplicate name 'squares' (first at {a}:1)",
    ]
