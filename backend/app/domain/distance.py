"""Great-circle distance between two points on Earth.

EC261, UK261 and the Israeli Aviation Services Law all size compensation by the
great-circle distance between the departure airport and the *final destination* --
not by the distance the aircraft actually flew, and not by road distance.

This module is the whole of that calculation. It is deliberately dependency-free
and has no knowledge of airports, flights or money.
"""

from __future__ import annotations

import math
from typing import Final

# IUGG mean Earth radius. The Earth is not a sphere, so any single radius is a
# compromise; this one keeps the error under ~0.5%, which is far tighter than
# the distance bands in any of the three regulations (the closest call is the
# 1,500 km EC261 boundary, where 0.5% is 7.5 km).
EARTH_RADIUS_KM: Final = 6371.0088


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Return the great-circle distance in kilometres between two coordinates.

    Latitudes and longitudes are in decimal degrees. Raises ValueError if a
    coordinate is outside its valid range.
    """
    _validate(lat1, lon1)
    _validate(lat2, lon2)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    # Floating-point error can push `a` a hair above 1, which would make
    # asin() raise. Clamping costs nothing and removes the whole failure mode.
    a = min(1.0, max(0.0, a))

    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _validate(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        raise ValueError(f"latitude {lat} is outside the range -90..90")
    if not -180 <= lon <= 180:
        raise ValueError(f"longitude {lon} is outside the range -180..180")
