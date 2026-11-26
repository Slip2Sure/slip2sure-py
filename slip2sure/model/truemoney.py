from datetime import datetime

from pydantic import BaseModel

from .base import Slip2SureBase

__all__ = ["Slip2SureTruemoneyInfo", "Slip2SureTruemoney"]


class Slip2SureTruemoneyInfo(BaseModel):
    """A verified TrueMoney Wallet transfer.

    ``payload``, ``account_from_name`` and ``account_to_name`` are returned by
    the v2 endpoint only, so they are None for a response from
    ``scanTruemoneySlipV1``.
    """

    # The slip's QR code data. v2 only.
    payload: str | None = None
    transaction_id: str
    paid_at: datetime
    amount: float
    # None when the sender's number is withheld.
    account_from_mobile: str | None = None
    # The sender's name. v2 only.
    account_from_name: str | None = None
    account_to_mobile: str
    # The recipient's name. v2 only.
    account_to_name: str | None = None


class Slip2SureTruemoney(Slip2SureBase):
    """Response of a TrueMoney Wallet slip verification."""

    info: Slip2SureTruemoneyInfo
