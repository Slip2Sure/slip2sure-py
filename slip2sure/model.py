from pydantic import BaseModel
from typing import Any

class Slip2SureInfo(BaseModel):
    transaction_id: str
    paid_at: str
    amount: float
    account_from_mobile: str | None
    account_to_mobile: str

class Slip2SureCredit(BaseModel):
    before: int
    usage: int
    after: int

class Slip2SureResponse(BaseModel):
    info: Slip2SureInfo
    credit: Slip2SureCredit
    is_exist: bool
