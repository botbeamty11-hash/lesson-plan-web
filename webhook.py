"""Fire-and-forget Grok Bot webhook for new jobs and payment slips.

Reads GROKBOT_WEBHOOK_URL / GROKBOT_WEBHOOK_KEY from the environment.
If the URL is unset, notify() is a no-op. Failures never raise to the caller.
"""
import json
import logging
import os
import threading
import time
import urllib.request

log = logging.getLogger("lp-web")

DEBOUNCE_SEC = 20
_ALLOWED_EVENTS = frozenset(("job_queued", "payment_review"))

_lock = threading.Lock()
_recent = {}  # (event, job_id) -> monotonic timestamp


def _config():
    url = (os.environ.get("GROKBOT_WEBHOOK_URL") or "").strip()
    key = (os.environ.get("GROKBOT_WEBHOOK_KEY") or "").strip()
    header = (os.environ.get("GROKBOT_WEBHOOK_HEADER") or "").strip() or "X-Webhook-Key"
    return url, key, header


def reset_debounce_for_tests():
    with _lock:
        _recent.clear()


def _should_send(event, job_id):
    now = time.monotonic()
    stamp = (event, job_id)
    with _lock:
        last = _recent.get(stamp)
        if last is not None and (now - last) < DEBOUNCE_SEC:
            return False
        _recent[stamp] = now
        if len(_recent) > 256:
            cutoff = now - DEBOUNCE_SEC
            for k, ts in list(_recent.items()):
                if ts < cutoff:
                    _recent.pop(k, None)
        return True


def _post(url, key, header_name, payload):
    try:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
            headers[header_name] = key
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        log.warning("webhook failed: %s", e)


def notify(event, job_id, service_id=None):
    """POST a short event payload in a background thread. Returns True if a send was started."""
    url, key, header_name = _config()
    if not url:
        return False
    job_id = str(job_id or "").strip()
    event = str(event or "").strip()
    if not job_id or event not in _ALLOWED_EVENTS:
        return False
    if not _should_send(event, job_id):
        return False
    payload = {
        "event": event,
        "job_id": job_id,
        "service_id": service_id or "",
    }
    threading.Thread(
        target=_post,
        args=(url, key, header_name, payload),
        daemon=True,
    ).start()
    return True
