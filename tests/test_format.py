from pathlib import Path

from dejalint.main import Config, by_rule, check


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
