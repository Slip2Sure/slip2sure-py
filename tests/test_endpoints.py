"""Tests for the endpoints added in 2.0, runnable with `python -m unittest`."""

import unittest

from aiohttp import web

from slip2sure import (
    ErrorCode,
    Slip2SureAuthError,
    Slip2SureError,
    Slip2SureNotFoundError,
    Slip2SurePendingError,
    Slip2SureValidationError,
    SlipType,
    TransactionStatus,
)

from .test_client import BANK_OK, ClientTestCase, png_bytes

TRUEMONEY_V2_OK = {
    "credit": {"before": 1000, "usage": 1, "after": 999},
    "is_exist": False,
    "info": {
        "payload": "00441999",
        "transaction_id": "50099999999999",
        "paid_at": "2025-02-07T14:00:30+07:00",
        "amount": 1000.25,
        "account_from_mobile": "XXXXXX8888",
        "account_from_name": "นายสหกิจ สม***",
        "account_to_mobile": "XXXXXX9999",
        "account_to_name": "นายกรมยัก นาระ",
    },
}

# A v1 response, which lacks every field v2 added.
TRUEMONEY_V1_OK = {
    "credit": {"before": 2, "usage": 1, "after": 1},
    "is_exist": False,
    "info": {
        "transaction_id": "T1",
        "paid_at": "2025-01-01T10:00:00Z",
        "amount": 25,
        "account_from_mobile": None,
        "account_to_mobile": "08x",
    },
}

TRANSACTIONS_OK = {
    "result": "SUCCESS",
    "items": [
        {
            "id": "id-1",
            # No timezone offset, unlike the slip endpoints.
            "created_at": "2026-07-08T17:38:39.744917",
            "paid_at": "2026-07-08T11:49:55",
            "transfer_id": "004.0X",
            "type": "BANK_SLIP_VERIFY",
            "status": "COMPLETED",
            "amount": 70,
            "error_code": None,
            "error_message": None,
            "fee": 0,
            "ref1": "REF001",
            "ref2": "REF002",
            "ref3": "",
            "receiver": {
                "account": {"type": None, "value": None},
                "name": "คุณมานี มีสุข",
                "bank": {"name": None, "code": None, "proxy": "EWALLETID"},
            },
            "sender": {
                "account": {"type": "BANKAC", "value": "xxx-x-x1234-x"},
                "name": "นาย สมชาย ใ.",
                "bank": {"name": "ธนาคารกสิกรไทย", "code": "004", "proxy": None},
            },
        },
        {
            "id": "id-2",
            "created_at": "2026-07-08T16:43:30.666779",
            "paid_at": None,
            "transfer_id": None,
            "type": "BANK_SLIP_VERIFY",
            "status": "FAIL",
            "amount": 0,
            "error_code": "SLIP_INVALID",
            "error_message": "Slip invalid",
            "fee": 0,
            "ref1": None,
            "ref2": None,
            "ref3": None,
            "sender": None,
            "receiver": None,
        },
    ],
    "pagination": {
        "current_page": 0,
        "current_size": 20,
        "total_page": 0,
        "total_size": 2,
        "is_end_page": True,
        "is_start_page": True,
        "is_empty_page": False,
    },
}

APP_OK = {
    "id": "app-1",
    "name": "My store stop (V2)",
    "description": "",
    "usage": 50,
    "whitelist_ips": ["203.0.113.10"],
    "created_at": "2025-02-14T16:14:30.322Z",
    "updated_at": "2025-02-14T16:14:30.322Z",
}


class TestTruemoneyVersions(ClientTestCase):
    async def test_default_uses_v2_and_exposes_new_fields(self):
        seen = {}

        async def handler(request):
            seen["path"] = request.path
            reader = await request.multipart()
            part = await reader.next()
            seen["field"] = part.name
            await part.read()
            return web.json_response(TRUEMONEY_V2_OK)

        client = self.client(await self.serve(handler))
        result = await client.scanTruemoneySlip(png_bytes())

        self.assertEqual(seen["path"], "/truemoney/v2/verify")
        self.assertEqual(seen["field"], "image")
        self.assertEqual(result.info.payload, "00441999")
        self.assertEqual(result.info.account_from_name, "นายสหกิจ สม***")
        self.assertEqual(result.info.account_to_name, "นายกรมยัก นาระ")
        self.assertEqual(result.info.amount, 1000.25)
        self.assertEqual(result.info.paid_at.year, 2025)

    async def test_v1_still_available_and_parses(self):
        seen = {}

        async def handler(request):
            seen["path"] = request.path
            reader = await request.multipart()
            await (await reader.next()).read()
            return web.json_response(TRUEMONEY_V1_OK)

        client = self.client(await self.serve(handler))
        result = await client.scanTruemoneySlipV1(png_bytes())

        self.assertEqual(seen["path"], "/truemoney/v1/verify")
        # v2-only fields must default rather than fail validation.
        self.assertIsNone(result.info.payload)
        self.assertIsNone(result.info.account_to_name)


class TestBankSlipVariants(ClientTestCase):
    async def test_by_file(self):
        seen = {}

        async def handler(request):
            seen["path"] = request.path
            reader = await request.multipart()
            part = await reader.next()
            seen["content_type"] = part.headers.get("Content-Type")
            seen["size"] = len(await part.read())
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler))
        result = await client.scanBankSlipByFile(png_bytes())

        self.assertEqual(seen["path"], "/bank/v0/verifyByFile")
        self.assertEqual(seen["content_type"], "image/png")
        self.assertGreater(seen["size"], 0)
        self.assertEqual(result.info.amount, 100.50)

    async def test_by_base64_strips_data_url(self):
        seen = {}

        async def handler(request):
            seen["path"] = request.path
            seen["body"] = await request.json()
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler))

        await client.scanBankSlipByBase64("QUJD")
        self.assertEqual(seen["path"], "/bank/v0/verifyByBase64")
        self.assertEqual(seen["body"], {"payload": "QUJD"})

        # A browser's data URL prefix must be stripped, not sent.
        await client.scanBankSlipByBase64("data:image/png;base64,QUJD")
        self.assertEqual(seen["body"], {"payload": "QUJD"})

        with self.assertRaises(Slip2SureValidationError):
            await client.scanBankSlipByBase64("   ")

    async def test_by_image_encodes_for_the_caller(self):
        seen = {}

        async def handler(request):
            seen["body"] = await request.json()
            return web.json_response(BANK_OK)

        client = self.client(await self.serve(handler))
        await client.scanBankSlipByImage(png_bytes())

        self.assertTrue(seen["body"]["payload"].startswith("iVBORw0KGgo"))

        # A non-image must still be rejected locally.
        with self.assertRaises(Slip2SureValidationError):
            await client.scanBankSlipByImage(b"%PDF-1.4 not an image")


class TestUserCredit(ClientTestCase):
    async def test_parses_string_credit_and_uses_bearer(self):
        seen = {}

        async def handler(request):
            seen["path"] = request.path
            seen["auth"] = request.headers.get("Authorization")
            seen["api_key"] = request.headers.get("x-api-key")
            return web.json_response({"credit": "36.85"})

        base_url = await self.serve(handler)
        client = self.client(base_url, user_api_token="USER_TOKEN")
        result = await client.getUserCredit()

        self.assertEqual(seen["path"], "/user/credit")
        self.assertEqual(seen["auth"], "Bearer USER_TOKEN")
        # The API key must not leak onto a user-token call.
        self.assertIsNone(seen["api_key"])
        self.assertEqual(result.credit, 36.85)

    async def test_requires_user_token(self):
        async def handler(request):
            raise AssertionError("should not have made a request")

        client = self.client(await self.serve(handler))
        with self.assertRaises(Slip2SureError) as ctx:
            await client.getUserCredit()
        self.assertEqual(ctx.exception.code, ErrorCode.UNAUTHORIZED.value)


class TestTransactions(ClientTestCase):
    async def test_parses_offsetless_timestamps_and_null_parties(self):
        seen = {}

        async def handler(request):
            seen["path"] = request.path
            seen["query"] = dict(request.query)
            return web.json_response(TRANSACTIONS_OK)

        client = self.client(await self.serve(handler))
        result = await client.getAllTransactions()

        self.assertEqual(seen["path"], "/transaction/getAllTransactions")
        self.assertEqual(seen["query"], {})
        self.assertEqual(len(result.items), 2)

        first = result.items[0]
        self.assertEqual(first.created_at.year, 2026)
        self.assertEqual(first.created_at.minute, 38)
        self.assertEqual(first.paid_at.hour, 11)
        self.assertEqual(first.status, TransactionStatus.COMPLETED.value)
        self.assertEqual(first.sender.bank.code, "004")
        self.assertEqual(first.receiver.bank.proxy, "EWALLETID")
        self.assertEqual(first.sender.account.type, "BANKAC")

        # A failed scan has null parties and a null paid_at.
        second = result.items[1]
        self.assertIsNone(second.sender)
        self.assertIsNone(second.receiver)
        self.assertIsNone(second.paid_at)
        self.assertEqual(second.error_code, "SLIP_INVALID")

        self.assertTrue(result.pagination.is_end_page)
        self.assertEqual(result.pagination.total_size, 2)

    async def test_sends_filters_including_page_zero(self):
        seen = {}

        async def handler(request):
            seen["query"] = dict(request.query)
            return web.json_response(TRANSACTIONS_OK)

        client = self.client(await self.serve(handler))
        await client.getAllTransactions(
            page=0,
            size=50,
            from_="2026-07-01T00:00:00Z",
            slip_type=SlipType.TRUEMONEY_P2P,
            status=TransactionStatus.FAIL,
        )

        # Page 0 is a real page, so a zero must still be sent.
        self.assertEqual(seen["query"]["page"], "0")
        self.assertEqual(seen["query"]["size"], "50")
        self.assertEqual(seen["query"]["from"], "2026-07-01T00:00:00Z")
        self.assertEqual(seen["query"]["slip_type"], "TRUEMONEY_P2P")
        self.assertEqual(seen["query"]["status"], "FAIL")
        # Unset filters must not appear at all.
        self.assertNotIn("to", seen["query"])
        self.assertNotIn("paid_at", seen["query"])


class TestApplicationManagement(ClientTestCase):
    async def start(self):
        self.seen = {}

        async def handler(request):
            self.seen["method"] = request.method
            self.seen["path"] = request.path
            self.seen["auth"] = request.headers.get("Authorization")
            if request.can_read_body:
                self.seen["body"] = await request.json()

            if request.method == "DELETE":
                return web.Response(status=204)  # no body at all
            if request.path.endswith("/api_key") or request.path.endswith("/rotate"):
                return web.json_response({"api_key": "NEW_KEY"})
            if request.method == "GET" and request.path == "/management/application":
                return web.json_response([APP_OK])
            if request.method == "POST":
                return web.json_response({**APP_OK, "api_key": "CREATED_KEY"})
            return web.json_response(APP_OK)

        base_url = await self.serve(handler)
        return self.client(base_url, user_api_token="USER_TOKEN")

    async def test_full_lifecycle(self):
        client = await self.start()

        apps = await client.getApplications()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0].id, "app-1")
        self.assertEqual(apps[0].whitelist_ips, ["203.0.113.10"])
        self.assertEqual(apps[0].created_at.year, 2025)
        self.assertEqual(self.seen["auth"], "Bearer USER_TOKEN")

        app = await client.getApplication("app-1")
        self.assertEqual(self.seen["path"], "/management/application/app-1")
        self.assertEqual(app.usage, 50)

        created = await client.createApplication(
            "My store stop (V2)", "", ["203.0.113.10"]
        )
        self.assertEqual(self.seen["method"], "POST")
        self.assertEqual(created.api_key, "CREATED_KEY")
        self.assertEqual(
            self.seen["body"],
            {
                "name": "My store stop (V2)",
                "description": "",
                "whitelist_ips": ["203.0.113.10"],
            },
        )

        await client.updateApplication("app-1", "My store stop (V3)")
        self.assertEqual(self.seen["method"], "PUT")
        self.assertEqual(self.seen["path"], "/management/application/app-1")

        key = await client.getApplicationApiKey("app-1")
        self.assertEqual(key.api_key, "NEW_KEY")
        self.assertEqual(self.seen["path"], "/management/application/app-1/api_key")

        rotated = await client.rotateApplicationApiKey("app-1")
        self.assertEqual(rotated.api_key, "NEW_KEY")
        self.assertEqual(
            self.seen["path"], "/management/application/app-1/api_key/rotate"
        )

        # 204 with no body must not be treated as a parse failure.
        self.assertIsNone(await client.deleteApplication("app-1"))
        self.assertEqual(self.seen["method"], "DELETE")

    async def test_rejects_bad_app_id(self):
        client = await self.start()
        for bad in ("", "a/b"):
            with self.subTest(app_id=bad):
                with self.assertRaises(Slip2SureValidationError):
                    await client.getApplication(bad)

    async def test_requires_user_token(self):
        async def handler(request):
            raise AssertionError("should not have made a request")

        client = self.client(await self.serve(handler))
        with self.assertRaises(Slip2SureError) as ctx:
            await client.getApplications()
        self.assertEqual(ctx.exception.code, ErrorCode.UNAUTHORIZED.value)


class TestMutatingCallsAreNotRetried(ClientTestCase):
    async def _count_calls(self, call):
        calls = {"n": 0}

        async def handler(request):
            calls["n"] += 1
            return web.json_response(
                {"result": "SERVER_ERROR", "message": "gateway"}, status=502
            )

        base_url = await self.serve(handler)
        client = self.client(base_url, user_api_token="T")
        with self.assertRaises(Slip2SureError):
            await call(client)
        return calls["n"]

    async def test_create_and_rotate_are_not_retried(self):
        """A retried gateway error could duplicate the application or discard
        the key the first attempt issued."""
        self.assertEqual(
            await self._count_calls(lambda c: c.createApplication("n")), 1
        )
        self.assertEqual(
            await self._count_calls(lambda c: c.rotateApplicationApiKey("app-1")), 1
        )

    async def test_reads_are_retried(self):
        self.assertEqual(await self._count_calls(lambda c: c.getApplications()), 3)
        self.assertEqual(await self._count_calls(lambda c: c.getUserCredit()), 3)


class TestNewErrorCodes(ClientTestCase):
    async def test_new_codes_map_to_classes(self):
        cases = [
            ("IP_NOT_ALLOWED", Slip2SureAuthError),
            ("SLIP_QRCODE_NOT_EXIST", Slip2SureNotFoundError),
            ("TRANSACTION_NOT_EXIST", Slip2SureNotFoundError),
            ("SLIP_BBL_PENDING", Slip2SurePendingError),
        ]
        for code, expected in cases:
            with self.subTest(code=code):

                async def handler(request, code=code):
                    return web.json_response(
                        {"result": code, "message": "m"}, status=403
                    )

                client = self.client(await self.serve(handler))
                with self.assertRaises(expected) as ctx:
                    await client.scanBankSlipByPayload("QR")
                self.assertEqual(ctx.exception.code, code)


if __name__ == "__main__":
    unittest.main()
