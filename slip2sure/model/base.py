from pydantic import BaseModel

__all__ = ["Slip2SureCredit", "Slip2SureBase"]


class Slip2SureCredit(BaseModel):
    """Credit balance around a verification call."""

    before: float
    usage: float
    after: float


class Slip2SureBase(BaseModel):
    """Fields every verification response carries."""

    credit: Slip2SureCredit
    # Whether this slip had already been verified before, which is how
    # duplicate slips are detected.
    is_exist: bool
