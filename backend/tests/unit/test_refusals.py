"""Tests for the survey of what the system refuses to answer.

WHY THIS TASK EXISTS, AND WHY IT IS TESTED
------------------------------------------
Four bugs were found in one week, all the same shape: a guard that discards
information, written for a good reason, never measured. Every one was found
by a person trying a flight and noticing the answer was wrong -- which finds
the flights somebody happens to check and misses the rest.

This is the feedback loop that was missing. If it under-reports, the loop is
worse than useless: it says "fine" while claims are being refused, and
everybody stops looking.
"""

from collections import Counter

from app.tasks.refusals import _shape, report


def test_reasons_are_grouped_by_shape_not_by_flight() -> None:
    """THE thing that makes the ranking mean anything.

    Reasons name the flight that produced them -- "we do not recognise the
    airline BZ". Counted raw, that is one bucket per airline and the pattern
    is invisible: two hundred instances of one bug look like two hundred
    unrelated one-offs.
    """
    assert _shape("we do not recognise the airline BZ") == _shape(
        "we do not recognise the airline H7"
    )


def test_the_shape_still_distinguishes_different_problems() -> None:
    """Grouping must not go so far that two real bugs share a line."""
    assert _shape("the provider did not give us an arrival airport") != _shape(
        "the provider did not give us an departure airport"
    )


def test_the_report_ranks_worst_first() -> None:
    """The reason hit nine hundred times must be fixed before the one hit
    twice, and a report that does not order them leaves that to chance."""
    body = report(
        Counter({"rare problem": 2, "common problem": 900}),
        {"rare problem": [], "common problem": []},
        Counter({"ELIGIBLE": 10}),
        show=0,
    )

    assert body.index("common problem") < body.index("rare problem")


def test_examples_are_named_so_they_can_be_chased() -> None:
    """A count says something is wrong. A flight number says where to look,
    and without one the next step is writing a database query."""
    body = report(
        Counter({"a problem": 1}),
        {"a problem": ["BZ734 2026-09-19 [iaa]"]},
        Counter(),
        show=2,
    )

    assert "BZ734 2026-09-19 [iaa]" in body


def test_verdicts_are_reported_beside_refusals() -> None:
    """A refusal count alone cannot be judged. Eleven thousand refusals
    against seven thousand answers is a different product from eleven
    thousand against a million."""
    body = report(Counter({"x": 5}), {"x": []}, Counter({"ELIGIBLE": 106}), show=0)

    assert "106" in body and "ELIGIBLE" in body
