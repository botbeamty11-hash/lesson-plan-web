"""User accounts + points ledger on disk (same DATA_DIR style as jobs)."""
import fcntl, json, os, uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

import store

USERS_DIR = None  # resolved lazily from store.DATA_DIR
TZ = timezone(timedelta(hours=7))


def _users_dir():
    d = os.path.join(store.DATA_DIR, "users")
    os.makedirs(d, exist_ok=True)
    return d


def _lock_path():
    return os.path.join(store.DATA_DIR, ".users.lock")


@contextmanager
def _lock():
    os.makedirs(store.DATA_DIR, exist_ok=True)
    with open(_lock_path(), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def _user_path(user_id):
    if not user_id or "/" in user_id or ".." in user_id:
        raise ValueError("bad user id")
    return os.path.join(_users_dir(), f"{user_id}.json")


def load_user(user_id):
    p = _user_path(user_id)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_user(user):
    p = _user_path(user["id"])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(user, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def find_by_google_sub(sub):
    if not sub:
        return None
    for u in list_users():
        if u.get("google_sub") == sub:
            return u
    return None


def find_by_email(email):
    if not email:
        return None
    email = email.lower().strip()
    for u in list_users():
        if (u.get("email") or "").lower() == email:
            return u
    return None


def upsert_google_user(*, sub, email, name, picture):
    """Create or update a user from Google OIDC claims. Returns user dict."""
    with _lock():
        u = find_by_google_sub(sub)
        if not u and email:
            u = find_by_email(email)
        now = now_iso()
        if u:
            u["google_sub"] = sub
            if email:
                u["email"] = email
            if name:
                u["name"] = name
            if picture:
                u["picture"] = picture
            u["last_login"] = now
            save_user(u)
            return u
        uid = "u_" + uuid.uuid4().hex[:12]
        u = {
            "id": uid,
            "google_sub": sub,
            "email": email or "",
            "name": name or (email.split("@")[0] if email else "ครู"),
            "picture": picture or "",
            "created_at": now,
            "last_login": now,
            "points": 0,
            "free_uses_left": 1,
            "ledger": [],
        }
        save_user(u)
        return u


def list_users():
    out = []
    d = _users_dir()
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out


def search_users(q):
    q = (q or "").strip().lower()
    users = list_users()
    if not q:
        return users
    return [u for u in users
            if q in (u.get("email") or "").lower()
            or q in (u.get("name") or "").lower()
            or q in (u.get("id") or "").lower()]


def points_totals():
    users = list_users()
    total_pts = sum(int(u.get("points") or 0) for u in users)
    return {"users": len(users), "points_outstanding": total_pts}


def adjust_points(user_id, amount, *, reason, job_id=None, admin=None, typ=None):
    """Add (positive) or deduct (negative) points. Raises ValueError if overdraw.
    Returns (user, entry)."""
    amount = int(amount)
    if amount == 0:
        raise ValueError("จำนวนพ้อยท์ต้องไม่เป็น 0")
    with _lock():
        u = load_user(user_id)
        if not u:
            raise KeyError(user_id)
        bal = int(u.get("points") or 0)
        new_bal = bal + amount
        if new_bal < 0:
            raise ValueError(f"พ้อยท์ไม่พอ (คงเหลือ {bal} ต้องการ {-amount})")
        entry = {
            "id": "tx_" + uuid.uuid4().hex[:10],
            "type": typ or ("credit" if amount > 0 else "debit"),
            "amount": amount,
            "balance_after": new_bal,
            "reason": (reason or "").strip() or ("เติมโดยแอดมิน" if amount > 0 else "หักโดยแอดมิน"),
            "job_id": job_id,
            "admin": admin,
            "at": now_iso(),
        }
        u["points"] = new_bal
        ledger = list(u.get("ledger") or [])
        ledger.insert(0, entry)
        u["ledger"] = ledger[:500]  # cap
        save_user(u)
        return u, entry


def ensure_points(user_id, cost, *, reason, job_id=None):
    """Deduct `cost` points if cost > 0. No-op if cost <= 0. Returns user or None."""
    cost = int(cost or 0)
    if cost <= 0:
        return load_user(user_id)
    u, _ = adjust_points(user_id, -cost, reason=reason, job_id=job_id, typ="spend")
    return u


DEFAULT_FREE_USES = 1


def free_uses_left(user):
    """Return free uses remaining. Missing field → default 1 (existing accounts)."""
    if not user:
        return 0
    if "free_uses_left" not in user:
        return DEFAULT_FREE_USES
    try:
        return max(0, int(user.get("free_uses_left") or 0))
    except (TypeError, ValueError):
        return 0


def set_free_uses(user_id, n, *, reason="แอดมินตั้งสิทธิ์ฟรี", admin=None):
    """Set free_uses_left absolutely. Returns user."""
    n = max(0, int(n))
    with _lock():
        u = load_user(user_id)
        if not u:
            raise KeyError(user_id)
        u["free_uses_left"] = n
        # audit note on ledger (0-amount marker via reason-only? skip ledger for free uses)
        u["_free_uses_note"] = {"at": now_iso(), "n": n, "reason": reason, "admin": admin}
        save_user(u)
        return u


def consume_free_use(user_id, *, reason="ใช้สิทธิ์ทดลองฟรี"):
    """Atomically consume one free use. Raises ValueError if none left.
    Returns (user, remaining)."""
    with _lock():
        u = load_user(user_id)
        if not u:
            raise KeyError(user_id)
        left = free_uses_left(u)
        if left <= 0:
            raise ValueError("ใช้สิทธิ์ฟรีครบแล้ว")
        u["free_uses_left"] = left - 1
        ledger = list(u.get("ledger") or [])
        entry = {
            "id": "tx_" + uuid.uuid4().hex[:10],
            "type": "free_use",
            "amount": 0,
            "balance_after": int(u.get("points") or 0),
            "free_uses_after": u["free_uses_left"],
            "reason": reason,
            "job_id": None,
            "admin": None,
            "at": now_iso(),
        }
        ledger.insert(0, entry)
        u["ledger"] = ledger[:500]
        save_user(u)
        return u, u["free_uses_left"]


def charge_for_service(user_id, points_cost, *, reason, free_trial_mode):
    """Charge a logged-in user for one service use.

    Returns dict:
      ok: bool
      points_spent: int
      used_free: bool
      show_promo: bool  # free just consumed, or insufficient points
      error: str|None
      user: dict|None
    """
    cost = int(points_cost or 0)
    u = load_user(user_id)
    if not u:
        return {"ok": False, "points_spent": 0, "used_free": False,
                "show_promo": False, "error": "ไม่พบผู้ใช้", "user": None}

    if not free_trial_mode:
        # Charging mode OFF: everything stays free (points_cost is display-only seed).
        return {"ok": True, "points_spent": 0, "used_free": False,
                "show_promo": False, "error": None, "user": u}

    # free_trial_mode ON
    left = free_uses_left(u)
    if left > 0:
        try:
            u, rem = consume_free_use(user_id, reason=reason or "ใช้สิทธิ์ทดลองฟรี")
        except ValueError as e:
            return {"ok": False, "points_spent": 0, "used_free": False,
                    "show_promo": True, "error": str(e), "user": load_user(user_id)}
        return {"ok": True, "points_spent": 0, "used_free": True,
                "show_promo": True,  # just consumed → show promo
                "error": None, "user": u}

    # no free uses — need points (even if cost is 0, treat as needing top-up when mode on
    # but if cost is 0, allow through without charge; admin should set prices)
    if cost <= 0:
        return {"ok": True, "points_spent": 0, "used_free": False,
                "show_promo": False, "error": None, "user": u}

    bal = int(u.get("points") or 0)
    if bal < cost:
        return {"ok": False, "points_spent": 0, "used_free": False,
                "show_promo": True,
                "error": f"พ้อยท์ไม่พอ — บริการนี้ใช้ {cost} พ้อยท์ (คุณมี {bal} พ้อยท์)",
                "user": u}
    try:
        u = ensure_points(user_id, cost, reason=reason)
    except ValueError as e:
        return {"ok": False, "points_spent": 0, "used_free": False,
                "show_promo": True, "error": str(e), "user": load_user(user_id)}
    return {"ok": True, "points_spent": cost, "used_free": False,
            "show_promo": False, "error": None, "user": u}
