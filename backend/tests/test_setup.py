"""Sanity check on the toolchain itself.

It fails loudly if the interpreter running the suite is not the Python 3.12 we pinned, which is the
single most likely way this project breaks on a new machine.
"""

import sys


def test_python_is_at_least_3_12() -> None:
    assert sys.version_info >= (3, 12), f"expected Python 3.12+, got {sys.version}"
