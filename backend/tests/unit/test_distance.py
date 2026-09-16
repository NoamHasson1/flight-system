"""Tests for the great-circle distance calculation.

The cases below fall into three groups, each guarding a different kind of bug:

1. Real routes with published distances -- proves the formula is *correct*, not
   merely self-consistent. These are the anchors.
2. Mathematical invariants -- proves it behaves sanely everywhere, including at
   the awkward edges of the coordinate system.
3. Rejected input -- proves bad reference data fails loudly instead of silently
   producing a plausible-looking wrong number.
"""

import math

import pytest

from app.domain.distance import EARTH_RADIUS_KM, haversine_km

# Airport coordinates, cross-checked against the public-domain OurAirports
# dataset (davidmegginson.github.io/ourairports-data) -- every one agrees to
# within 0.71 km, and TLV is exact.
#
# They are duplicated here on purpose rather than imported from the dataset we
# ship in step 5. If these tests read that dataset, a bad row in it could make
# them pass for the wrong reason: the test and the thing under test would share
# a single point of failure. Please do not "tidy" this into an import.
#
# The sub-kilometre disagreements are not errors. An airport covers several
# square kilometres, so sources differ on whether the reference point is the
# terminal, the runway midpoint or the official Aerodrome Reference Point.
# Against the 88 km margin by which TLV-LHR clears the 3,500 km band boundary,
# it is noise.
TLV = (32.0114, 34.8867)  # Tel Aviv, Ben Gurion
LHR = (51.4706, -0.4619)  # London Heathrow
CDG = (49.0097, 2.5479)  # Paris, Charles de Gaulle
JFK = (40.6413, -73.7781)  # New York, JFK
SYD = (-33.9399, 151.1753)  # Sydney


# --- 1. Real routes, checked against published great-circle distances --------


@pytest.mark.parametrize(
    ("origin", "destination", "expected_km", "route"),
    [
        (TLV, LHR, 3570, "TLV-LHR"),
        (TLV, CDG, 3290, "TLV-CDG"),
        (TLV, JFK, 9130, "TLV-JFK"),
        (LHR, CDG, 348, "LHR-CDG"),
        (TLV, SYD, 14230, "TLV-SYD"),
    ],
)
def test_known_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    expected_km: float,
    route: str,
) -> None:
    """Distances match published figures to within 1%.

    1% is the right tolerance here: published figures vary slightly depending on
    which Earth radius and which airport reference point the publisher used, so
    demanding exactness would make the test brittle for no gain. 1% of even the
    tightest regulatory boundary (1,500 km) is 15 km -- nowhere near enough to
    move a flight into the wrong compensation band.
    """
    actual = haversine_km(*origin, *destination)
    assert actual == pytest.approx(expected_km, rel=0.01), (
        f"{route}: expected ~{expected_km} km, got {actual:.1f} km"
    )


# --- 2. Mathematical invariants ---------------------------------------------


def test_distance_to_itself_is_zero() -> None:
    """A degenerate case that naive implementations get wrong.

    Floating-point error inside sqrt() can produce a tiny negative or NaN result
    for identical points. This is also the real-world case of a flight whose
    origin and destination are the same airport (a diverted return).
    """
    assert haversine_km(*TLV, *TLV) == 0.0


def test_distance_is_symmetric() -> None:
    """TLV->LHR must equal LHR->TLV.

    Compensation cannot depend on travel direction, so an asymmetry here would
    be a real legal bug, not just an aesthetic one.
    """
    assert haversine_km(*TLV, *LHR) == pytest.approx(haversine_km(*LHR, *TLV))


def test_antipodal_points_are_half_the_circumference() -> None:
    """The maximum possible distance -- the upper bound of the whole function."""
    expected = math.pi * EARTH_RADIUS_KM  # ~20,015 km
    assert haversine_km(0.0, 0.0, 0.0, 180.0) == pytest.approx(expected)


def test_one_degree_of_longitude_at_the_equator() -> None:
    """Anchors the scale against a figure anyone can verify: ~111.19 km."""
    assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.19, rel=0.001)


def test_crossing_the_antimeridian_takes_the_short_way() -> None:
    """The classic longitude bug.

    Two points either side of the 180th meridian are 2 degrees apart, not 358.
    An implementation that subtracts longitudes without going through the
    trigonometry returns a wildly inflated distance. Pacific routes are real.
    """
    distance = haversine_km(0.0, 179.0, 0.0, -179.0)
    assert distance == pytest.approx(222.4, rel=0.01)


def test_poles_are_half_the_circumference_apart() -> None:
    """Extreme latitudes, where cos(phi) approaches zero."""
    expected = math.pi * EARTH_RADIUS_KM
    assert haversine_km(90.0, 0.0, -90.0, 0.0) == pytest.approx(expected)


def test_short_distances_stay_precise() -> None:
    """Guards the reason we use haversine at all.

    The naive spherical law-of-cosines formula loses precision catastrophically
    over short distances. One ten-thousandth of a degree of latitude is ~11.1 m;
    a formula suffering that cancellation would return 0 here.
    """
    distance = haversine_km(32.0000, 34.0000, 32.0001, 34.0000)
    assert distance == pytest.approx(0.01112, rel=0.01)


# --- 3. Invalid input must fail loudly --------------------------------------


@pytest.mark.parametrize(
    ("lat", "lon", "field"),
    [
        (91.0, 0.0, "latitude"),
        (-91.0, 0.0, "latitude"),
        (0.0, 181.0, "longitude"),
        (0.0, -181.0, "longitude"),
    ],
)
def test_rejects_impossible_coordinates(lat: float, lon: float, field: str) -> None:
    """Bad reference data must crash, not compute something plausible.

    If a malformed row in the airport dataset gives us latitude 91, the worst
    outcome is a confident wrong distance that quietly moves someone into the
    wrong compensation band. An exception is loud and gets fixed.
    """
    with pytest.raises(ValueError, match=field):
        haversine_km(lat, lon, 0.0, 0.0)
