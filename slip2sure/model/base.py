from pydantic import BaseModel

class Slip2SureCredit(BaseModel):
    before: float
    usage: float
    after: float
