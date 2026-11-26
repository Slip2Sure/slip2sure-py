from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .bankslip import Slip2SureBankSlipAccountData

__all__ = [
    "SlipType",
    "TransactionStatus",
    "Slip2SureTransactionBank",
    "Slip2SureTransactionParty",
    "Slip2SureTransaction",
    "Slip2SurePagination",
    "Slip2SureTransactionList",
]


class SlipType(str, Enum):
    """The kind of slip a transaction verified."""

    TRUEMONEY_P2P = "TRUEMONEY_P2P"
    BANK_SLIP_VERIFY = "BANK_SLIP_VERIFY"


class TransactionStatus(str, Enum):
    """The outcome of a verification."""

    COMPLETED = "COMPLETED"
    FAIL = "FAIL"


class Slip2SureTransactionBank(BaseModel):
    """The bank behind an account."""

    name: str | None = None
    code: str | None = None
    # The PromptPay proxy type, such as EWALLETID.
    proxy: str | None = None


class Slip2SureTransactionParty(BaseModel):
    """One side of a recorded transfer."""

    name: str | None = None
    account: Slip2SureBankSlipAccountData = Field(
        default_factory=Slip2SureBankSlipAccountData
    )
    bank: Slip2SureTransactionBank = Field(default_factory=Slip2SureTransactionBank)


class Slip2SureTransaction(BaseModel):
    """One verification the application performed."""

    id: str
    # When the slip was scanned (UTC).
    created_at: datetime
    # When the transfer was made (UTC+7), None for a failed scan.
    paid_at: datetime | None = None
    transfer_id: str | None = None
    # Left as a plain str rather than the enum so a type added to the API
    # after this release does not fail validation.
    type: str
    status: str
    amount: float = 0.0
    fee: float = 0.0
    # Set when status is FAIL.
    error_code: str | None = None
    error_message: str | None = None
    ref1: str | None = None
    ref2: str | None = None
    ref3: str | None = None
    # None when the scan failed.
    sender: Slip2SureTransactionParty | None = None
    receiver: Slip2SureTransactionParty | None = None


class Slip2SurePagination(BaseModel):
    """Which page of results was returned."""

    # Zero based.
    current_page: int
    current_size: int
    total_page: int
    total_size: int
    is_end_page: bool
    is_start_page: bool
    is_empty_page: bool


class Slip2SureTransactionList(BaseModel):
    """A page of verification history."""

    result: str
    items: list[Slip2SureTransaction] = []
    pagination: Slip2SurePagination
