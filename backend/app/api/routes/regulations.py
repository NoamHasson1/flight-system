"""What each law pays, read out of the rules themselves.

    GET /api/v1/regulations

WHY THIS ENDPOINT EXISTS AT ALL
-------------------------------
The site has a page explaining how much a passenger can claim. Those figures
also live in `app/domain/rules/` as the constants the engine actually applies.

Written twice, they drift. Not hypothetically: the Israeli amounts are
index-linked and revised, and the revision arrives as a line in a law, which
somebody applies to the rules and forgets on the page -- or to the page and
forgets in the rules. Either way the site then promises one number and the
check returns another, which is the single most damaging inconsistency this
product can have.

So the page reads them from here, and here reads them from the engine. One
source, and the copy cannot say something the system will not honour.

WHAT IS NOT HERE
----------------
Anything that is a judgement rather than a figure. The wording of the
exemptions, what counts as extraordinary, how notice is weighed -- that is
prose and it belongs in the page's own copy. This carries only what the
engine can be held to: thresholds, bands and amounts.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.domain.rules import ec261, israel, uk261

router = APIRouter(prefix="/api/v1/regulations", tags=["regulations"])


class BandOut(BaseModel):
    """One distance band and what it pays."""

    up_to_km: float | None = Field(
        description="Upper bound of the band. Null for the top band, which has none."
    )
    amount: str
    currency: str


class RegulationOut(BaseModel):
    key: str
    threshold_hours: float
    measured_at: str = Field(description="departure or arrival")
    bands: list[BandOut]


class RegulationsOut(BaseModel):
    regulations: list[RegulationOut]


def _bands(boundaries: tuple[float, ...], awards: tuple) -> list[BandOut]:  # type: ignore[type-arg]
    edges: list[float | None] = [*boundaries, None]
    return [
        BandOut(up_to_km=edge, amount=f"{award.amount:,.0f}", currency=award.currency.value)
        for edge, award in zip(edges, awards, strict=True)
    ]


_ISRAEL: Final = RegulationOut(
    key="ISRAEL",
    # Israeli law measures at DEPARTURE, and eight hours, not three. Getting
    # this the European way round is the easiest mistake to make here and it
    # denies real claims.
    threshold_hours=israel.MINIMUM_DEPARTURE_DELAY_HOURS,
    measured_at="departure",
    bands=_bands((israel.BAND_1_KM, israel.BAND_2_KM), israel.COMPENSATION),
)

_EC261: Final = RegulationOut(
    key="EC261",
    threshold_hours=ec261.MINIMUM_ARRIVAL_DELAY_HOURS,
    measured_at="arrival",
    bands=_bands((ec261.BAND_1_KM, ec261.BAND_2_KM), ec261.COMPENSATION),
)

_UK261: Final = RegulationOut(
    key="UK261",
    threshold_hours=uk261.MINIMUM_ARRIVAL_DELAY_HOURS,
    measured_at="arrival",
    bands=_bands((uk261.BAND_1_KM, uk261.BAND_2_KM), uk261.COMPENSATION),
)


@router.get("", response_model=RegulationsOut, summary="What each law pays")
def regulations() -> RegulationsOut:
    """The thresholds and amounts the engine applies, for the page that
    explains them."""
    return RegulationsOut(regulations=[_ISRAEL, _EC261, _UK261])
