"""Tests for the figures the explanation page reads.

WHY THIS ENDPOINT IS WORTH TESTING AT ALL
-----------------------------------------
It exists to stop one specific failure: the page saying a number the engine
will not honour. Somebody reads "₪3,670", runs a check, and is told something
else. That is the most damaging inconsistency this product can have, because
it is the one that makes a person stop believing the answer.

So these assert that what the endpoint publishes IS what the rules apply --
not that it returns some plausible-looking JSON.
"""

from fastapi.testclient import TestClient

from app.domain.rules import ec261, israel, uk261


def test_the_published_figures_are_the_ones_the_engine_applies(
    client: TestClient,
) -> None:
    """THE test in this file.

    Read from the rule modules, not from a copy written here: a test with its
    own hardcoded 1530 passes happily on the day somebody changes one of the
    two and not the other, which is exactly the day it should fail.
    """
    published = {r["key"]: r for r in client.get("/api/v1/regulations").json()["regulations"]}

    for key, module in (
        ("ISRAEL", israel),
        ("EC261", ec261),
        ("UK261", uk261),
    ):
        amounts = [band["amount"].replace(",", "") for band in published[key]["bands"]]
        expected = [f"{money.amount:.0f}" for money in module.COMPENSATION]
        assert amounts == expected, f"{key} drifted from the engine"


def test_israel_is_measured_at_departure_and_europe_at_arrival(
    client: TestClient,
) -> None:
    """The easiest mistake in this whole system, stated out loud.

    Israeli law counts EIGHT hours at DEPARTURE; EC261 and UK261 count THREE
    at ARRIVAL. Getting it the European way round denies real Israeli claims,
    and a page explaining the law to customers must not teach it wrongly.
    """
    published = {r["key"]: r for r in client.get("/api/v1/regulations").json()["regulations"]}

    assert published["ISRAEL"]["measured_at"] == "departure"
    assert published["ISRAEL"]["threshold_hours"] == 8.0
    for european in ("EC261", "UK261"):
        assert published[european]["measured_at"] == "arrival"
        assert published[european]["threshold_hours"] == 3.0


def test_the_israeli_bands_are_not_the_european_ones(client: TestClient) -> None:
    """2,000 and 4,500 km, not 1,500 and 3,500.

    Two laws with the same shape and different numbers is how a plausible
    wrong answer gets written.
    """
    published = {r["key"]: r for r in client.get("/api/v1/regulations").json()["regulations"]}

    assert [b["up_to_km"] for b in published["ISRAEL"]["bands"]] == [2000.0, 4500.0, None]
    assert [b["up_to_km"] for b in published["EC261"]["bands"]] == [1500.0, 3500.0, None]


def test_the_top_band_has_no_upper_bound(client: TestClient) -> None:
    """Null rather than a large number, so the page can say "over 4,500" and
    never "4,500 to 99,999"."""
    for regulation in client.get("/api/v1/regulations").json()["regulations"]:
        assert regulation["bands"][-1]["up_to_km"] is None
