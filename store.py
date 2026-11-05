"""Job storage on disk, shared by the web app and worker_cli.py."""
import fcntl, json, os, shutil, time, uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("LP_DATA_DIR", os.path.join(BASE, "data"))
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
TEMPLATE_DIR = os.path.join(DATA_DIR, "template")
TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, "main.docx")
LOCK_PATH = os.path.join(DATA_DIR, ".lock")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
QR_IMAGE_PATH = os.path.join(DATA_DIR, "promptpay_qr.png")
QR_GENERATED_PATH = os.path.join(DATA_DIR, "promptpay_qr_generated.png")
DEFAULT_MINUTES = 8.0
OPTIONS = ["ทำภาพประกอบเพิ่ม", "ทำใบงาน/ใบความรู้แนบท้าย", "แก้คำผิดและเนื้อหาที่ผิด"]
OPT_ILLUSTRATIONS = OPTIONS[0]
SLOW_FACTOR = 1.5  # from-scratch jobs or extra illustrations take longer (applied once)
TZ = timezone(timedelta(hours=7))

DEFAULT_TEMPLATE_SRC = os.path.join(BASE, "default_template", "main.docx")

# Payment defaults (overridable via admin settings)
DEFAULT_PRICE_PER_PLAN = 10.0
DEFAULT_PAYEE_NAME = "พิภูษณ ยิ้มหนองโพธิ์"
DEFAULT_PROMPTPAY_ID = ""

# Job statuses involving payment (not claimable until queued)
PAYMENT_STATUSES = ("awaiting_payment", "payment_review", "payment_rejected")
CLAIMABLE_STATUSES = ("queued",)
SLIP_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}
RESULT_EXTS = {".docx", ".pdf", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".zip", ".txt"}
RESULT_KIND_BY_EXT = {
    ".docx": "docx", ".pdf": "pdf", ".pptx": "pptx", ".xlsx": "xlsx",
    ".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".zip": "zip", ".txt": "txt",
}

os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)
if not os.path.exists(TEMPLATE_PATH) and os.path.exists(DEFAULT_TEMPLATE_SRC):
    shutil.copy2(DEFAULT_TEMPLATE_SRC, TEMPLATE_PATH)  # seed fallback template on (ephemeral) boot


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def parse_iso(s):
    return datetime.fromisoformat(s) if s else None


@contextmanager
def lock():
    with open(LOCK_PATH, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def job_dir(job_id):
    if not job_id or "/" in job_id or ".." in job_id:
        raise ValueError("bad id")
    return os.path.join(JOBS_DIR, job_id)


def load(job_id):
    p = os.path.join(job_dir(job_id), "job.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(job):
    d = job_dir(job["id"])
    tmp = os.path.join(d, "job.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(d, "job.json"))


DEFAULT_POINTS_PACKAGES = [
    {"id": "p100", "baht": 100, "points": 100, "label": "100 พ้อยท์"},
    {"id": "p200", "baht": 200, "points": 220, "label": "220 พ้อยท์ (โบนัส +20) · คุ้มกว่า"},
]


def default_settings():
    return {
        "price_per_plan": DEFAULT_PRICE_PER_PLAN,
        "payee_name": DEFAULT_PAYEE_NAME,
        "promptpay_id": DEFAULT_PROMPTPAY_ID,
        "qr_image": "promptpay_qr.png" if os.path.isfile(QR_IMAGE_PATH) else None,
        "qr_decoded_id": None,
        "points_topup_enabled": False,
        "points_packages": list(DEFAULT_POINTS_PACKAGES),
        # Owner toggle: 1 free use per Google account + promo top-up popup. DEFAULT OFF.
        "free_trial_mode": False,
    }


def load_settings():
    s = default_settings()
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                s.update({k: data[k] for k in ("price_per_plan", "payee_name", "promptpay_id",
                                               "qr_image", "qr_decoded_id",
                                               "points_topup_enabled", "points_packages",
                                               "free_trial_mode") if k in data})
        except Exception:
            pass
    try:
        s["price_per_plan"] = float(s.get("price_per_plan") or DEFAULT_PRICE_PER_PLAN)
    except (TypeError, ValueError):
        s["price_per_plan"] = DEFAULT_PRICE_PER_PLAN
    s["payee_name"] = (s.get("payee_name") or DEFAULT_PAYEE_NAME).strip() or DEFAULT_PAYEE_NAME
    s["promptpay_id"] = (s.get("promptpay_id") or "").strip()
    s["points_topup_enabled"] = bool(s.get("points_topup_enabled"))
    s["free_trial_mode"] = bool(s.get("free_trial_mode"))
    pkgs = s.get("points_packages")
    if not isinstance(pkgs, list) or not pkgs:
        s["points_packages"] = list(DEFAULT_POINTS_PACKAGES)
    else:
        clean = []
        for p in pkgs:
            if not isinstance(p, dict):
                continue
            try:
                baht = float(p.get("baht") or 0)
                pts = int(p.get("points") or 0)
            except (TypeError, ValueError):
                continue
            if baht <= 0 or pts <= 0:
                continue
            clean.append({
                "id": str(p.get("id") or f"p{int(baht)}"),
                "baht": baht,
                "points": pts,
                "label": str(p.get("label") or f"{pts} พ้อยท์"),
            })
        s["points_packages"] = clean or list(DEFAULT_POINTS_PACKAGES)
    if not os.path.isfile(QR_IMAGE_PATH):
        s["qr_image"] = None
    return s


def save_settings(updates):
    """Merge updates into settings.json under lock. Returns full settings."""
    with lock():
        s = load_settings()
        if "price_per_plan" in updates:
            try:
                s["price_per_plan"] = max(0.0, float(updates["price_per_plan"]))
            except (TypeError, ValueError):
                pass
        if "payee_name" in updates and updates["payee_name"] is not None:
            name = str(updates["payee_name"]).strip()
            if name:
                s["payee_name"] = name
        if "promptpay_id" in updates and updates["promptpay_id"] is not None:
            s["promptpay_id"] = str(updates["promptpay_id"]).strip()
        if "qr_image" in updates:
            s["qr_image"] = updates["qr_image"]
        if "qr_decoded_id" in updates:
            s["qr_decoded_id"] = updates["qr_decoded_id"]
        if "points_topup_enabled" in updates:
            s["points_topup_enabled"] = bool(updates["points_topup_enabled"])
        if "free_trial_mode" in updates:
            s["free_trial_mode"] = bool(updates["free_trial_mode"])
        if "points_packages" in updates and isinstance(updates["points_packages"], list):
            s["points_packages"] = updates["points_packages"]
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
        return s


def set_qr_image(save_fn, original_name=None):
    """save_fn(dest) writes uploaded QR image to QR_IMAGE_PATH. Tries to decode PromptPay ID."""
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = QR_IMAGE_PATH + ".tmp"
    save_fn(tmp)
    os.replace(tmp, QR_IMAGE_PATH)
    decoded_id = None
    payloads = []
    try:
        from promptpay import decode_qr_from_image, extract_promptpay_id_from_payload
        payloads = decode_qr_from_image(QR_IMAGE_PATH)
        for pl in payloads:
            decoded_id = extract_promptpay_id_from_payload(pl)
            if decoded_id:
                break
    except Exception:
        pass
    updates = {"qr_image": "promptpay_qr.png", "qr_decoded_id": decoded_id}
    # If upload decoded an ID and settings ID empty, fill it
    s = load_settings()
    if decoded_id and not s.get("promptpay_id"):
        updates["promptpay_id"] = decoded_id
    return save_settings(updates)


def clear_qr_image():
    if os.path.isfile(QR_IMAGE_PATH):
        try:
            os.remove(QR_IMAGE_PATH)
        except OSError:
            pass
    return save_settings({"qr_image": None, "qr_decoded_id": None})


def qr_image_path_for_display(amount=None):
    """Return (path, source) where source is 'uploaded'|'generated'|None.
    Prefer uploaded image; else generate from promptpay_id if set."""
    if os.path.isfile(QR_IMAGE_PATH):
        return QR_IMAGE_PATH, "uploaded"
    s = load_settings()
    pid = s.get("promptpay_id") or ""
    if not pid:
        return None, None
    try:
        from promptpay import generate_qr_png
        ok = generate_qr_png(pid, QR_GENERATED_PATH, amount=amount)
        if ok and os.path.isfile(QR_GENERATED_PATH):
            return QR_GENERATED_PATH, "generated"
    except Exception:
        pass
    return None, None


def amount_due_for(job, settings=None):
    """Compute amount due. Lesson plans use price_per_plan × plans (+ addons).
    Other services use catalog price × qty (+ optional breakdown already on job)."""
    settings = settings or load_settings()
    # Prefer already-computed payment / breakdown
    if job.get("payment") and job["payment"].get("amount_due") is not None and job.get("_amount_locked"):
        pay = job["payment"]
        return float(pay["amount_due"]), int(pay.get("plan_count_billed") or pay.get("qty") or 1), float(pay.get("price_per_plan") or pay.get("unit_price") or 0)

    sid = job.get("service_id") or "lesson_plan"
    if sid == "lesson_plan":
        n = plan_count_of(job)
        price = float(settings.get("price_per_plan") or DEFAULT_PRICE_PER_PLAN)
        amount = round(price * n, 2)
        for ad in job.get("addons") or []:
            try:
                amount = round(amount + float(ad.get("price") or 0), 2)
            except (TypeError, ValueError):
                pass
        return amount, n, price

    # Generic service: use catalog
    try:
        import catalog
        svc = catalog.get_service(sid) or {}
        amount, qty, price, _ = catalog.compute_amount(svc, job.get("inputs") or {}, job.get("addons"))
        return amount, qty, price
    except Exception:
        n = 1
        price = float(settings.get("price_per_plan") or DEFAULT_PRICE_PER_PLAN)
        return round(price * n, 2), n, price


def _init_payment(job, settings=None):
    settings = settings or load_settings()
    amount, n, price = amount_due_for(job, settings)
    breakdown = job.get("price_breakdown")
    job["payment"] = {
        "amount_due": amount,
        "plan_count_billed": n,  # qty billed (plans or other units)
        "qty": n,
        "price_per_plan": price,  # legacy name = unit price
        "unit_price": price,
        "service_id": job.get("service_id") or "lesson_plan",
        "service_name": job.get("service_name") or "แผนการจัดการเรียนรู้",
        "breakdown": breakdown,
        "payee_name": settings.get("payee_name") or DEFAULT_PAYEE_NAME,
        "promptpay_id": settings.get("promptpay_id") or settings.get("qr_decoded_id") or "",
        "requested_at": now_iso(),
        "slip_file": None,
        "slip_original_name": None,
        "slip_uploaded_at": None,
        "slip_qr_payload": None,
        "slip_ref": None,
        "verified_at": None,
        "verified_by": None,
        "payer_name": None,
        "payee_name_on_slip": None,
        "amount_on_slip": None,
        "transfer_time": None,
        "note": None,
        "reject_reason": None,
        "duplicate_ref_flag": False,
    }
    return job


def begin_payment(job_id):
    """Move a ready job into awaiting_payment and stamp amount due."""
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        if j["status"] in ("awaiting_payment", "payment_review", "payment_rejected",
                           "queued", "processing", "done"):
            # already past choice; ensure payment block exists
            if not j.get("payment"):
                _init_payment(j)
                save(j)
            return j
        if j["status"] != "awaiting_choice":
            _init_payment(j)
            j["status"] = "awaiting_payment"
            save(j)
        return j


def find_slip_ref(slip_ref, exclude_job_id=None):
    """Return job id that already used this slip_ref, or None."""
    if not slip_ref:
        return None
    key = str(slip_ref).strip()
    if not key:
        return None
    for j in all_jobs():
        if exclude_job_id and j["id"] == exclude_job_id:
            continue
        p = j.get("payment") or {}
        if (p.get("slip_ref") or "").strip() == key:
            return j["id"]
    return None


def save_slip(job_id, save_fn, original_name):
    """Teacher uploads transfer slip. Status -> payment_review. Returns job."""
    ext = os.path.splitext(original_name or "")[1].lower()
    if ext not in SLIP_EXTS:
        raise ValueError("slip must be an image or pdf")
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        if j["status"] not in ("awaiting_payment", "payment_rejected", "payment_review"):
            raise ValueError(f"cannot upload slip in status {j['status']}")
        if not j.get("payment"):
            _init_payment(j)
        d = job_dir(job_id)
        stored = "slip" + ext
        dest = os.path.join(d, stored)
        save_fn(dest)
        pay = j["payment"]
        pay["slip_file"] = stored
        pay["slip_original_name"] = original_name
        pay["slip_uploaded_at"] = now_iso()
        pay["reject_reason"] = None
        pay["slip_qr_payload"] = None
        # best-effort decode QR on slip
        try:
            from promptpay import decode_qr_from_image
            payloads = decode_qr_from_image(dest)
            if payloads:
                pay["slip_qr_payload"] = payloads[0]
        except Exception:
            pass
        j["files"]["slip"] = stored
        j["status"] = "payment_review"
        save(j)
        return j


def approve_payment(job_id, *, slip_ref=None, amount=None, transfer_time=None,
                    payer_name=None, payee_name=None, note=None, by="worker"):
    """Verify payment and put job in the work queue. Raises ValueError on duplicate ref."""
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        if j["status"] not in ("payment_review", "payment_rejected", "awaiting_payment"):
            if j["status"] == "queued":
                return j
            raise ValueError(f"cannot approve payment in status {j['status']}")
        if not j.get("payment"):
            _init_payment(j)
        pay = j["payment"]
        ref = (slip_ref if slip_ref is not None else pay.get("slip_ref") or "").strip() or None
        if ref:
            dup = None
            for other in all_jobs():
                if other["id"] == job_id:
                    continue
                op = other.get("payment") or {}
                if (op.get("slip_ref") or "").strip() == ref:
                    dup = other["id"]
                    break
            if dup:
                pay["duplicate_ref_flag"] = True
                save(j)
                raise ValueError(f"duplicate slip_ref already used by job {dup}")
            pay["slip_ref"] = ref
        if amount is not None and amount != "":
            try:
                pay["amount_on_slip"] = float(amount)
            except (TypeError, ValueError):
                pay["amount_on_slip"] = amount
        if transfer_time is not None:
            pay["transfer_time"] = transfer_time
        if payer_name is not None:
            pay["payer_name"] = payer_name
        if payee_name is not None:
            pay["payee_name_on_slip"] = payee_name
        if note is not None:
            pay["note"] = note
        pay["verified_at"] = now_iso()
        pay["verified_by"] = by
        pay["reject_reason"] = None
        pay["duplicate_ref_flag"] = False
        # Points top-up: credit and mark done (no worker queue)
        if j.get("service_id") == "points_topup" or j.get("fulfil") == "topup":
            pts = int((j.get("inputs") or {}).get("points") or pay.get("points_credit") or 0)
            uid = j.get("user_id")
            if uid and pts > 0 and not j.get("points_credited"):
                try:
                    import users
                    users.adjust_points(
                        uid, pts,
                        reason=f"เติมพ้อยท์แพ็ก {pay.get('amount_due') or ''}฿",
                        job_id=j["id"], admin=by, typ="topup",
                    )
                    j["points_credited"] = pts
                except Exception as e:
                    # keep job in review if credit fails
                    pay["note"] = (pay.get("note") or "") + f" | credit failed: {e}"
                    save(j)
                    raise ValueError(f"เติมพ้อยท์ไม่สำเร็จ: {e}")
            j["status"] = "done"
            j["queued_at"] = j.get("queued_at") or now_iso()
            j["started_at"] = j.get("started_at") or now_iso()
            j["finished_at"] = now_iso()
            save(j)
            j["_run_auto"] = False
            return j
        j["status"] = "queued"
        j["queued_at"] = now_iso()
        save(j)
        # Auto services fulfil immediately after payment (outside this lock via flag)
        j["_run_auto"] = (j.get("fulfil") == "auto")
        return j


def reject_payment(job_id, reason, by="worker"):
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        if j["status"] not in ("payment_review", "awaiting_payment", "queued"):
            # allow reject from payment_review primarily; also undo queued if needed
            if j["status"] == "payment_rejected":
                return j
            raise ValueError(f"cannot reject payment in status {j['status']}")
        if not j.get("payment"):
            _init_payment(j)
        pay = j["payment"]
        pay["reject_reason"] = (reason or "").strip() or "สลิปไม่ถูกต้อง"
        pay["verified_at"] = now_iso()
        pay["verified_by"] = by
        # keep slip file so teacher can see what was rejected; they may re-upload
        j["status"] = "payment_rejected"
        save(j)
        return j


def payment_jobs(status=None):
    """Jobs that are in a payment-related state (or any with a payment block if status set)."""
    out = []
    for j in all_jobs():
        st = j["status"]
        if status:
            if st == status:
                out.append(j)
        elif st in PAYMENT_STATUSES or (j.get("payment") and st in ("queued", "processing", "done")):
            out.append(j)
    return out


def payment_totals():
    """Simple totals: paid today / all time (jobs approved into the work queue)."""
    today = datetime.now(TZ).date().isoformat()
    paid_all = paid_today = 0.0
    count_all = count_today = 0
    for j in all_jobs():
        pay = j.get("payment") or {}
        if not pay.get("verified_at"):
            continue
        # Count only when payment was approved (job left payment_* for the work pipeline)
        if j["status"] in ("awaiting_payment", "payment_review", "payment_rejected"):
            continue
        try:
            amt = float(pay.get("amount_due") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        paid_all += amt
        count_all += 1
        try:
            vd = parse_iso(pay["verified_at"]).date().isoformat()
        except Exception:
            vd = (pay["verified_at"] or "")[:10]
        if vd == today:
            paid_today += amt
            count_today += 1
    return {
        "paid_today": round(paid_today, 2),
        "paid_all_time": round(paid_all, 2),
        "count_today": count_today,
        "count_all_time": count_all,
    }


def all_jobs():
    out = []
    for name in os.listdir(JOBS_DIR):
        j = load(name) if os.path.isdir(os.path.join(JOBS_DIR, name)) else None
        if j:
            out.append(j)
    out.sort(key=lambda j: (j["created_at"], j["id"]))
    return out


def new_job_id():
    return datetime.now(TZ).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def plan_count_of(job):
    """Effective number of plans to produce, used for ETA (old jobs lack it -> 1)."""
    try:
        v = job.get("effective_plan_count")
        if v is None:
            v = 1 if job.get("plan_mode") == "one" else job.get("plan_count")
        return max(1, int(v or 1))
    except (TypeError, ValueError):
        return 1


def instructions_of(job):
    return job.get("instructions") or job.get("note") or ""


def eta_factor(job):
    """1.5 when the job has no data file or asks for extra illustrations (not stacked), else 1."""
    if job.get("from_scratch") or OPT_ILLUSTRATIONS in (job.get("options") or []):
        return SLOW_FACTOR
    return 1.0



def create_service_job(service, inputs, uploads, *, file_count=1, user_id=None, points_spent=0):
    """Create a job for a catalog service (not lesson_plan special form).
    uploads: {field_id: (filename, save_fn)} or {field_id: [(filename, save_fn), ...]} for multi.
    inputs: dict of text/number/select values (no files).
    """
    import catalog
    job_id = new_job_id()
    d = job_dir(job_id)
    os.makedirs(d)
    files = {
        "source": None, "source_original_name": None,
        "template": None, "template_original_name": None,
        "template_is_default": False,
        "result_docx": None, "result_pdf": None, "slip": None,
        "uploads": [],
    }
    # Persist uploads
    for field_id, val in (uploads or {}).items():
        items = val if isinstance(val, list) else [val]
        for idx, item in enumerate(items):
            if not item:
                continue
            fname, save_fn = item
            ext = os.path.splitext(fname)[1].lower()
            if len(items) > 1:
                stored = f"{field_id}_{idx}{ext}"
            else:
                stored = f"{field_id}{ext}"
            save_fn(os.path.join(d, stored))
            files["uploads"].append({
                "field": field_id, "stored": stored,
                "original_name": fname, "index": idx,
            })
            # Convenience mirrors for first source/template
            if field_id in ("source", "template") and not files.get(field_id):
                files[field_id] = stored
                files[field_id + "_original_name"] = fname
            elif field_id not in ("source", "template") and not files.get("source"):
                # first non-template file also exposed as source for workers
                files["source"] = stored
                files["source_original_name"] = fname

    inputs = dict(inputs or {})
    inputs["_file_count"] = int(file_count or 1)
    amount, qty, price, breakdown = catalog.compute_amount(service, inputs)
    collect = bool(service.get("collect_payment"))

    job = {
        "id": job_id,
        "service_id": service["id"],
        "service_name": service["name"],
        "user_id": user_id,
        "points_spent": int(points_spent or 0),
        "fulfil": service.get("fulfil") or "worker",
        "collect_payment": collect,
        "status": "queued" if not collect else "awaiting_payment",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "queued_at": now_iso() if not collect else None,
        "fields": {},  # lesson-plan compatibility
        "inputs": inputs,
        "note": inputs.get("instructions") or "",
        "instructions": inputs.get("instructions") or "",
        "options": [],
        "addons": [],
        "from_scratch": not bool(files.get("source") or files.get("uploads")),
        "files": files,
        "results": [],
        "plan_count": 1,
        "plan_numbers": [],
        "plan_mode": "all",
        "plan_selected": None,
        "effective_plan_count": 1,
        "price_breakdown": breakdown,
        "error": None,
        "payment": None,
    }
    if collect:
        _init_payment(job)
        job["payment"]["plan_count_billed"] = qty
        job["payment"]["qty"] = qty
        job["payment"]["unit_price"] = price
        job["payment"]["price_per_plan"] = price
    else:
        # Keep amount as catalog data for later; do not start PromptPay flow
        job["catalog_amount"] = amount
        job["catalog_qty"] = qty
        job["catalog_unit_price"] = price
    with lock():
        save(job)
    return job


def try_auto_fulfil(job_id):
    """If job is auto-fulfil and queued, run immediately and mark done. Returns job."""
    j = load(job_id)
    if not j:
        raise KeyError(job_id)
    if j.get("fulfil") != "auto":
        return j
    if j["status"] not in ("queued", "processing"):
        return j
    # mark processing
    with lock():
        j = load(job_id)
        if j["status"] == "queued":
            j["status"] = "processing"
            j["started_at"] = now_iso()
            save(j)
    try:
        import autofulfil
        results = autofulfil.run_auto(j, job_dir(job_id))
        extras = []
        for stored, kind in results:
            extras.append((os.path.join(job_dir(job_id), stored), stored, kind, stored))
        # complete without requiring docx — pass via extra_files only
        # Avoid double-copy: files already in place; register via a no-op copy path
        with lock():
            j = load(job_id)
            for stored, kind in results:
                _register_result(j, stored, kind, stored)
            j["status"] = "done"
            j["started_at"] = j["started_at"] or j["created_at"]
            j["finished_at"] = now_iso()
            j["error"] = None
            save(j)
            return j
    except Exception as e:
        return fail(job_id, f"ทำอัตโนมัติไม่สำเร็จ: {e}")


def create_job(uploads, fields, note, plan_counter=None, instructions=None, options=None, addons=None, user_id=None):
    """uploads: {"template": (filename, save_fn), "source": (filename, save_fn)}.
    save_fn(dest_path) writes the uploaded file. If no template upload is given,
    the admin default template (data/template/main.docx) is copied as a fallback.
    addons: optional list of {id,name,price,unit} upsells (slides/worksheet/test)."""
    job_id = new_job_id()
    d = job_dir(job_id)
    os.makedirs(d)
    files = {"source": None, "source_original_name": None,
             "template": None, "template_original_name": None,
             "template_is_default": False,
             "result_docx": None, "result_pdf": None, "slip": None}
    for kind in ("template", "source"):
        if kind in uploads and uploads[kind]:
            fname, save_fn = uploads[kind]
            stored = kind + os.path.splitext(fname)[1].lower()
            save_fn(os.path.join(d, stored))
            files[kind] = stored
            files[kind + "_original_name"] = fname
    if not files["template"] and os.path.exists(TEMPLATE_PATH):
        shutil.copy2(TEMPLATE_PATH, os.path.join(d, "template.docx"))
        files["template"] = "template.docx"
        files["template_original_name"] = "main.docx (ค่าเริ่มต้นของระบบ)"
        files["template_is_default"] = True
    # Resolve addon definitions from catalog (price snapshot at order time)
    addon_list = []
    if addons:
        try:
            import catalog
            svc = catalog.get_service("lesson_plan") or {}
            allowed = {a["id"]: a for a in (svc.get("addons") or [])}
            for a in addons:
                aid = a if isinstance(a, str) else (a.get("id") if isinstance(a, dict) else None)
                if aid and aid in allowed:
                    src = allowed[aid]
                    addon_list.append({
                        "id": src["id"], "name": src["name"],
                        "price": float(src["price"]), "unit": src.get("unit") or "per_set",
                    })
        except Exception:
            pass

    job = {
        "id": job_id,
        "service_id": "lesson_plan",
        "service_name": "แผนการจัดการเรียนรู้",
        "user_id": user_id,
        "points_spent": 0,
        "fulfil": "worker",
        "collect_payment": True,
        "status": "queued",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "fields": fields,
        "inputs": dict(fields or {}),
        "note": note,               # legacy name, same text as instructions
        "instructions": instructions if instructions is not None else note,
        "options": list(options or []),
        "addons": addon_list,
        "from_scratch": not files["source"],
        "files": files,
        "results": [],              # [{name, kind, original_name}]
        "plan_count": 1,          # plans detected in the source file
        "plan_numbers": [],       # detected plan numbers
        "plan_mode": "all",       # 'all' | 'one'
        "plan_selected": None,    # plan number when plan_mode == 'one'
        "effective_plan_count": 1,  # plans actually produced (ETA)
        "error": None,
    }
    if plan_counter and files["source"]:
        try:
            cnt, nums = plan_counter(os.path.join(d, files["source"]))
            job["plan_count"], job["plan_numbers"] = max(1, int(cnt)), list(nums)
        except Exception:
            job["plan_count"], job["plan_numbers"] = 1, []
    job["effective_plan_count"] = job["plan_count"]
    job["payment"] = None
    try:
        import catalog
        svc = catalog.get_service("lesson_plan") or {"id": "lesson_plan", "name": "แผนการจัดการเรียนรู้", "unit": "per_plan", "price": DEFAULT_PRICE_PER_PLAN}
        # price comes from settings for lesson_plan
        s = load_settings()
        svc = dict(svc)
        svc["price"] = float(s.get("price_per_plan") or DEFAULT_PRICE_PER_PLAN)
        amount, qty, price, breakdown = catalog.compute_amount(
            svc, {"effective_plan_count": job["effective_plan_count"]}, job["addons"])
        job["price_breakdown"] = breakdown
    except Exception:
        job["price_breakdown"] = None
    if job["plan_count"] > 1:
        job["status"] = "awaiting_choice"  # submitter must choose one plan vs all before paying
    else:
        # single plan: go straight to payment (not the work queue)
        _init_payment(job)
        job["status"] = "awaiting_payment"
    with lock():
        save(job)
    return job


def set_plan_choice(job_id, mode, selected=None):
    """Record the submitter's choice and put the job in the queue."""
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        if j["status"] != "awaiting_choice":
            return j
        if mode == "one":
            j["plan_mode"], j["plan_selected"], j["effective_plan_count"] = "one", selected, 1
        else:
            j["plan_mode"], j["plan_selected"] = "all", None
            j["effective_plan_count"] = max(1, int(j.get("plan_count") or 1))
        try:
            import catalog
            svc = catalog.get_service("lesson_plan") or {"id": "lesson_plan", "name": "แผนการจัดการเรียนรู้", "unit": "per_plan", "price": DEFAULT_PRICE_PER_PLAN}
            svc = dict(svc)
            s = load_settings()
            svc["price"] = float(s.get("price_per_plan") or DEFAULT_PRICE_PER_PLAN)
            _, _, _, breakdown = catalog.compute_amount(
                svc, {"effective_plan_count": j["effective_plan_count"]}, j.get("addons"))
            j["price_breakdown"] = breakdown
        except Exception:
            pass
        _init_payment(j)
        j["status"] = "awaiting_payment"
        save(j)
        return j


def mark_job_points_paid(job_id, points_spent=0):
    """Skip PromptPay: mark a lesson-plan (or paid) job as points-settled and queued."""
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        j["points_spent"] = int(points_spent or 0)
        j["collect_payment"] = False
        j["payment"] = None
        if j.get("status") in ("awaiting_payment", "payment_rejected", "payment_review", "awaiting_choice"):
            j["status"] = "queued"
        elif j.get("status") not in ("queued", "processing", "done", "error", "cancelled"):
            j["status"] = "queued"
        save(j)
        return j


def with_paths(job):
    d = job_dir(job["id"])
    j = dict(job)
    j["paths"] = {k: (os.path.join(d, v) if v else None)
                  for k, v in job["files"].items()
                  if k in ("source", "template", "result_docx", "result_pdf", "slip")
                  or (isinstance(k, str) and k.startswith("result_"))}
    j["paths"]["job_dir"] = d
    # multi uploads
    uploads = []
    for u in (job.get("files") or {}).get("uploads") or []:
        uploads.append({**u, "path": os.path.join(d, u["stored"])})
    j["paths"]["uploads"] = uploads
    results = []
    for r in job.get("results") or []:
        results.append({**r, "path": os.path.join(d, r["name"])})
    j["paths"]["results"] = results
    j["service_id"] = job.get("service_id") or "lesson_plan"
    j["service_name"] = job.get("service_name") or "แผนการจัดการเรียนรู้"
    return j


def claim_next(service_id=None):
    """Claim oldest queued worker job. Skips auto-fulfil jobs (they self-complete).
    Optional service_id filter."""
    with lock():
        for j in all_jobs():
            if j["status"] != "queued":
                continue
            if j.get("fulfil") == "auto":
                continue
            if service_id and (j.get("service_id") or "lesson_plan") != service_id:
                continue
            j["status"] = "processing"
            j["started_at"] = now_iso()
            save(j)
            return j
    return None


def claim(job_id):
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        if j["status"] != "queued":
            raise ValueError(f"job {job_id} is {j['status']}, not queued (unpaid jobs cannot be claimed)")
        j["status"] = "processing"
        j["started_at"] = j["started_at"] or now_iso()
        save(j)
        return j


def _register_result(j, stored_name, kind=None, original_name=None):
    """Append/update a result file entry on the job."""
    ext = os.path.splitext(stored_name)[1].lower()
    kind = kind or RESULT_KIND_BY_EXT.get(ext) or ext.lstrip(".")
    results = list(j.get("results") or [])
    results = [r for r in results if r.get("name") != stored_name]
    results.append({"name": stored_name, "kind": kind, "original_name": original_name or stored_name})
    j["results"] = results
    # legacy mirrors
    if kind == "docx":
        j["files"]["result_docx"] = stored_name
    elif kind == "pdf":
        j["files"]["result_pdf"] = stored_name
    else:
        j["files"][f"result_{kind}"] = stored_name
    return j


def complete(job_id, docx_src=None, pdf_src=None, docx_writer=None, pdf_writer=None,
             extra_files=None):
    """Mark job done. Lesson-plan jobs still require a .docx; other services accept any result.
    extra_files: list of (src_path | writer_fn, stored_name, kind?, original_name?)."""
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        d = job_dir(job_id)
        if docx_src or docx_writer:
            dest = os.path.join(d, "result.docx")
            docx_writer(dest) if docx_writer else shutil.copy2(docx_src, dest)
            _register_result(j, "result.docx", "docx")
        if pdf_src or pdf_writer:
            dest = os.path.join(d, "result.pdf")
            pdf_writer(dest) if pdf_writer else shutil.copy2(pdf_src, dest)
            _register_result(j, "result.pdf", "pdf")
        for item in extra_files or []:
            if len(item) == 2:
                src, stored = item
                kind = original = None
            elif len(item) == 3:
                src, stored, kind = item
                original = None
            else:
                src, stored, kind, original = item[:4]
            dest = os.path.join(d, stored)
            if callable(src):
                src(dest)
            else:
                shutil.copy2(src, dest)
            _register_result(j, stored, kind, original)
        sid = j.get("service_id") or "lesson_plan"
        has_any = bool(j.get("results")) or bool(j["files"].get("result_docx")) or bool(j["files"].get("result_pdf"))
        if sid == "lesson_plan" and not j["files"].get("result_docx"):
            raise ValueError("result docx required")
        if not has_any:
            raise ValueError("at least one result file required")
        j["status"] = "done"
        j["started_at"] = j["started_at"] or j["created_at"]
        j["finished_at"] = now_iso()
        j["error"] = None
        save(j)
        return j


def fail(job_id, message):
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        j["status"] = "failed"
        j["finished_at"] = now_iso()
        j["error"] = message
        save(j)
        return j


def requeue(job_id):
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        j["status"] = "queued"
        j["started_at"] = None
        save(j)
        return j


def avg_minutes_per_plan(jobs=None):
    """Average minutes per lesson plan over the last 20 completed jobs (>=1 min each)."""
    jobs = jobs if jobs is not None else all_jobs()
    per_plan = []
    for j in jobs:
        if j["status"] == "done" and j.get("started_at") and j.get("finished_at"):
            m = (parse_iso(j["finished_at"]) - parse_iso(j["started_at"])).total_seconds() / 60
            if m >= 1.0:  # ignore near-instant test completions (<1 min)
                per_plan.append(m / (plan_count_of(j) * eta_factor(j)))
    per_plan = per_plan[-20:]
    return sum(per_plan) / len(per_plan) if per_plan else DEFAULT_MINUTES


avg_minutes = avg_minutes_per_plan  # backwards-compatible name


def remaining_minutes(job, avg, now=None):
    """Estimated minutes left for one job: plan_count x avg (minus elapsed if processing), min 1."""
    total = plan_count_of(job) * avg * eta_factor(job)
    if job["status"] == "processing" and job.get("started_at"):
        elapsed = ((now or datetime.now(TZ)) - parse_iso(job["started_at"])).total_seconds() / 60
        total -= elapsed
    return max(1.0, total)


def status_info(job_id):
    jobs = all_jobs()
    j = next((x for x in jobs if x["id"] == job_id), None)
    if not j:
        return None
    avg = avg_minutes_per_plan(jobs)
    now = datetime.now(TZ)
    pc = plan_count_of(j)
    pay = j.get("payment") or {}
    results = j.get("results") or []
    info = {"id": j["id"],
            "service_id": j.get("service_id") or "lesson_plan",
            "service_name": j.get("service_name") or "แผนการจัดการเรียนรู้",
            "fulfil": j.get("fulfil") or "worker",
            "inputs": j.get("inputs") or {},
            "addons": j.get("addons") or [],
            "results": results,
            "status": j["status"], "created_at": j["created_at"],
            "started_at": j["started_at"], "finished_at": j["finished_at"],
            "error": j["error"], "avg_minutes_per_plan": round(avg, 1),
            "avg_minutes": round(avg, 1),  # kept for older clients (now per plan)
            "plan_count": pc,  # effective plans used for ETA
            "detected_plan_count": max(1, int(j.get("plan_count") or 1)),
            "plan_numbers": j.get("plan_numbers") or [],
            "plan_mode": j.get("plan_mode") or "all", "plan_selected": j.get("plan_selected"),
            "eta_factor": eta_factor(j), "from_scratch": bool(j.get("from_scratch")),
            "instructions": instructions_of(j), "options": j.get("options") or [],
            "job_minutes": round(pc * avg * eta_factor(j), 1),
            "has_docx": bool(j["files"].get("result_docx")),
            "has_pdf": bool(j["files"].get("result_pdf")),
            "has_results": bool(results) or bool(j["files"].get("result_docx")) or bool(j["files"].get("result_pdf")),
            "result_kinds": sorted({r.get("kind") for r in results if r.get("kind")}
                                   | ({"docx"} if j["files"].get("result_docx") else set())
                                   | ({"pdf"} if j["files"].get("result_pdf") else set())),
            "has_slip": bool((j.get("files") or {}).get("slip") or pay.get("slip_file")),
            "payment": {
                "amount_due": pay.get("amount_due"),
                "plan_count_billed": pay.get("plan_count_billed"),
                "price_per_plan": pay.get("price_per_plan"),
                "payee_name": pay.get("payee_name"),
                "requested_at": pay.get("requested_at"),
                "slip_uploaded_at": pay.get("slip_uploaded_at"),
                "reject_reason": pay.get("reject_reason"),
                "verified_at": pay.get("verified_at"),
                "slip_ref": pay.get("slip_ref"),
            } if pay else None,
            "queue_position": None, "jobs_ahead": None, "plans_ahead": None,
            "eta_minutes": None}
    processing = [x for x in jobs if x["status"] == "processing"]
    if j["status"] == "queued":
        queued = [x for x in jobs if x["status"] == "queued"]
        idx = [x["id"] for x in queued].index(j["id"])
        ahead = processing + queued[:idx]
        info["queue_position"] = idx + 1
        info["jobs_ahead"] = len(ahead)
        info["plans_ahead"] = sum(plan_count_of(x) for x in ahead)
        mins = sum(remaining_minutes(x, avg, now) for x in ahead) + remaining_minutes(j, avg, now)
        info["eta_minutes"] = max(1, round(mins))
    elif j["status"] == "processing":
        info["queue_position"] = 0
        info["jobs_ahead"] = 0
        info["plans_ahead"] = 0
        info["eta_minutes"] = max(1, round(remaining_minutes(j, avg, now)))
    return info


BOARD_FILTERS = ("all", "review", "approved", "rejected")


def _board_state(j):
    st = j["status"]
    if st == "payment_rejected":
        return "rejected"
    if st == "payment_review":
        return "review"
    if st == "awaiting_payment":
        return "awaiting"
    if (j.get("payment") or {}).get("verified_at"):
        return "approved"
    return "other"


def topup_board(filt="all", page=1, per_page=24):
    """Stats + slip gallery for the admin top-up board (Asia/Bangkok dates)."""
    now = datetime.now(TZ)
    today = now.date()
    week_start = today - timedelta(days=6)
    stats = {k: {"amount": 0.0, "count": 0} for k in ("today", "week", "month", "all")}
    review = rejected = 0
    slips = []
    for j in all_jobs():
        pay = j.get("payment") or {}
        state = _board_state(j)
        if state == "review":
            review += 1
        elif state == "rejected":
            rejected += 1
        elif state == "approved":
            try:
                amt = float(pay.get("amount_due") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            try:
                vd = parse_iso(pay["verified_at"]).astimezone(TZ).date()
            except Exception:
                vd = None
            buckets = ["all"]
            if vd:
                if vd == today:
                    buckets.append("today")
                if week_start <= vd <= today:
                    buckets.append("week")
                if (vd.year, vd.month) == (today.year, today.month):
                    buckets.append("month")
            for b in buckets:
                stats[b]["amount"] += amt
                stats[b]["count"] += 1
        slip = pay.get("slip_file") or (j.get("files") or {}).get("slip")
        if slip and os.path.isfile(os.path.join(job_dir(j["id"]), slip)):
            up = pay.get("slip_uploaded_at") or j.get("created_at") or ""
            try:
                up_disp = parse_iso(up).astimezone(TZ).strftime("%d/%m/%Y %H:%M")
            except Exception:
                up_disp = up[:16].replace("T", " ")
            slips.append({"job": j, "pay": pay, "state": state,
                          "uploaded_at": up, "uploaded_disp": up_disp,
                          "is_pdf": slip.lower().endswith(".pdf"),
                          "service_id": j.get("service_id") or "lesson_plan",
                          "service_name": j.get("service_name") or "แผนการจัดการเรียนรู้"})
    for v in stats.values():
        v["amount"] = round(v["amount"], 2)
    slips.sort(key=lambda s: s["uploaded_at"], reverse=True)
    if filt not in BOARD_FILTERS:
        filt = "all"
    if filt != "all":
        slips = [s for s in slips if s["state"] == filt]
    total = len(slips)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    return {"stats": stats, "review": review, "rejected": rejected,
            "slips": slips[(page - 1) * per_page: page * per_page],
            "filter": filt, "page": page, "pages": pages, "total": total}

def create_topup_job(user_id, package):
    """Create a points top-up payment job (PromptPay slip → credit on approve)."""
    job_id = new_job_id()
    d = job_dir(job_id)
    os.makedirs(d)
    baht = float(package["baht"])
    pts = int(package["points"])
    job = {
        "id": job_id,
        "service_id": "points_topup",
        "service_name": "เติมพ้อยท์",
        "user_id": user_id,
        "points_spent": 0,
        "fulfil": "topup",
        "collect_payment": True,
        "status": "awaiting_payment",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "queued_at": None,
        "fields": {},
        "inputs": {
            "package_id": package.get("id"),
            "points": pts,
            "baht": baht,
            "label": package.get("label") or f"{pts} พ้อยท์",
        },
        "note": f"เติมพ้อยท์ {pts} จาก {baht} บาท",
        "instructions": "",
        "options": [],
        "addons": [],
        "from_scratch": True,
        "files": {"source": None, "template": None, "result_docx": None, "result_pdf": None,
                  "slip": None, "uploads": [], "template_is_default": False,
                  "source_original_name": None, "template_original_name": None},
        "results": [],
        "plan_count": 1,
        "plan_numbers": [],
        "plan_mode": "all",
        "plan_selected": None,
        "effective_plan_count": 1,
        "error": None,
        "payment": None,
        "points_credited": 0,
    }
    _init_payment(job)
    job["payment"]["amount_due"] = baht
    job["payment"]["plan_count_billed"] = 1
    job["payment"]["qty"] = 1
    job["payment"]["unit_price"] = baht
    job["payment"]["price_per_plan"] = baht
    job["payment"]["points_credit"] = pts
    job["_amount_locked"] = True
    with lock():
        save(job)
    return job


def jobs_for_user(user_id, limit=100):
    if not user_id:
        return []
    out = [j for j in all_jobs() if j.get("user_id") == user_id]
    out.sort(key=lambda j: j.get("created_at") or "", reverse=True)
    return out[:limit]
