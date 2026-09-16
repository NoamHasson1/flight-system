"""Tests for the airport and airline reference data.

These fall into three groups:

1. Lookups behave correctly, including the unknown-code case, which is the
   hook for the NEEDS_REVIEW verdict.
2. The shipped datasets are internally sound -- these are data tests, not code
   tests, and they run against all 4,133 rows.
3. Specific entries that decide jurisdiction are correct. A wrong country here
   silently applies the wrong law.
"""

import pytest

from app.domain.reference import (
    Airline,
    Airport,
    _airlines,
    _airports,
    _coordinates,
    _reject_duplicate,
    distance_between,
    find_airline,
    find_airport,
)

# --- 1. Lookups --------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "country"), [("TLV", "IL"), ("LHR", "GB"), ("CDG", "FR"), ("JFK", "US")]
)
def test_finds_known_airports(code: str, country: str) -> None:
    airport = find_airport(code)
    assert airport is not None
    assert airport.country == country


def test_unknown_airport_returns_none_rather_than_raising() -> None:
    """The single most important behaviour in this module.

    An unrecognised code must be able to become NEEDS_REVIEW. If this raised,
    the caller would be tempted to catch the exception and fall through to
    NOT_ELIGIBLE -- telling a passenger they have no claim because *we* did not
    recognise their airport. Returning None makes the missing case an ordinary
    value the caller has to handle deliberately.
    """
    assert find_airport("ZZZ") is None
    assert find_airline("ZZ") is None


@pytest.mark.parametrize("code", ["tlv", " TLV ", "Tlv", "  tlv"])
def test_lookup_is_case_and_whitespace_insensitive(code: str) -> None:
    """Provider payloads are not consistent about casing or padding."""
    airport = find_airport(code)
    assert airport is not None
    assert airport.iata == "TLV"


def test_distance_between_airports() -> None:
    """Ties the dataset back to the step 3 formula.

    3,588.6 km here versus the 3,588.7 km the hardcoded test coordinates give:
    a 100 m difference from coordinate precision, and the routes still land in
    the same compensation band, which is the only thing that matters.
    """
    tlv, lhr = find_airport("TLV"), find_airport("LHR")
    assert tlv is not None and lhr is not None
    assert distance_between(tlv, lhr) == pytest.approx(3588.6, abs=1.0)


# --- 2. Integrity of the shipped data ----------------------------------------
#
# These test the CSV files, not the code that reads them. They exist because a
# bad row does not crash -- it produces a confident wrong answer, which is the
# failure mode this whole system is built to avoid.


def test_airport_dataset_is_the_expected_size() -> None:
    """Catches a truncated or half-regenerated file.

    A loose bound, not an exact count: the upstream dataset legitimately gains
    and loses airports over time, and pinning the exact number would just make
    this test fail every time the data is refreshed.
    """
    assert 3500 <= len(_airports()) <= 5000


def test_every_airport_has_a_two_letter_country() -> None:
    """Country codes drive jurisdiction. A blank one would silently exclude a
    flight from every regulation."""
    bad = [a.iata for a in _airports().values() if len(a.country) != 2 or not a.country.isalpha()]
    assert bad == []


def test_every_airport_has_coordinates_in_range() -> None:
    """A latitude of 91 would not crash -- haversine would reject it later, at
    request time, on a real customer's check. Better to know now."""
    bad = [
        a.iata
        for a in _airports().values()
        if not (-90 <= a.latitude <= 90 and -180 <= a.longitude <= 180)
    ]
    assert bad == []


def test_no_airport_sits_at_exactly_zero_zero() -> None:
    """0,0 is in the Atlantic off Africa and is the classic signature of a
    missing coordinate that was defaulted rather than left blank."""
    bad = [a.iata for a in _airports().values() if a.latitude == 0.0 and a.longitude == 0.0]
    assert bad == []


def test_every_airline_has_a_two_letter_country() -> None:
    bad = [a.iata for a in _airlines().values() if len(a.country) != 2 or not a.country.isalpha()]
    assert bad == []


def test_airline_names_are_present() -> None:
    assert [a.iata for a in _airlines().values() if not a.name] == []


# --- 3. Entries that decide which law applies --------------------------------


@pytest.mark.parametrize(
    ("code", "country", "why"),
    [
        ("FR", "IE", "Ryanair is Irish, not British -- an EU carrier"),
        ("RK", "GB", "Ryanair UK is the separate British AOC"),
        ("U2", "GB", "easyJet UK"),
        ("W6", "HU", "Wizz Air is Hungarian -- an EU carrier"),
        ("W9", "GB", "Wizz Air UK is the separate British AOC"),
        ("LX", "CH", "Swiss is Swiss. Switzerland is NOT in the EU or the EEA"),
        ("DY", "NO", "Norwegian is Norwegian -- EEA, so EC261 applies"),
        ("FI", "IS", "Icelandair is Icelandic -- EEA"),
        ("TK", "TR", "Turkish is not an EU carrier, however European it feels"),
        ("LY", "IL", "El Al is Israeli, so EC261 does not cover it arriving into the EU"),
        ("BA", "GB", "British Airways"),
        ("LH", "DE", "Lufthansa"),
    ],
)
def test_carrier_nationality_is_correct(code: str, country: str, why: str) -> None:
    """Each of these has been picked wrong by somebody before.

    Carrier nationality is half of the EC261 and UK261 jurisdiction test. Get
    Ryanair wrong and every Ryanair flight arriving into the EU from outside it
    is wrongly excluded -- a silent, systematic underpayment.
    """
    airline = find_airline(code)
    assert airline is not None, f"{code} missing from airlines.csv"
    assert airline.country == country, why


def test_israeli_airports_are_israeli() -> None:
    """The three Israeli airports with scheduled commercial service.

    If TLV were filed under the wrong country the Israeli law would never fire
    at all, for any flight.

    Note the absentees. Ovda (VDA) is deliberately *not* here: it closed to
    civilian traffic in 2019 when Ramon (ETM) opened, and the dataset filter
    correctly drops it for having no scheduled service. This test asserted VDA
    on first writing and failed -- the data was right and the assumption was
    wrong, which is the whole point of testing the dataset.
    """
    for code in ("TLV", "ETM", "HFA"):
        airport = find_airport(code)
        assert airport is not None, f"{code} missing from airports.csv"
        assert airport.country == "IL"


# --- Malformed data must fail loudly at load time ----------------------------


@pytest.mark.parametrize(
    "row",
    [
        {"iata": "XXX", "latitude": "91.0", "longitude": "0.0"},
        {"iata": "XXX", "latitude": "0.0", "longitude": "181.0"},
        {"iata": "XXX", "latitude": "north", "longitude": "0.0"},
        {"iata": "XXX", "latitude": "", "longitude": "0.0"},
    ],
)
def test_bad_coordinates_are_rejected_with_a_locatable_message(row: dict[str, str]) -> None:
    """The error must name the file, the line and the code.

    "invalid coordinates" in a 4,133-row file is not an actionable error
    message; "airports.csv line 42 (XXX)" is.
    """
    with pytest.raises(ValueError, match=r"airports\.csv line 42 \(XXX\)"):
        _coordinates(row, "airports.csv", 42)


def test_duplicate_codes_are_rejected() -> None:
    """A duplicate would silently resolve to whichever row loaded last.

    This is our own shipped data, so a duplicate is a packaging mistake that
    should stop the process, not a user error to be tolerated.
    """
    with pytest.raises(ValueError, match="duplicate IATA code 'TLV'"):
        _reject_duplicate({"TLV": object()}, "TLV", "airports.csv", 42)


def test_loaded_types_are_immutable() -> None:
    """Reference data is shared process-wide and cached; if it were mutable,
    one request could corrupt it for every later request."""
    tlv = find_airport("TLV")
    assert isinstance(tlv, Airport)
    with pytest.raises(AttributeError):
        tlv.country = "GB"  # type: ignore[misc]
    ba = find_airline("BA")
    assert isinstance(ba, Airline)
    with pytest.raises(AttributeError):
        ba.country = "IL"  # type: ignore[misc]
