"""Tests for the check that tells you the archive is complete.

WHY THIS TASK IS WORTH TESTING
------------------------------
It is the only thing in the system whose job is to notice that something
else has failed. If it is wrong it is wrong in the worst direction: it says
"complete" while flights are being lost, and nobody looks again for months.

So these pin the two judgements it makes -- what counts as short, and which
direction of difference is a fault.
"""

from datetime import date

from app.tasks.coverage import HEALTHY, report

DAY = date(2026, 9, 27)


def test_matching_counts_are_fine() -> None:
    body, short = report([(DAY, 800, 800)])

    assert short is False
    assert "OK" in body


def test_holding_more_than_the_board_is_not_a_fault() -> None:
    """THE judgement that stops this crying wolf every single day.

    The board sheds the past continuously: a day captured in full this
    morning is already thinner on the board by tonight. An archive holding
    MORE than the board is the archive doing exactly its job, and a check
    that flagged it would be ignored within a week -- at which point it
    stops catching the failures it exists for.
    """
    body, short = report([(DAY, 270, 416)])

    assert short is False, body


def test_a_shortfall_is_reported_with_the_number_missing() -> None:
    """"SHORT" alone sends somebody to the database to find out how short.
    The count is what decides whether to backfill this morning or this
    month."""
    body, short = report([(DAY, 800, 400)])

    assert short is True
    assert "SHORT by 400" in body


def test_a_couple_of_rows_is_weather_not_a_fault() -> None:
    """The board is a live document. A flight can appear between the last
    archive run and this check, so exact equality would fail most days and
    teach everybody to ignore the report."""
    body, short = report([(DAY, 800, 795)])

    assert short is False, body


def test_the_threshold_is_where_it_says_it_is() -> None:
    """Pinned, because moving it silently is how a check stops checking."""
    _, just_under = report([(DAY, 1000, int(1000 * HEALTHY) - 1)])
    _, just_over = report([(DAY, 1000, int(1000 * HEALTHY) + 1)])

    assert just_under is True
    assert just_over is False


def test_a_day_with_nothing_archived_is_short() -> None:
    """The shape of a cron that stopped. It must not read as "no flights"."""
    body, short = report([(DAY, 800, 0)])

    assert short is True
    assert "SHORT by 800" in body


def test_an_empty_board_day_does_not_divide_by_zero() -> None:
    """A closed airport -- Yom Kippur -- publishes nothing, and a crash here
    would take out the check on exactly the day it looks most alarming."""
    _, short = report([(DAY, 0, 0)])

    assert short is False
