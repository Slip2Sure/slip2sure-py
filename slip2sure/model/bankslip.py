from pydantic import BaseModel

from .base import Slip2SureCredit

class Slip2SureBankSlipAccountData(BaseModel):
    type: str | None
    value: str | None

class Slip2SureBankSlipAccount(BaseModel):
    displayName: str
    name: str | None
    proxy: Slip2SureBankSlipAccountData
    account: Slip2SureBankSlipAccountData

class Slip2SureBankSlipInfo(BaseModel):
    payload: str
    transRef: str
    ref1: str | None
    ref2: str | None
    ref3: str | None
    transDate: str
    transTime: str
    transDateTime: str
    sender: Slip2SureBankSlipAccount
    receiver: Slip2SureBankSlipAccount
    amount: float
    transFeeAmount: float
    paidLocalAmount: float
    paidLocalCurrency: str
    countryCode: str
    toMerchantId: str

class Slip2SureBankSlip(BaseModel):
    info: Slip2SureBankSlipInfo
    credit: Slip2SureCredit
    is_exist: bool