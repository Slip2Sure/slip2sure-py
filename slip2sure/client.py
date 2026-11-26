"""Async client for the Slip2Sure slip verification API."""

import asyncio
import base64
import json
import random
import re
import time
import uuid
from datetime import datetime
from enum import Enum
from types import TracebackType
from typing import Any, Callable

import aiohttp
from aiohttp import FormData

from ._version import VERSION
from .exception import (
    ErrorCode,
    Slip2SureError,
    Slip2SureTransportError,
    Slip2SureValidationError,
)
from .model import (
    Slip2SureAPIKey,
    Slip2SureApplication,
    Slip2SureApplicationInput,
    Slip2SureBankSlip,
    Slip2SureTransactionList,
    Slip2SureTruemoney,
    Slip2SureUserCredit,
    SlipType,
    TransactionStatus,
)

__all__ = [
    "Slip2SureAPI",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
]

DEFAULT_BASE_URL = "https://api.slip2sure.com/api/v0"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF = 0.5

# Exponential growth is capped so a long retry chain cannot stall a call well
# past what the caller expected.
_MAX_RETRY_BACKOFF = 10.0

# Statuses worth retrying. Verification costs credits, so 500 is deliberately
# excluded: the request may have been processed and billed before failing, and
# retrying it could bill the caller twice. The statuses below all mean the
# request did not reach or complete processing.
_RETRYABLE_STATUS = frozenset({408, 429, 502, 503, 504})

# Which credential a request authenticates with.
_AUTH_API_KEY = "api-key"
_AUTH_USER_TOKEN = "user-token"

_MANAGEMENT_PATH = "/management/application"

# Magic bytes of the formats the API accepts, longest prefix first.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
)

# The "data:image/png;base64," preamble browsers prepend, which the API does
# not accept.
_DATA_URL_PREFIX = re.compile(r"^data:[^;,]*(;[^;,]*)*,")


def _detect_image(raw: bytes) -> tuple[str, str]:
    """Return the ``(extension, mime type)`` of ``raw``.

    Raises:
        Slip2SureValidationError: if ``raw`` is empty or is not a PNG or JPEG.
    """
    if not raw:
        raise Slip2SureValidationError(
            ErrorCode.FILE_REQUIRED.value, "image is empty"
        )

    for signature, extension, mime in _IMAGE_SIGNATURES:
        if raw.startswith(signature):
            return extension, mime

    raise Slip2SureValidationError(
        ErrorCode.FILE_NOT_SUPPORTED.value, "file not supported (PNG/JPEG only)"
    )


class Slip2SureAPI:
    """Client for the Slip2Sure API.

    Args:
        api_key: The Application API Key, sent as the ``x-api-key`` header.
            Required by the slip verification and transaction endpoints.
        user_api_token: The User API Token, sent as an ``Authorization``
            bearer token. Required by the credit and application management
            endpoints, which the Application API Key cannot authenticate.
        base_url: Override the API root, for staging or for a local mock.
        timeout: Seconds bounding one whole call including retries. ``None``
            disables the timeout.
        max_retries: How many times a retryable request is retried.
        retry_backoff: Base delay in seconds for exponential backoff.
        session: An ``aiohttp.ClientSession`` to use. When given, the caller
            keeps ownership and is responsible for closing it; otherwise the
            client creates one lazily and closes it in :meth:`close`.

    The client reuses a single session across calls, so prefer keeping one
    instance alive over building one per request::

        async with Slip2SureAPI("YOUR_API_KEY") as client:
            result = await client.scanBankSlipByPayload("YOUR_QR_CODE")

    Every method is available in camelCase, matching earlier releases, and in
    snake_case for callers who prefer PEP 8 naming.
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        user_api_token: str = "",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | None = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
        session: aiohttp.ClientSession | None = None,
    ):
        self._api_key = api_key
        self._user_api_token = user_api_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._retry_backoff = (
            retry_backoff if retry_backoff > 0 else DEFAULT_RETRY_BACKOFF
        )
        self._session = session
        self._owns_session = session is None

    # --- Slip verification -------------------------------------------------

    async def scanTruemoneySlip(self, file: bytes) -> Slip2SureTruemoney:
        """Verify a TrueMoney Wallet slip image against the v2 endpoint.

        v2 also returns the slip's payload and both parties' names.

        Args:
            file: The slip image as bytes. Must be PNG or JPEG; the format is
                detected from the contents, not from a filename.

        Raises:
            Slip2SureError: if the API rejects the request or is unreachable.
        """
        payload = await self._scan_image("/truemoney/v2/verify", file)
        return Slip2SureTruemoney(**payload)

    async def scanTruemoneySlipV1(self, file: bytes) -> Slip2SureTruemoney:
        """Verify a TrueMoney Wallet slip image against the v1 endpoint.

        Deprecated: use :meth:`scanTruemoneySlip`, which calls v2. v1 omits
        ``payload``, ``account_from_name`` and ``account_to_name``.
        """
        payload = await self._scan_image("/truemoney/v1/verify", file)
        return Slip2SureTruemoney(**payload)

    async def scanBankSlipByPayload(self, payload: str) -> Slip2SureBankSlip:
        """Verify a bank slip from the payload encoded in its QR code."""
        if not payload:
            raise Slip2SureValidationError(
                ErrorCode.VALIDATE_ERROR.value, "payload is empty"
            )

        body = await self._request(
            "POST",
            "/bank/v0/verifyByPayload",
            json_body={"payload": payload},
            retryable=True,
        )
        return Slip2SureBankSlip(**body)

    async def scanBankSlipByFile(self, file: bytes) -> Slip2SureBankSlip:
        """Verify a bank slip from its image.

        Use this when the QR code has not been decoded yet.

        Args:
            file: The slip image as bytes. Must be PNG or JPEG.
        """
        payload = await self._scan_image("/bank/v0/verifyByFile", file)
        return Slip2SureBankSlip(**payload)

    async def scanBankSlipByBase64(self, encoded: str) -> Slip2SureBankSlip:
        """Verify a bank slip from a base64 encoded image.

        A ``data:image/png;base64,`` prefix is stripped if present, since the
        API expects the bare encoding.
        """
        encoded = _DATA_URL_PREFIX.sub("", encoded.strip()).strip()
        if not encoded:
            raise Slip2SureValidationError(
                ErrorCode.VALIDATE_ERROR.value, "base64 image is empty"
            )

        body = await self._request(
            "POST",
            "/bank/v0/verifyByBase64",
            json_body={"payload": encoded},
            retryable=True,
        )
        return Slip2SureBankSlip(**body)

    async def scanBankSlipByImage(self, file: bytes) -> Slip2SureBankSlip:
        """Verify a bank slip by base64 encoding ``file`` for the caller.

        Prefer :meth:`scanBankSlipByFile`, which uploads the bytes directly
        and avoids the roughly one third size increase of base64. This exists
        for callers whose infrastructure cannot send multipart bodies.
        """
        _detect_image(file)
        return await self.scanBankSlipByBase64(base64.b64encode(file).decode("ascii"))

    # --- Transactions ------------------------------------------------------

    async def getAllTransactions(
        self,
        *,
        page: int | None = None,
        size: int | None = None,
        from_: datetime | str | None = None,
        to: datetime | str | None = None,
        paid_at: datetime | str | None = None,
        slip_type: SlipType | str | None = None,
        status: TransactionStatus | str | None = None,
    ) -> Slip2SureTransactionList:
        """List the application's verification history.

        Args:
            page: Zero based page number. The API defaults to 0.
            size: Items per page. The API defaults to 20.
            from_: Only slips scanned at or after this time. Named with a
                trailing underscore because ``from`` is a Python keyword.
            to: Only slips scanned at or before this time.
            paid_at: Only transfers made at this time.
            slip_type: Restrict to one :class:`SlipType`.
            status: Restrict to one :class:`TransactionStatus`.
        """
        params: dict[str, str] = {}
        # Compared against None rather than truthiness so page 0, a real
        # page, is still sent.
        if page is not None:
            params["page"] = str(page)
        if size is not None:
            params["size"] = str(size)
        if from_ is not None:
            params["from"] = _format_time(from_)
        if to is not None:
            params["to"] = _format_time(to)
        if paid_at is not None:
            params["paid_at"] = _format_time(paid_at)
        if slip_type is not None:
            params["slip_type"] = _enum_value(slip_type)
        if status is not None:
            params["status"] = _enum_value(status)

        body = await self._request(
            "GET",
            "/transaction/getAllTransactions",
            params=params,
            retryable=True,
        )
        return Slip2SureTransactionList(**body)

    # --- User --------------------------------------------------------------

    async def getUserCredit(self) -> Slip2SureUserCredit:
        """Return the account's remaining credit.

        Authenticates with the User API Token, so the client needs
        ``user_api_token``. The Application API Key was accepted here until
        3 October 2026 and no longer is.
        """
        body = await self._request(
            "GET", "/user/credit", auth=_AUTH_USER_TOKEN, retryable=True
        )
        return Slip2SureUserCredit(**body)

    # --- Application management --------------------------------------------
    #
    # Every endpoint below authenticates with the User API Token; the
    # Application API Key cannot authenticate them.

    async def getApplications(self) -> list[Slip2SureApplication]:
        """List the user's active applications."""
        body = await self._request(
            "GET", _MANAGEMENT_PATH, auth=_AUTH_USER_TOKEN, retryable=True, expect=list
        )
        return [Slip2SureApplication(**item) for item in body]

    async def getApplication(self, app_id: str) -> Slip2SureApplication:
        """Return one application by ID."""
        body = await self._request(
            "GET",
            _application_path(app_id),
            auth=_AUTH_USER_TOKEN,
            retryable=True,
        )
        return Slip2SureApplication(**body)

    async def createApplication(
        self,
        name: str,
        description: str = "",
        whitelist_ips: list[str] | None = None,
    ) -> Slip2SureApplication:
        """Create an application and return it with its API key.

        The API key is returned in full only here, so store it before
        discarding the result. This call is never retried automatically,
        because a retried gateway error could create a second application.

        Args:
            whitelist_ips: IPs allowed to use the key. Pass ``["*"]`` to allow
                every IP.
        """
        payload = Slip2SureApplicationInput(
            name=name, description=description, whitelist_ips=whitelist_ips or []
        )
        body = await self._request(
            "POST",
            _MANAGEMENT_PATH,
            json_body=payload.model_dump(),
            auth=_AUTH_USER_TOKEN,
        )
        return Slip2SureApplication(**body)

    async def updateApplication(
        self,
        app_id: str,
        name: str,
        description: str = "",
        whitelist_ips: list[str] | None = None,
    ) -> Slip2SureApplication:
        """Replace an application's name, description and IP whitelist."""
        payload = Slip2SureApplicationInput(
            name=name, description=description, whitelist_ips=whitelist_ips or []
        )
        body = await self._request(
            "PUT",
            _application_path(app_id),
            json_body=payload.model_dump(),
            auth=_AUTH_USER_TOKEN,
        )
        return Slip2SureApplication(**body)

    async def deleteApplication(self, app_id: str) -> None:
        """Delete an application. It cannot be undone through the API."""
        # The API answers 204 with no body on success.
        await self._request(
            "DELETE",
            _application_path(app_id),
            auth=_AUTH_USER_TOKEN,
            allow_empty=True,
        )

    async def getApplicationApiKey(self, app_id: str) -> Slip2SureAPIKey:
        """Return an application's current API key."""
        body = await self._request(
            "GET",
            _application_path(app_id, "/api_key"),
            auth=_AUTH_USER_TOKEN,
            retryable=True,
        )
        return Slip2SureAPIKey(**body)

    async def rotateApplicationApiKey(self, app_id: str) -> Slip2SureAPIKey:
        """Issue a new API key and invalidate the old one immediately.

        The new key is returned in full only here. This call is never retried
        automatically: a retried gateway error could rotate the key twice and
        discard the key the first attempt returned.
        """
        body = await self._request(
            "POST",
            _application_path(app_id, "/api_key/rotate"),
            auth=_AUTH_USER_TOKEN,
        )
        return Slip2SureAPIKey(**body)

    # --- Lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying session, if this client created it."""
        if self._session is not None and self._owns_session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "Slip2SureAPI":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    # --- HTTP --------------------------------------------------------------

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def _scan_image(self, path: str, file: bytes) -> dict[str, Any]:
        """Upload an image to a verification endpoint."""
        extension, mime = _detect_image(file)

        def build_form() -> FormData:
            # Rebuilt per attempt because an aiohttp FormData is consumed by
            # the request that sends it and cannot be replayed on a retry.
            form = FormData()
            form.add_field(
                "image",
                file,
                filename=f"{uuid.uuid4()}.{extension}",
                content_type=mime,
            )
            return form

        return await self._request(
            "POST", path, form_factory=build_form, retryable=True
        )

    def _check_auth(self, auth: str) -> None:
        """Fail locally when the credential a call needs is not configured."""
        if auth == _AUTH_USER_TOKEN:
            if not self._user_api_token:
                raise Slip2SureError(
                    ErrorCode.UNAUTHORIZED.value,
                    "no User API Token configured; pass user_api_token",
                )
        elif not self._api_key:
            raise Slip2SureError(
                ErrorCode.UNAUTHORIZED.value, "no Application API Key configured"
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        form_factory: Callable[[], FormData] | None = None,
        params: dict[str, str] | None = None,
        auth: str = _AUTH_API_KEY,
        retryable: bool = False,
        allow_empty: bool = False,
        expect: type = dict,
    ) -> Any:
        """Send a request, retrying transient failures, and return its JSON.

        ``retryable`` is False by default so a call with a side effect that
        must not happen twice, such as creating an application or rotating a
        key, is never retried behind the caller's back.
        """
        self._check_auth(auth)

        url = f"{self._base_url}{path}"
        session = self._get_session()
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        attempts = self._max_retries if retryable else 0

        last_error: Slip2SureError | None = None
        retry_after = 0.0

        for attempt in range(attempts + 1):
            if attempt:
                delay = self._backoff_for(attempt, retry_after)
                if deadline is not None and time.monotonic() + delay > deadline:
                    break
                await asyncio.sleep(delay)
            retry_after = 0.0

            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                break

            is_last = attempt == attempts

            try:
                async with session.request(
                    method,
                    url,
                    headers=self._headers(auth),
                    params=params or None,
                    json=json_body,
                    data=form_factory() if form_factory else None,
                    timeout=aiohttp.ClientTimeout(total=remaining),
                ) as response:
                    raw = await response.read()

                    if response.status >= 400:
                        error = self._parse_error(raw, response.status)
                        if is_last or response.status not in _RETRYABLE_STATUS:
                            raise error
                        last_error = error
                        retry_after = _parse_retry_after(
                            response.headers.get("Retry-After")
                        )
                        continue

                    return self._parse_success(
                        raw, response.status, allow_empty=allow_empty, expect=expect
                    )

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                error = Slip2SureTransportError(f"request failed: {exc}")
                if is_last:
                    raise error from exc
                last_error = error
                continue

        raise last_error or Slip2SureTransportError("request failed: timed out")

    def _headers(self, auth: str) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"slip2sure-py/{VERSION}",
        }
        if auth == _AUTH_USER_TOKEN:
            headers["Authorization"] = f"Bearer {self._user_api_token}"
        else:
            headers["x-api-key"] = self._api_key
        return headers

    def _backoff_for(self, attempt: int, retry_after: float) -> float:
        """Delay before ``attempt``, honouring a server Retry-After hint."""
        if retry_after > 0:
            return min(retry_after, _MAX_RETRY_BACKOFF)

        backoff = min(self._retry_backoff * (2 ** (attempt - 1)), _MAX_RETRY_BACKOFF)
        # Full jitter, so concurrent clients retrying after the same outage do
        # not line up into a second thundering herd.
        return backoff / 2 + random.uniform(0, backoff / 2)

    @staticmethod
    def _parse_error(raw: bytes, status: int) -> Slip2SureError:
        """Turn an error body into an error.

        Degrades gracefully when the body is not the expected JSON, which a
        proxy serving an HTML error page would previously have crashed on.
        """
        try:
            body = json.loads(raw)
            result = body["result"]
        except (ValueError, TypeError, KeyError):
            return Slip2SureError(
                ErrorCode.UNKNOWN_ERROR.value,
                _body_excerpt(raw, status),
                status,
            )

        return Slip2SureError.from_response(result, body.get("message", ""), status)

    @staticmethod
    def _parse_success(
        raw: bytes, status: int, *, allow_empty: bool, expect: type
    ) -> Any:
        if allow_empty and not raw.strip():
            return None
        try:
            body = json.loads(raw)
        except ValueError:
            raise Slip2SureError(
                ErrorCode.UNKNOWN_ERROR.value, _body_excerpt(raw, status), status
            ) from None
        if not isinstance(body, expect):
            raise Slip2SureError(
                ErrorCode.UNKNOWN_ERROR.value, _body_excerpt(raw, status), status
            )
        return body

    # --- snake_case aliases ------------------------------------------------
    #
    # The camelCase names above are what earlier releases shipped; these let
    # callers use PEP 8 naming instead. Both refer to the same function.

    scan_truemoney_slip = scanTruemoneySlip
    scan_truemoney_slip_v1 = scanTruemoneySlipV1
    scan_bank_slip_by_payload = scanBankSlipByPayload
    scan_bank_slip_by_file = scanBankSlipByFile
    scan_bank_slip_by_base64 = scanBankSlipByBase64
    scan_bank_slip_by_image = scanBankSlipByImage
    get_all_transactions = getAllTransactions
    get_user_credit = getUserCredit
    get_applications = getApplications
    get_application = getApplication
    create_application = createApplication
    update_application = updateApplication
    delete_application = deleteApplication
    get_application_api_key = getApplicationApiKey
    rotate_application_api_key = rotateApplicationApiKey


def _application_path(app_id: str, suffix: str = "") -> str:
    """Build a management path, rejecting an empty or path-bearing ID."""
    if not app_id:
        raise Slip2SureValidationError(
            ErrorCode.VALIDATE_ERROR.value, "application ID is empty"
        )
    if "/" in app_id:
        raise Slip2SureValidationError(
            ErrorCode.VALIDATE_ERROR.value, "application ID must not contain '/'"
        )
    return f"{_MANAGEMENT_PATH}/{app_id}{suffix}"


def _format_time(value: datetime | str) -> str:
    """Render a filter timestamp as ISO 8601."""
    return value.isoformat() if isinstance(value, datetime) else value


def _enum_value(value: Any) -> str:
    """Accept either an enum member or its raw string."""
    return value.value if isinstance(value, Enum) else str(value)


def _body_excerpt(raw: bytes, status: int) -> str:
    """Describe a body that is not a Slip2Sure envelope, keeping an excerpt."""
    excerpt = raw.decode("utf-8", errors="replace").strip()
    if not excerpt:
        return f"HTTP {status} with empty body"
    if len(excerpt) > 200:
        excerpt = excerpt[:200] + "..."
    return f"HTTP {status}: {excerpt}"


def _parse_retry_after(value: str | None) -> float:
    """Read a Retry-After header given as a delay in seconds."""
    if not value:
        return 0.0
    try:
        seconds = float(value.strip())
    except ValueError:
        return 0.0
    return seconds if seconds > 0 else 0.0
