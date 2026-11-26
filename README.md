# Slip2Sure Python
SDK for integrating with the [Slip2Sure](https://slip2sure.com) slip verification service. (Python)

For the full API documentation, see:
- [API documentation index](https://app.slip2sure.com/user/api/docs)
- [Authentication](https://app.slip2sure.com/user/api/docs/authenticate) — Application API Key vs User API Token
- [TrueMoney slip](https://app.slip2sure.com/user/api/docs/truemoney/by-image)
- Bank slip — [by payload](https://app.slip2sure.com/user/api/docs/bankslip/by-payload), [by image](https://app.slip2sure.com/user/api/docs/bankslip/by-image), [by base64](https://app.slip2sure.com/user/api/docs/bankslip/by-base64)
- [Transactions](https://app.slip2sure.com/user/api/docs/transaction/get-all-transaction)
- [Credit balance](https://app.slip2sure.com/user/api/docs/user/credit-remaining)
- [Application management](https://app.slip2sure.com/user/api/docs/application/get-all-application)
- [Error codes](https://app.slip2sure.com/user/api/docs/errorcode)

## Install
```sh
pip install slip2sure
```

Requires Python 3.10 or newer; tested on 3.10 through 3.14. Ships type
annotations (PEP 561), so type checkers pick them up with no stubs needed.

## Example
### Truemoney
```py
import asyncio
from slip2sure import Slip2SureAPI

async def main():
    async with Slip2SureAPI("YOUR_API_KEY") as client:
        # You can use Flask or FastAPI to receive the body
        with open("FILE_PATH", "rb") as f:
            result = await client.scanTruemoneySlip(f.read())

        print(result.info.amount, result.info.paid_at)

asyncio.run(main())
```

### Bank Slip
```py
import asyncio
from slip2sure import Slip2SureAPI

async def main():
    async with Slip2SureAPI("YOUR_API_KEY") as client:
        result = await client.scanBankSlipByPayload("YOUR_QR_CODE")
        print(result.info.amount, result.info.sender.displayName)

asyncio.run(main())
```

The client holds one `aiohttp` session across calls, so keep a single instance
alive rather than building one per request. Use it as an async context manager,
or call `await client.close()` when you are done.

## Endpoints

Every method is available in camelCase, matching earlier releases, and in
snake_case for PEP 8 style. `scanTruemoneySlip` and `scan_truemoney_slip` are
the same function.

### Slip verification — needs the Application API Key

| Method | API |
| --- | --- |
| `scanTruemoneySlip(file)` | `POST /truemoney/v2/verify` |
| `scanTruemoneySlipV1(file)` | `POST /truemoney/v1/verify` (deprecated) |
| `scanBankSlipByPayload(payload)` | `POST /bank/v0/verifyByPayload` |
| `scanBankSlipByFile(file)` | `POST /bank/v0/verifyByFile` |
| `scanBankSlipByBase64(encoded)` | `POST /bank/v0/verifyByBase64` |
| `scanBankSlipByImage(file)` | same, base64 encoding the image for you |
| `getAllTransactions(...)` | `GET /transaction/getAllTransactions` |

### Account and management — needs the User API Token

| Method | API |
| --- | --- |
| `getUserCredit()` | `GET /user/credit` |
| `getApplications()` | `GET /management/application` |
| `getApplication(app_id)` | `GET /management/application/:id` |
| `createApplication(name, description, whitelist_ips)` | `POST /management/application` |
| `updateApplication(app_id, name, description, whitelist_ips)` | `PUT /management/application/:id` |
| `deleteApplication(app_id)` | `DELETE /management/application/:id` |
| `getApplicationApiKey(app_id)` | `GET /management/application/:id/api_key` |
| `rotateApplicationApiKey(app_id)` | `POST /management/application/:id/api_key/rotate` |

The two credentials are different things: the Application API Key verifies
slips, and the User API Token manages applications and reads your credit.
Configure both if you use both.

```py
client = Slip2SureAPI("YOUR_API_KEY", user_api_token="YOUR_USER_API_TOKEN")
```

### Bank slip from an image

```py
with open("FILE_PATH", "rb") as f:
    result = await client.scanBankSlipByFile(f.read())
```

### Transaction history

```py
from slip2sure import SlipType, TransactionStatus

page = await client.getAllTransactions(
    page=0,
    size=50,
    status=TransactionStatus.COMPLETED,
    slip_type=SlipType.BANK_SLIP_VERIFY,
)
for item in page.items:
    print(item.id, item.amount, item.status)
print("last page:", page.pagination.is_end_page)
```

The date filter is named `from_` because `from` is a Python keyword. Page 0 is
a real page, so passing `page=0` still sends the filter.

### Credit and applications

```py
credit = await client.getUserCredit()
print(credit.credit)        # a float, parsed from the API's string

app = await client.createApplication(
    "My store",
    "",
    ["203.0.113.10"],       # ["*"] allows every IP
)
# app.api_key is returned in full only here, so store it now.
```

## Configuration

```py
client = Slip2SureAPI(
    "YOUR_API_KEY",
    base_url="https://api.slip2sure.com/api/v0",
    timeout=30.0,        # seconds for the whole call, retries included; None disables
    max_retries=2,       # 0 disables
    retry_backoff=0.5,   # base delay for exponential backoff
    session=None,        # supply your own aiohttp.ClientSession
    user_api_token="",   # needed by the credit and management endpoints
)
```

When you pass a `session`, you keep ownership of it: `close()` leaves it open
for you to manage.

### Retries

Transient failures are retried with exponential backoff and full jitter, and a
`Retry-After` response header is honoured when present.

Only `408`, `429`, `502`, `503` and `504` are retried, along with connection
errors and timeouts. `500` is deliberately **not** retried: verification costs
credit, and a request that failed after being processed could otherwise be
billed twice.

`createApplication` and `rotateApplicationApiKey` are never retried at all,
whatever the status: a retried gateway error could create a second application
or rotate the key twice and discard the key the first attempt returned.

## Error handling

Every failure is a `Slip2SureError` carrying `.code`, `.message` and
`.status_code`. Catch a subclass to handle one family of failures:

```py
from slip2sure import (
    ErrorCode,
    Slip2SureAuthError,
    Slip2SureCreditError,
    Slip2SureError,
    Slip2SureNotFoundError,
    Slip2SureServerError,
    Slip2SureTransportError,
    Slip2SureValidationError,
)

try:
    result = await client.scanBankSlipByPayload("YOUR_QR_CODE")
except Slip2SureCreditError:
    ...                      # out of credit
except Slip2SureNotFoundError:
    ...                      # not a real slip
except Slip2SureError as exc:
    print(exc.code, exc.message, exc.status_code)
```

| Exception | Codes |
| --- | --- |
| `Slip2SureAuthError` | `INVALID_HEADER`, `UNAUTHORIZED`, `APPLICATION_LOCKED` |
| `Slip2SureValidationError` | `VALIDATE_ERROR`, `FILE_REQUIRED`, `FILE_TOO_LARGE`, `FILE_NOT_SUPPORTED` |
| `Slip2SureCreditError` | `CREDIT_INSUFFIENCT` |
| `Slip2SureNotFoundError` | `SLIP_NOT_EXIST` |
| `Slip2SureServerError` | `SERVER_ERROR`, `SERVICE_ERROR`, `SERVICE_TIMEOUT` |
| `Slip2SurePendingError` | `SLIP_BBL_PENDING` |
| `Slip2SureTransportError` | connection failures and timeouts |

`Slip2SureAuthError` also covers `IP_NOT_ALLOWED`, and `Slip2SureNotFoundError`
also covers `SLIP_QRCODE_NOT_EXIST` and `TRANSACTION_NOT_EXIST`; v1 defined
none of those four codes.

`Slip2SurePendingError` is worth handling on its own: Bangkok Bank returns
`SLIP_BBL_PENDING` for a few minutes after a transfer, and the same slip
succeeds on a later attempt.

A code this SDK predates still raises a plain `Slip2SureError` with `.code`
intact, rather than being flattened or raising a `KeyError`.

## Migrating from v1

- **v1 did not import on Python 3.10 or 3.11.** `client.py` used a nested
  same-quote f-string, which is only valid from 3.12, while the package
  declared `python_requires=">=3.10"`. This release works on 3.10 upward.
- **`scanBankSlipByPayload` no longer prints the response** to stdout.
- **Timestamps are `datetime`, not `str`.** `info.transDateTime` and
  `info.paid_at` are parsed, matching the Go SDK.
- **Optional fields now default instead of being required.** A slip whose
  account omitted `name` used to fail validation outright; `ref1`–`ref3`,
  `paidLocalCurrency`, `countryCode` and `toMerchantId` are likewise optional.
- **`scanTruemoneySlip` now calls the v2 endpoint**, which also returns
  `info.payload`, `info.account_from_name` and `info.account_to_name`. The v1
  endpoint is still reachable as `scanTruemoneySlipV1`.
- **`Slip2SureBankSlip` and `Slip2SureTruemoney` inherit `Slip2SureBase`.**
  `credit` and `is_exist` are unchanged.
- **Errors gained `.code`, `.message` and `.status_code`,** plus the subclasses
  above. The old `.errorCode` and `.errorMessage` attributes still work.
- **An uploaded file's MIME type is now `image/jpeg`** rather than the invalid
  `image/jpg`.
- **Dependencies are ranges, not exact pins,** so installing the SDK no longer
  forces a specific `pydantic` or `aiohttp` on your project.
- **There is now a 30 second default timeout.** v1 had none.

## Tests
```sh
python -m unittest discover
```

## LICENSE
[MIT](./LICENSE)
