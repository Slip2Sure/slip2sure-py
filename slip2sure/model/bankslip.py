from datetime import datetime

from pydantic import BaseModel, Field

from .base import Slip2SureBase

__all__ = [
    "Slip2SureBankSlipAccountData",
    "Slip2SureBankSlipAccount",
    "Slip2SureBankSlipInfo",
    "Slip2SureBankSlip",
]


class Slip2SureBankSlipAccountData(BaseModel):
    """A typed account identifier.

    Both fields default to None because a slip carries either a proxy or an
    account, not both.
    """

    type: str | None = None
    value: str | None = None


class Slip2SureBankSlipAccount(BaseModel):
    """One side of a transfer."""

    displayName: str
    # Defaulted because banks do not always disclose the holder's name. It
    # was previously required, so any slip omitting it failed validation.
    name: str | None = None
    # The PromptPay proxy the transfer was addressed to, typed NATID,
    # MSISDN, EWALLETID or BILLERID.
    proxy: Slip2SureBankSlipAccountData = Field(
        default_factory=Slip2SureBankSlipAccountData
    )
    # The underlying bank account, typed BANKAC.
    account: Slip2SureBankSlipAccountData = Field(
        default_factory=Slip2SureBankSlipAccountData
    )


class Slip2SureBankSlipInfo(BaseModel):
    """A verified bank transfer."""

    payload: str
    transRef: str
    ref1: str | None = None
    ref2: str | None = None
    ref3: str | None = None
    transDate: str
    transTime: str
    transDateTime: datetime
    sender: Slip2SureBankSlipAccount
    receiver: Slip2SureBankSlipAccount
    amount: float
    transFeeAmount: float = 0.0
    paidLocalAmount: float = 0.0
    paidLocalCurrency: str | None = None
    countryCode: str | None = None
    toMerchantId: str | None = None


class Slip2SureBankSlip(Slip2SureBase):
    """Response of a bank slip verification."""

    info: Slip2SureBankSlipInfo
