from __future__ import annotations

import http.client
import json
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from web_server import QuestFlowLocalServer


class DummyApi:
    def bootstrap_shell(self):
        return {"app": {"name": "QuestFlow Studio", "version": "test"}, "deferred": True}

    def list_questions(self, search="", status="todos", offset=0, limit=500):
        return {"total": 1, "items": [{"uid": "1", "materia": search or "AUDITORIA"}]}


class LocalHttpEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="questflow_http_test_")
        self.web = Path(self.temp.name)
        (self.web / "index.html").write_text("<!doctype html><title>QuestFlow</title>", encoding="utf-8")
        self.server = QuestFlowLocalServer(DummyApi(), self.web)
        self.server.start()

    def tearDown(self):
        self.server.stop()
        self.temp.cleanup()

    def request(self, path: str, *, method="GET", payload=None, token=True):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {}
        if token:
            headers["X-QuestFlow-Token"] = self.server.token
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.server.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read(), response.headers

    def test_serves_static_interface(self):
        status, body, headers = self.request("/index.html", token=False)
        self.assertEqual(status, 200)
        self.assertIn(b"QuestFlow", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

    def test_rejects_api_without_session_token(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/health", token=False)
        self.assertEqual(context.exception.code, 401)

    def test_health_and_rpc(self):
        status, body, _ = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["transport"], "http-json")

        status, body, _ = self.request(
            "/api/call",
            method="POST",
            payload={"method": "list_questions", "args": ["TRIBUTÁRIO", "todos", 0, 20]},
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["items"][0]["materia"], "TRIBUTÁRIO")



    def test_heartbeat_body_is_consumed_on_keep_alive_connection(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        headers = {
            "X-QuestFlow-Token": self.server.token,
            "Content-Type": "application/json",
        }
        try:
            connection.request("POST", "/api/heartbeat", body="{}", headers=headers)
            first = connection.getresponse()
            self.assertEqual(first.status, 200)
            first.read()

            connection.request("GET", "/api/health", headers={"X-QuestFlow-Token": self.server.token})
            second = connection.getresponse()
            body = second.read()
            self.assertEqual(second.status, 200)
            self.assertEqual(json.loads(body)["transport"], "http-json")
        finally:
            connection.close()

    def test_post_health_and_malformed_get_are_supported(self):
        status, body, _ = self.request(
            "/api/health",
            method="POST",
            payload={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["transport"], "http-json")

        raw = (
            f"{{{{GET /api/health HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.server.port}\r\n"
            f"X-QuestFlow-Token: {self.server.token}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        with socket.create_connection(("127.0.0.1", self.server.port), timeout=5) as client:
            client.sendall(raw)
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        response = b"".join(chunks)
        self.assertIn(b" 200 ", response.split(b"\r\n", 1)[0])
        self.assertIn(b'"transport":"http-json"', response)

    def test_blocks_non_whitelisted_method(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request(
                "/api/call",
                method="POST",
                payload={"method": "shutdown", "args": []},
            )
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
