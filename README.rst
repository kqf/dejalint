dejalint
========

.. image:: https://github.com/kqf/dejalint/actions/workflows/tests.yml/badge.svg
   :target: https://github.com/kqf/dejalint/actions
   :alt: Tests

.. image:: https://img.shields.io/pypi/dm/dejalint.svg
   :target: https://pypi.org/project/dejalint/
   :alt: PyPI Downloads

``dejalint`` is yet another linter.

----

Installation
------------

Install via pip:

.. code-block:: bash

    pip install dejalint

Configuration
-------------

Every command-line option can also be set in ``pyproject.toml``. The file is
looked up from the current directory upwards, and command-line arguments take
precedence over it. Paths are relative to the ``pyproject.toml`` location.

.. code-block:: toml

    [tool.dejalint]
    paths = ["src", "tests"]
    min-nodes = 8
    format = "line"  # or "rule"

Suppressing violations
----------------------

Add a ``noqa`` comment with the rule code either on the ``def`` / ``class``
line or right at the top of its body. A suppressed definition is left out of
the comparison entirely, so marking either copy silences the pair.

.. code-block:: python

    def squares(xs):  # noqa: DJL001
        ...

    def squares(xs):
        # noqa: DJL001
        ...

A bare ``# noqa`` without codes does not affect ``dejalint``. If you use Ruff,
declare the codes as external so it doesn't report them as unknown:

.. code-block:: toml

    [tool.ruff.lint]
    external = ["DJL"]

Pre-commit
----------

.. code-block:: yaml

    repos:
      - repo: https://github.com/kqf/dejalint
        rev: v0.x.y
        hooks:
          - id: dejalint
