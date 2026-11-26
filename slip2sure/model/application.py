from datetime import datetime

from pydantic import BaseModel

__all__ = [
    "Slip2SureApplication",
    "Slip2SureApplicationInput",
    "Slip2SureAPIKey",
]


class Slip2SureApplication(BaseModel):
    """An application belonging to the authenticated user."""

    id: str
    name: str
    description: str = ""
    # How many verifications this application has made.
    usage: float = 0.0
    # The IPs allowed to use this application's API key. A single "*" entry
    # allows every IP.
    whitelist_ips: list[str] = []
    created_at: datetime
    updated_at: datetime
    # Set only by create_application, which is the one response that returns
    # the key in full. Use get_application_api_key otherwise.
    api_key: str | None = None


class Slip2SureApplicationInput(BaseModel):
    """Body for creating or updating an application."""

    name: str
    description: str = ""
    # Use ["*"] to allow every IP.
    whitelist_ips: list[str] = []


class Slip2SureAPIKey(BaseModel):
    """An application's API key."""

    api_key: str
