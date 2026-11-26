"""Tests for the Slip2Sure client, runnable with `python -m unittest`.

Built on unittest's IsolatedAsyncioTestCase so the suite needs no test
dependencies beyond what the SDK already requires.
"""

import asyncio
import contextlib
import io
import json
import time
import unittest
import zlib

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from slip2sure import (
    ErrorCode,
    Slip2SureAPI,
    Slip2SureAuthError,
    Slip2SureCreditError,
    Slip2SureError,
    Slip2SureNotFoundError,
    Slip2SureServerError,
    Slip2SureValidationError,
)

BANK_OK = {
    "credit": {"before": 10, "usage": 1, "after": 9},
    "is_exist": False,
    "info": {
        "payload": "P",
        "transRef": "R1",
        "ref1": None,
        "ref2": None,
        "ref3": None,
        "transDate": "20250101",
        "transTime": "10:00",
        "transDateTime": "2025-01-01T10:00:00Z",
        "sender": {
            "displayName": "A",
            "name": "Alice",
            "proxy": {"type": "MSISDN", "value": "08x"},
            "account": {"type": "BANKAC", "value": "1234"},
        },
        # No "name" key at all: banks omit it, and requiring it used to make
        # the whole response fail validation.
        "receiver": {
            "displayName": "B",
            "proxy": {"type": None, "value": None},
            "account": {"type": "BANKAC", "value": "5678"},
        },
        "amount": 100.50,
        "transFeeAmount": 0,
        "paidLocalAmount": 0,
        "paidLocalCurrency": "THB",
        "countryCode": "TH",
        "toMerchantId": "M1",
    },
}

TRUEMONEY_OK = {
    "credit": {"before": 2, "usage": 1, "after": 1},
    "is_exist": False,
    "info": {
        "transaction_id": "T1",
        "paid_at": "2025-01-01T10:00:00Z",
        "amount": 25.75,
        "account_from_mobile": None,
        "account_to_mobile": "08x",
    },
}


def png_bytes() -> bytes:
    """A minimal valid PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            len(data).to_bytes(4, "big")
            + kind
            + data
            + zlib.crc32(kind + data).to_bytes(4, "big")
        )

    header = (1).to_bytes(4, "big") * 2 + bytes([8, 0, 0, 0, 0])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\x00"))
        + chunk(b"IEND", b"")
    )


class ClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def serve(self, handler) -> str:
        """Start a server routing everything to handler, return its base URL."""
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", handler)
        server = TestServer(app)
        await server.start_server()
        self.addAsyncCleanup(server.close)
        return str(server.make_url("")).rstrip("/")

    def client(self, base_url: str, **kwargs) -> Slip2SureAPI:
        kwargs.setdefault("retry_backoff", 0.001)
        client = Slip2SureAPI("KEY", base_url=base_url, **kwargs)  # noqa: E501
        self.addAsyncCleanup(client.close)
        return client


class TestBankSlip(ClientTestCase):
    async def test_parses_and_keeps_satang(self):
        seen = {}

        async def handler(request):
            seen["key"] = request.headers.get("x-api-key")
            seen["body"] = await request.json()
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler))
        result = await client.scanBankSlipByPayload("QR")

        self.assertEqual(seen["key"], "KEY")
        self.assertEqual(seen["body"], {"payload": "QR"})
        self.assertEqual(result.info.amount, 100.50)
        self.assertEqual(result.credit.after, 9)
        self.assertFalse(result.is_exist)
        self.assertEqual(result.info.sender.name, "Alice")
        # Absent in the payload, so it must default rather than fail.
        self.assertIsNone(result.info.receiver.name)
        self.assertEqual(result.info.transDateTime.year, 2025)
        self.assertEqual(result.info.sender.proxy.type, "MSISDN")
        self.assertEqual(result.info.sender.account.type, "BANKAC")

    async def test_empty_payload_rejected_locally(self):
        async def handler(request):
            raise AssertionError("should not have made a request")

        client = self.client(await self.serve(handler))
        with self.assertRaises(Slip2SureValidationError) as ctx:
            await client.scanBankSlipByPayload("")
        self.assertEqual(ctx.exception.code, ErrorCode.VALIDATE_ERROR.value)

    async def test_does_not_print_to_stdout(self):
        """An earlier version left a debug print of every response body."""

        async def handler(request):
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await client.scanBankSlipByPayload("QR")
        self.assertEqual(buffer.getvalue(), "")


class TestTruemoney(ClientTestCase):
    async def test_uploads_and_replays_form_on_retry(self):
        calls = {"n": 0}
        seen = {}

        async def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return web.json_response(
                    {"result": "SERVICE_ERROR", "message": "slow down"}, status=503
                )
            reader = await request.multipart()
            part = await reader.next()
            seen["name"] = part.name
            seen["content_type"] = part.headers.get("Content-Type")
            seen["size"] = len(await part.read())
            return web.json_response(TRUEMONEY_OK)

        client = self.client(await self.serve(handler))
        result = await client.scanTruemoneySlip(png_bytes())

        self.assertEqual(calls["n"], 2)
        self.assertEqual(seen["name"], "image")
        self.assertEqual(seen["content_type"], "image/png")
        # The retried attempt must carry the image, not an exhausted body.
        self.assertGreater(seen["size"], 0)
        self.assertEqual(result.info.amount, 25.75)
        self.assertIsNone(result.info.account_from_mobile)

    async def test_rejects_non_image_locally(self):
        async def handler(request):
            raise AssertionError("should not have made a request")

        client = self.client(await self.serve(handler))

        with self.assertRaises(Slip2SureValidationError) as ctx:
            await client.scanTruemoneySlip(b"%PDF-1.4 not an image")
        self.assertEqual(ctx.exception.code, ErrorCode.FILE_NOT_SUPPORTED.value)

        with self.assertRaises(Slip2SureValidationError) as ctx:
            await client.scanTruemoneySlip(b"")
        self.assertEqual(ctx.exception.code, ErrorCode.FILE_REQUIRED.value)


class TestErrors(ClientTestCase):
    async def _error(self, status, body, **kwargs):
        async def handler(request):
            if isinstance(body, (dict, list)):
                return web.json_response(body, status=status)
            return web.Response(body=body, status=status, content_type="text/html")

        client = self.client(await self.serve(handler), **kwargs)
        with self.assertRaises(Slip2SureError) as ctx:
            await client.scanBankSlipByPayload("QR")
        return ctx.exception

    async def test_application_locked_is_mapped(self):
        """Defined but missing from the old error switch, so it surfaced as
        UNKNOWN_ERROR and lost the server's message."""
        error = await self._error(
            403, {"result": "APPLICATION_LOCKED", "message": "locked by admin"}
        )
        self.assertIsInstance(error, Slip2SureAuthError)
        self.assertEqual(error.code, ErrorCode.APPLICATION_LOCKED.value)
        self.assertEqual(error.message, "locked by admin")
        self.assertEqual(error.status_code, 403)

    async def test_error_families(self):
        cases = [
            (401, "UNAUTHORIZED", Slip2SureAuthError),
            (402, "CREDIT_INSUFFIENCT", Slip2SureCreditError),
            (404, "SLIP_NOT_EXIST", Slip2SureNotFoundError),
            (400, "FILE_TOO_LARGE", Slip2SureValidationError),
            (500, "SERVER_ERROR", Slip2SureServerError),
        ]
        for status, code, expected in cases:
            with self.subTest(code=code):
                error = await self._error(status, {"result": code, "message": "m"})
                self.assertIsInstance(error, expected)
                self.assertEqual(error.code, code)

    async def test_unknown_code_still_raises(self):
        error = await self._error(400, {"result": "BRAND_NEW_CODE", "message": "m"})
        self.assertIs(type(error), Slip2SureError)
        self.assertEqual(error.code, "BRAND_NEW_CODE")

    async def test_non_json_error_body(self):
        """A proxy's HTML error page used to crash on JSON decoding."""
        error = await self._error(502, b"<html>502 Bad Gateway</html>", max_retries=0)
        self.assertEqual(error.code, ErrorCode.UNKNOWN_ERROR.value)
        self.assertIn("502", error.message)
        self.assertEqual(error.status_code, 502)

    async def test_legacy_attribute_names_kept(self):
        error = await self._error(401, {"result": "UNAUTHORIZED", "message": "nope"})
        self.assertEqual(error.errorCode, "UNAUTHORIZED")
        self.assertEqual(error.errorMessage, "nope")

    async def test_missing_api_key(self):
        async def handler(request):
            raise AssertionError("should not have made a request")

        client = Slip2SureAPI("", base_url=await self.serve(handler))
        self.addAsyncCleanup(client.close)
        with self.assertRaises(Slip2SureError) as ctx:
            await client.scanBankSlipByPayload("QR")
        self.assertEqual(ctx.exception.code, ErrorCode.UNAUTHORIZED.value)


class TestRetry(ClientTestCase):
    async def test_retries_transient_then_succeeds(self):
        calls = {"n": 0}

        async def handler(request):
            calls["n"] += 1
            if calls["n"] <= 2:
                return web.json_response(
                    {"result": "SERVICE_ERROR", "message": "down"}, status=503
                )
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler))
        await client.scanBankSlipByPayload("QR")
        self.assertEqual(calls["n"], 3)

    async def test_does_not_retry_500(self):
        """A 500 may already have been billed, so retrying could double-charge."""
        calls = {"n": 0}

        async def handler(request):
            calls["n"] += 1
            return web.json_response(
                {"result": "SERVER_ERROR", "message": "boom"}, status=500
            )

        client = self.client(await self.serve(handler))
        with self.assertRaises(Slip2SureServerError):
            await client.scanBankSlipByPayload("QR")
        self.assertEqual(calls["n"], 1)

    async def test_does_not_retry_client_errors(self):
        calls = {"n": 0}

        async def handler(request):
            calls["n"] += 1
            return web.json_response(
                {"result": "UNAUTHORIZED", "message": "nope"}, status=401
            )

        client = self.client(await self.serve(handler))
        with self.assertRaises(Slip2SureAuthError):
            await client.scanBankSlipByPayload("QR")
        self.assertEqual(calls["n"], 1)

    async def test_retries_exhausted_raises_last_error(self):
        async def handler(request):
            return web.json_response(
                {"result": "SERVICE_ERROR", "message": "still down"}, status=503
            )

        client = self.client(await self.serve(handler), max_retries=1)
        with self.assertRaises(Slip2SureServerError) as ctx:
            await client.scanBankSlipByPayload("QR")
        self.assertEqual(ctx.exception.message, "still down")


class TestConfig(ClientTestCase):
    async def test_timeout_is_honoured(self):
        async def handler(request):
            await asyncio.sleep(5)
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler), timeout=0.2, max_retries=0)
        start = time.monotonic()
        with self.assertRaises(Slip2SureError):
            await client.scanBankSlipByPayload("QR")
        self.assertLess(time.monotonic() - start, 2.0)

    async def test_injected_session_is_not_closed(self):
        async def handler(request):
            return web.json_response(BANK_OK)

        base_url = await self.serve(handler)
        async with aiohttp.ClientSession() as session:
            client = Slip2SureAPI("KEY", base_url=base_url, session=session)
            await client.scanBankSlipByPayload("QR")
            await client.close()
            # Ownership stays with the caller, so close() must leave it open.
            self.assertFalse(session.closed)
            await client.scanBankSlipByPayload("QR")

    async def test_owned_session_is_reused_then_closed(self):
        async def handler(request):
            return web.json_response(BANK_OK)

        base_url = await self.serve(handler)
        async with Slip2SureAPI("KEY", base_url=base_url) as client:
            await client.scanBankSlipByPayload("QR")
            first = client._get_session()
            await client.scanBankSlipByPayload("QR")
            # One session across calls, rather than one per request.
            self.assertIs(client._get_session(), first)
        self.assertTrue(first.closed)

    async def test_base_url_trailing_slash(self):
        async def handler(request):
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler) + "/")
        await client.scanBankSlipByPayload("QR")


if __name__ == "__main__":
    unittest.main()
