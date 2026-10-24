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
