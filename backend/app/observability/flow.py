"""A readable trace of one eligibility check, from request to database row.

WHY A DEDICATED MODULE
----------------------
Logging spread through the layers produces lines that interleave with every
other request and have to be reassembled by eye. This builds ONE block per
check, in order, so a person can read a whole decision in the terminal without
grepping — which is the only form of logging anybody actually uses while
working on something.

It is also why the formatting lives here rather than in the layers: the rules
must not learn to print, and the provider must not learn what a verdict is.
Each layer reports a fact; this decides how it reads.

WHAT IS DELIBERATELY NOT LOGGED
-------------------------------
* **The API key.** Never, in any form, including inside a URL.
* **National identity numbers.** Not masked — absent. A masked secret in a log
  is still a secret in a log, and these are the most sensitive field in the
  system.
* **Full email addresses.** Masked to `n***@example.com`: enough to confirm the
  right person was emailed, not enough to harvest.

Turn the whole thing off with LOG_FLOW=false.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("flight_system.flow")

WIDTH = 78
_RULE = "─" * WIDTH


def enabled() -> bool:
    return logger.isEnabledFor(logging.INFO)


def open_block(title: str, detail: str = "") -> None:
    logger.info("")
    logger.info(_RULE)
    logger.info("▸ %s%s", title, f"   {detail}" if detail else "")


def close_block() -> None:
    logger.info(_RULE)


def line(label: str, value: Any = "") -> None:
    """One labelled fact, aligned so a block scans as a column."""
    logger.info("  %-16s %s", label, value)


def header(label: str) -> None:
    """A label introducing indented lines, with no value of its own."""
    logger.info("  %s", label)


def wrapped(text: str, indent: int = 10) -> None:
    """Continuation text, wrapped on word boundaries.

    Truncating a sentence mid-word to fit a column makes the one thing worth
    reading -- the reason a law did or did not apply -- unreadable.
    """
    import textwrap

    pad = " " * indent
    for chunk in textwrap.wrap(text, WIDTH - len(pad) - 2) or [""]:
        logger.info("  %-16s %s%s", "", pad, chunk)


def cont(value: Any) -> None:
    """A continuation of the previous label, kept in the value column."""
    logger.info("  %-16s %s", "", value)


def mask_email(address: str | None) -> str:
    """`noam@example.com` -> `n***@example.com`.

    Enough to confirm the right person was contacted, not enough to harvest.
    """
    if not address or "@" not in address:
        return "—"
    local, _, domain = address.partition("@")
    head = local[0] if local else "?"
    return f"{head}***@{domain}"


def hours(value: float | None) -> str:
    if value is None:
        return "—"
    total = round(abs(value) * 60)
    sign = "-" if value < 0 else ""
    return f"{sign}{total // 60}h {total % 60:02d}m"
