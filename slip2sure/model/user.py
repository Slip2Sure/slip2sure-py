from pydantic import BaseModel

__all__ = ["Slip2SureUserCredit"]


class Slip2SureUserCredit(BaseModel):
    """The account's remaining credit.

    The API sends the balance as a JSON string ("36.85"); pydantic coerces it
    to a float so callers do not have to parse it themselves.
    """

    credit: float
