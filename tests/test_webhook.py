"""Grok Bot webhook: fires on queued jobs and slip review; silent when env is unset."""
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import webhook  # noqa: E402


ENV_KEYS = ("GROKBOT_WEBHOOK_URL", "GROKBOT_WEBHOOK_KEY", "GROKBOT_WEBHOOK_HEADER")


class Recorder:
    def __init__(self, delay=0):
        self.requests = []
        self.got = threading.Event()
        self.delay = delay

    def handler_class(self):
        rec = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if rec.delay:
                    time.sleep(rec.delay)
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    body = raw
                rec.requests.append({
                    "path": self.path,
                    "headers": {k: v for k, v in self.headers.items()},
                    "body": body,
                })
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                rec.got.set()

            def log_message(self, fmt, *args):
                pass

        return Handler


class WebhookTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        webhook.reset_debounce_for_tests()
        self.httpd = None
        self.thread = None
        self.rec = None

    def tearDown(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        webhook.reset_debounce_for_tests()

    def _start_server(self, delay=0):
        self.rec = Recorder(delay=delay)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self.rec.handler_class())
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        return f"http://127.0.0.1:{port}/hook"

    def _wait(self, timeout=2.0):
        return self.rec.got.wait(timeout)

    def test_no_url_is_noop(self):
        url = self._start_server()
        # env deliberately unset
        started = webhook.notify("job_queued", "job-1", "lesson_plan")
        self.assertFalse(started)
        time.sleep(0.3)
        self.assertEqual(self.rec.requests, [])
        # sanity: the mock server itself works if we had set the env
        self.assertTrue(url.startswith("http://127.0.0.1:"))

    def test_fires_job_queued_with_auth_headers(self):
        url = self._start_server()
        os.environ["GROKBOT_WEBHOOK_URL"] = url
        os.environ["GROKBOT_WEBHOOK_KEY"] = "test-secret-key"
        started = webhook.notify("job_queued", "abc123", "lesson_plan")
        self.assertTrue(started)
        self.assertTrue(self._wait(), "webhook was not received")
        self.assertEqual(len(self.rec.requests), 1)
        req = self.rec.requests[0]
        self.assertEqual(req["body"], {
            "event": "job_queued",
            "job_id": "abc123",
            "service_id": "lesson_plan",
        })
        self.assertEqual(set(req["body"]), {"event", "job_id", "service_id"})
        self.assertEqual(req["headers"].get("Authorization"), "Bearer test-secret-key")
        self.assertEqual(req["headers"].get("X-Webhook-Key"), "test-secret-key")
        self.assertTrue(req["headers"].get("Content-Type", "").startswith("application/json"))

    def test_fires_payment_review_and_custom_header_name(self):
        url = self._start_server()
        os.environ["GROKBOT_WEBHOOK_URL"] = url
        os.environ["GROKBOT_WEBHOOK_KEY"] = "k2"
        os.environ["GROKBOT_WEBHOOK_HEADER"] = "X-Grokbot-Hook"
        started = webhook.notify("payment_review", "topup-9", "points_topup")
        self.assertTrue(started)
        self.assertTrue(self._wait(), "webhook was not received")
        req = self.rec.requests[0]
        self.assertEqual(req["body"], {
            "event": "payment_review",
            "job_id": "topup-9",
            "service_id": "points_topup",
        })
        self.assertEqual(req["headers"].get("Authorization"), "Bearer k2")
        self.assertEqual(req["headers"].get("X-Grokbot-Hook"), "k2")
        # default header name must not also be required when a custom name is set
        self.assertIsNone(req["headers"].get("X-Webhook-Key"))

    def test_debounce_same_event_and_job(self):
        url = self._start_server()
        os.environ["GROKBOT_WEBHOOK_URL"] = url
        os.environ["GROKBOT_WEBHOOK_KEY"] = "k"
        self.assertTrue(webhook.notify("job_queued", "same-job", "slides"))
        self.assertTrue(self._wait(), "first webhook missing")
        self.rec.got.clear()
        second = webhook.notify("job_queued", "same-job", "slides")
        self.assertFalse(second)
        time.sleep(0.3)
        self.assertEqual(len(self.rec.requests), 1)
        # a different event for the same job is allowed
        self.assertTrue(webhook.notify("payment_review", "same-job", "slides"))
        self.assertTrue(self._wait(), "second event missing")
        self.assertEqual(len(self.rec.requests), 2)
        self.assertEqual(self.rec.requests[1]["body"]["event"], "payment_review")

    def test_notify_returns_before_slow_server(self):
        url = self._start_server(delay=3)
        os.environ["GROKBOT_WEBHOOK_URL"] = url
        os.environ["GROKBOT_WEBHOOK_KEY"] = "k"
        t0 = time.monotonic()
        started = webhook.notify("job_queued", "slow-1", "ocr")
        elapsed = time.monotonic() - t0
        self.assertTrue(started)
        self.assertLess(elapsed, 0.5, "notify must not block on the HTTP call")
        self.assertTrue(self._wait(timeout=6), "delayed webhook never arrived")

    def test_rejects_unknown_event(self):
        url = self._start_server()
        os.environ["GROKBOT_WEBHOOK_URL"] = url
        self.assertFalse(webhook.notify("teacher_email", "j1", "lesson_plan"))
        time.sleep(0.2)
        self.assertEqual(self.rec.requests, [])


if __name__ == "__main__":
    unittest.main()
