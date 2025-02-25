
from pydantic import BaseModel

from .base import Slip2SureCredit

class Slip2SureTruemoneyInfo(BaseModel):
    transaction_id: str
    paid_at: str
    amount: float
    account_from_mobile: str | None
    account_to_mobile: str

class Slip2SureTruemoney(BaseModel):
    info: Slip2SureTruemoneyInfo
    credit: Slip2SureCredit
    is_exist: bool