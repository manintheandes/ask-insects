import json
import tempfile
import unittest
from pathlib import Path

from askinsects.hosted import HostedConfig, hosted_request, load_config, save_config


class HostedClientTests(unittest.TestCase):
    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"

            save_config(HostedConfig(url="https://ask-insects.example", token="secret"), path=path)
            loaded = load_config(path=path)

            self.assertEqual(loaded.url, "https://ask-insects.example")
            self.assertEqual(loaded.token, "secret")

    def test_hosted_request_sends_bearer_token_and_json(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps({"ok": True}).encode("utf-8")

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


if __name__ == "__main__":
    unittest.main()
