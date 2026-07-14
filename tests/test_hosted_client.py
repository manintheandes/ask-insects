import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from askinsects.hosted import HostedConfig, hosted_request, load_config, save_config


class HostedClientTests(unittest.TestCase):
    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"

            save_config(HostedConfig(url="https://ask-insects.example", token="secret"), path=path)
            loaded = load_config(path=path)

            self.assertEqual(loaded.url, "https://ask-insects.example")
            self.assertEqual(loaded.token, "secret")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_hosted_request_sends_bearer_token_and_json(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self, size=-1):
                    data = json.dumps({"ok": True}).encode("utf-8")
                    return data if size is None or size < 0 else data[:size]

            return Response()

        payload = hosted_request(
            HostedConfig(url="https://ask-insects.example/", token="secret"),
            "POST",
            "/ask",
            {"question": "hello"},
            urlopen_fn=fake_urlopen,
        )

        request, timeout = calls[0]
        self.assertTrue(payload["ok"])
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(request.full_url, "https://ask-insects.example/ask")
        self.assertEqual(timeout, 120)

    def test_hosted_request_rejects_oversized_success_and_error_bodies(self):
        config = HostedConfig(url="https://ask-insects.example", token="secret")

        class OversizedResponse:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return b"x" * min(17, size)

        with self.assertRaisesRegex(ValueError, "configured byte limit"):
            hosted_request(
                config,
                "GET",
                "/context-package",
                urlopen_fn=lambda request, timeout: OversizedResponse(),
                max_response_bytes=16,
            )

        def oversized_error(request, timeout):
            raise HTTPError(
                request.full_url,
                500,
                "failure",
                {},
                io.BytesIO(b"/Users/josh/private token-secret"),
            )

        with self.assertRaisesRegex(ValueError, "configured byte limit"):
            hosted_request(
                config,
                "GET",
                "/context-package",
                urlopen_fn=oversized_error,
                max_response_bytes=16,
            )

    def test_hosted_request_rejects_declared_oversized_body_before_reading(self):
        class DeclaredOversizedResponse:
            headers = {"Content-Length": "17"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                raise AssertionError("oversized declared body must not be read")

        with self.assertRaisesRegex(ValueError, "configured byte limit"):
            hosted_request(
                HostedConfig(url="https://ask-insects.example", token="secret"),
                "GET",
                "/context-package",
                urlopen_fn=lambda request, timeout: DeclaredOversizedResponse(),
                max_response_bytes=16,
            )


if __name__ == "__main__":
    unittest.main()
