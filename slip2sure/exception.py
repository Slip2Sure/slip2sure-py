"""Errors raised by the Slip2Sure SDK.

Every API failure is a :class:`Slip2SureError` carrying the error code, the
server's message and the HTTP status code. Catch a subclass to handle one
family of failures, or the base class to handle them all::

    try:
        result = await client.scanBankSlipByPayload(qr)
    except Slip2SureCreditError:
        ...                      # out of credit
    except Slip2SureError as exc:
        print(exc.code, exc.message, exc.status_code)
"""

from enum import Enum

__all__ = [
    "ErrorCode",
    "Slip2SureError",
    "Slip2SureAuthError",
    "Slip2SureValidationError",
    "Slip2SureCreditError",
    "Slip2SureNotFoundError",
    "Slip2SureServerError",
    "Slip2SurePendingError",
    "Slip2SureTransportError",
]


class ErrorCode(str, Enum):
    """Error codes returned in the response's ``result`` field.

    Documented at https://app.slip2sure.com/user/api/docs/errorcode

    ``CREDIT_INSUFFIENCT`` keeps the misspelling the API actually sends.
    """

    INVALID_HEADER = "INVALID_HEADER"
    UNAUTHORIZED = "UNAUTHORIZED"
    IP_NOT_ALLOWED = "IP_NOT_ALLOWED"
    VALIDATE_ERROR = "VALIDATE_ERROR"
    APPLICATION_LOCKED = "APPLICATION_LOCKED"
    CREDIT_INSUFFIENCT = "CREDIT_INSUFFIENCT"
    FILE_REQUIRED = "FILE_REQUIRED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_NOT_SUPPORTED = "FILE_NOT_SUPPORTED"
    SLIP_NOT_EXIST = "SLIP_NOT_EXIST"
    SLIP_QRCODE_NOT_EXIST = "SLIP_QRCODE_NOT_EXIST"
    SLIP_BBL_PENDING = "SLIP_BBL_PENDING"
    TRANSACTION_NOT_EXIST = "TRANSACTION_NOT_EXIST"
    SERVER_ERROR = "SERVER_ERROR"
    SERVICE_ERROR = "SERVICE_ERROR"
    SERVICE_TIMEOUT = "SERVICE_TIMEOUT"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class Slip2SureError(Exception):
    """Base class for every Slip2Sure failure."""

    def __init__(self, result: str, message: str, status_code: int | None = None):
        super().__init__(f"[{result}] {message}")
        self.code = result
        self.message = message
        self.status_code = status_code

        # Kept so code written against earlier versions keeps working.
        self.errorCode = result
        self.errorMessage = message

    @classmethod
    def from_response(
        cls, result: str, message: str, status_code: int | None = None
    ) -> "Slip2SureError":
        """Build the most specific error class for ``result``.

        An unrecognised code still yields a ``Slip2SureError`` rather than
        raising, so a code added to the API after this release stays usable.
        """
        return _CODE_TO_ERROR.get(result, cls)(result, message, status_code)


class Slip2SureAuthError(Slip2SureError):
    """The API key is missing, wrong, or the application is locked."""


class Slip2SureValidationError(Slip2SureError):
    """The request or the uploaded file was rejected."""


class Slip2SureCreditError(Slip2SureError):
    """The account has run out of verification credit."""


class Slip2SureNotFoundError(Slip2SureError):
    """The slip does not exist."""


class Slip2SureServerError(Slip2SureError):
    """Slip2Sure or an upstream bank service failed."""


class Slip2SurePendingError(Slip2SureError):
    """The slip is still awaiting confirmation at the bank.

    Raised for ``SLIP_BBL_PENDING``, which Bangkok Bank returns for a few
    minutes after a transfer. Retry the same slip in 2-3 minutes.
    """


class Slip2SureTransportError(Slip2SureError):
    """The request never produced a usable response.

    Raised for connection failures and timeouts, where there is no server
    error code to report.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(ErrorCode.UNKNOWN_ERROR.value, message, status_code)


_CODE_TO_ERROR: dict[str, type[Slip2SureError]] = {
    ErrorCode.INVALID_HEADER.value: Slip2SureAuthError,
    ErrorCode.UNAUTHORIZED.value: Slip2SureAuthError,
    ErrorCode.APPLICATION_LOCKED.value: Slip2SureAuthError,
    ErrorCode.IP_NOT_ALLOWED.value: Slip2SureAuthError,
    ErrorCode.VALIDATE_ERROR.value: Slip2SureValidationError,
    ErrorCode.FILE_REQUIRED.value: Slip2SureValidationError,
    ErrorCode.FILE_TOO_LARGE.value: Slip2SureValidationError,
    ErrorCode.FILE_NOT_SUPPORTED.value: Slip2SureValidationError,
    ErrorCode.CREDIT_INSUFFIENCT.value: Slip2SureCreditError,
    ErrorCode.SLIP_NOT_EXIST.value: Slip2SureNotFoundError,
    ErrorCode.SLIP_QRCODE_NOT_EXIST.value: Slip2SureNotFoundError,
    ErrorCode.TRANSACTION_NOT_EXIST.value: Slip2SureNotFoundError,
    # Retryable by the caller after a short wait, so it gets its own class.
    ErrorCode.SLIP_BBL_PENDING.value: Slip2SurePendingError,
    ErrorCode.SERVER_ERROR.value: Slip2SureServerError,
    ErrorCode.SERVICE_ERROR.value: Slip2SureServerError,
    ErrorCode.SERVICE_TIMEOUT.value: Slip2SureServerError,
}
