from pathlib import Path

import pytest


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


@pytest.fixture
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
