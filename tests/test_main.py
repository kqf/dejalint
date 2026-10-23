from pathlib import Path

import pytest

from dejalint.main import check

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
    assert check([src], min_nodes=8) == [
        f"{b}:1:1: DJL001 Duplicate function body 'other' (first at {a}:1)",
        f"{b}:8:1: DJL002 Duplicate name 'squares' (first at {a}:1)",
    ]


def test_clean(src: Path):
    assert check([src / "c.py"], min_nodes=8) == []
