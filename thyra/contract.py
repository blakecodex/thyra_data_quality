"""the contract at the door: what one published hub-hour has to look like to be let in.

a row that breaks the contract is not dropped. it is quarantined with a reason, so the
count of what arrived still adds up and the row can be replayed when the publisher fixes
the cause. the reasons are short, stable strings on purpose: a person reads them in the
morning, and a test asserts them.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .clock import hours_in_local_day

# nyiso's eleven load zones stand in for the hubs. the names are the publisher's, spaces and dots included.
HUBS = ("CAPITL", "CENTRL", "DUNWOD", "GENESE", "HUD VL", "LONGIL", "MHK VL", "MILLWD", "N.Y.C.", "NORTH", "WEST")

# prices in $/mwh. negative prices are real in this market, so the floor is well below zero;
# the cap sits above the market's own offer cap, so a value past it is a unit or parsing error.
PRICE_MIN, PRICE_MAX = -500.0, 5000.0
UNIT = "USD/MWh"


class PriceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hub: str
    day: date
    hour: int = Field(ge=1, le=25)  # position in the local day; the clock decides the real upper bound
    price_da: float = Field(ge=PRICE_MIN, le=PRICE_MAX)
    price_rt: float | None = Field(default=None, ge=PRICE_MIN, le=PRICE_MAX)
    unit: Literal["USD/MWh"]
    status: Literal["preliminary", "verified"]

    @model_validator(mode="after")
    def hour_fits_the_day(self):
        if self.hour > hours_in_local_day(self.day):
            raise ValueError("hour_beyond_day")
        return self

    @model_validator(mode="after")
    def hub_is_known(self):
        if self.hub not in HUBS:
            raise ValueError("unknown_hub")
        return self


def quarantine_reason(raw: dict) -> str | None:
    """none when the row passes; otherwise one short reason for the first failure found."""
    try:
        PriceRow(**raw)
        return None
    except ValidationError as e:
        err = e.errors()[0]
        etype, loc, msg = err["type"], err.get("loc", ()), err.get("msg", "")
        field = str(loc[0]) if loc else ""
        if etype == "extra_forbidden":
            return "unexpected_field"
        if etype == "missing":
            return "missing_field"
        if etype == "value_error":
            # our own rules raise with the reason as the message
            return msg.replace("Value error, ", "")
        if etype.endswith("_parsing") or etype.endswith("_type"):
            return "bad_type"
        if field == "unit":
            return "unit_not_usd_mwh"
        if field == "status":
            return "unknown_status"
        if field in ("price_da", "price_rt"):
            return "price_out_of_range"
        if field == "hour":
            return "hour_before_day" if etype == "greater_than_equal" else "hour_beyond_day"
        return etype


def validate(rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """split published rows into accepted and quarantined frames. the quarantined frame keeps the payload."""
    accepted, held = [], []
    for raw in rows:
        reason = quarantine_reason(raw)
        if reason is None:
            accepted.append(raw)
        else:
            held.append({**raw, "reason": reason})
    acc = pd.DataFrame(accepted, columns=list(PriceRow.model_fields))
    qua = pd.DataFrame(held)
    if qua.empty:
        qua = pd.DataFrame(columns=list(PriceRow.model_fields) + ["reason"])
    return acc, qua
