import hmac, json, logging, os, shutil, threading, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
try:  # local development only; on Render, env vars come from the dashboard
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE, ".env"))
except ImportError:
    pass

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for, flash, g)
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
import store
import catalog
import users
import brand
from plancount import detect_plans

ALLOWED = {".doc", ".docx", ".pdf"}
ALLOWED_SERVICE = {".doc", ".docx", ".pdf", ".pptx", ".xlsx", ".xls", ".csv",
                   ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".txt", ".zip"}
MAX_MB = 20
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
GOOGLE_CLIENT_ID = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
GOOGLE_CLIENT_SECRET = (os.environ.get("GOOGLE_CLIENT_SECRET") or "").strip()
GOOGLE_OAUTH_READY = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
LP_TEST_LOGIN = os.environ.get("LP_TEST_LOGIN", "").strip() == "1"

log = logging.getLogger("lp-web")
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Render/Cloudflare HTTPS proxy
_secret = os.environ.get("SECRET_KEY", "")
if len(_secret) < 16:
    log.warning("SECRET_KEY missing/short: using a random key (admin sessions reset on restart)")
    _secret = os.urandom(32)
app.secret_key = _secret
app.config["MAX_CONTENT_LENGTH"] = (10 * MAX_MB + 2) * 1024 * 1024  # multi-file service uploads
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("LP_COOKIE_SECURE", "1") not in ("0", "false", "False")

# Google OAuth (Authlib) — optional; site still works without credentials
_oauth = None
if GOOGLE_OAUTH_READY:
    try:
        from authlib.integrations.flask_client import OAuth
        _oauth = OAuth(app)
        _oauth.register(
            name="google",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        log.info("Google OAuth enabled")
    except Exception as e:
        log.warning("Google OAuth setup failed: %s", e)
        _oauth = None
        GOOGLE_OAUTH_READY = False
else:
    log.warning("GOOGLE_CLIENT_ID/SECRET missing: Google login disabled (friendly UI message)")

if len(ADMIN_PASSWORD) < 8:
    log.warning("ADMIN_PASSWORD missing/short (<8): /admin login is DISABLED")
    ADMIN_PASSWORD = ""
if len(WORKER_TOKEN) < 16:
    log.warning("WORKER_TOKEN missing/short (<16): worker API is DISABLED (401)")
    WORKER_TOKEN = ""

FIELDS = [
    ("teacher", "ชื่อผู้สอน", "text"),
    ("plan_no", "แผนการจัดการเรียนรู้ที่", "number"),
    ("unit_no", "หน่วยการเรียนรู้ที่", "text"),
    ("semester", "ภาคเรียน", "text"),
    ("year", "ปีการศึกษา", "text"),
]
THAI_MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
LABELS = {"teacher": "ชื่อผู้สอน", "teach_day": "สอนวันที่ (วัน)", "teach_month": "สอนวันที่ (เดือน)",
          "teach_year": "สอนวันที่ (ปี พ.ศ.)", "plan_no": "แผนการจัดการเรียนรู้ที่",
          "unit_no": "หน่วยการเรียนรู้ที่", "semester": "ภาคเรียน", "year": "ปีการศึกษา"}
FIELD_KEYS = ["teacher", "teach_day", "teach_month", "teach_year", "plan_no", "unit_no", "semester", "year"]
UPLOADS = [("template", "ไฟล์ที่ 1: ฟอร์มแผนการสอนของโรงเรียน (template)"),
           ("source", "ไฟล์ที่ 2: ไฟล์ข้อมูล (เช่น แผนจาก พว. หรือแหล่งอื่น ๆ)")]
REQUIRED_UPLOADS = {"template"}
OPTIONS = store.OPTIONS  # quick-option checkboxes (Thai labels, stored as-is in job['options'])
MIN_INSTRUCTIONS = 10    # without a data file, instructions must describe subject/grade/topic
STATUS_TH = {
    "awaiting_choice": "รอเลือกแผน",
    "awaiting_payment": "รอชำระเงิน",
    "payment_review": "รอตรวจสลิป",
    "payment_rejected": "สลิปไม่ผ่าน",
    "queued": "รอคิว",
    "processing": "กำลังทำ",
    "done": "เสร็จแล้ว",
    "failed": "ผิดพลาด",
}
SLIP_MAX_MB = 10
QR_UPLOAD_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}



def current_user():
    """Logged-in teacher from session, or None."""
    uid = session.get("user_id")
    if not uid:
        return None
    if getattr(g, "_user_cached", None) and g._user_cached.get("id") == uid:
        return g._user_cached
    u = users.load_user(uid)
    g._user_cached = u
    return u


def _safe_next(raw):
    """Allow only same-site relative paths (no protocol-relative //)."""
    if not raw:
        return None
    raw = str(raw).strip()
    if raw.startswith("/") and not raw.startswith("//"):
        # drop trailing ? from Flask full_path
        if raw.endswith("?"):
            raw = raw[:-1]
        return raw or "/"
    return None


def _return_path_after_login():
    """Where to send the teacher after Google login (never a POST-only submit URL)."""
    nxt = _safe_next(request.values.get("next")) or _safe_next(request.referrer and request.referrer.replace(request.url_root.rstrip("/"), "") if request.referrer else None)
    if nxt:
        return nxt
    path = request.path or "/"
    if path == "/submit":
        return "/plan"
    if path.endswith("/submit"):
        return path[: -len("/submit")] or "/"
    if request.method == "POST":
        ref = request.referrer or ""
        # prefer referer path if same host
        try:
            from urllib.parse import urlparse
            p = urlparse(ref)
            if p.path and (not p.netloc or p.netloc == request.host):
                return p.path
        except Exception:
            pass
    return path if request.method == "GET" else "/"


def login_required(view):
    """Require Google (or test) login for mutating / private teacher actions."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user():
            return view(*args, **kwargs)
        nxt = _return_path_after_login()
        session["after_login"] = nxt
        flash("กรุณาเข้าสู่ระบบด้วย Google ก่อนใช้งาน")
        return redirect(url_for("login", next=nxt))
    return wrapped


def _public_url(path="/"):
    """Absolute URL honouring HTTPS behind Render ProxyFix."""
    return request.url_root.rstrip("/") + path


@app.context_processor
def inject_globals():
    u = current_user()
    return {
        "current_user": u,
        "google_oauth_ready": bool(_oauth),
        "points_topup_enabled": bool(store.load_settings().get("points_topup_enabled")),
        "brand": brand,
        "site_name": brand.SITE_NAME,
        "site_url": brand.SITE_URL,
    }


def fire_webhook(job_id):

    if not WEBHOOK_URL:
        return
    def run():
        try:
            req = urllib.request.Request(WEBHOOK_URL, data=json.dumps({"job_id": job_id}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:
            app.logger.warning("webhook failed: %s", e)
    threading.Thread(target=run, daemon=True).start()


@app.errorhandler(413)
def too_large(e):
    flash(f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_MB} MB ต่อไฟล์)")
    ref = (request.referrer or "")
    if "/plan" in ref or "/submit" in (request.path or ""):
        return redirect(url_for("plan_form"))
    return redirect(request.referrer or url_for("index"))


@app.get("/")
def index():
    groups = catalog.services_by_group(include_disabled=False, home=True)
    meta = brand.page_meta(
        title="ครูดี — ทำแผนการสอน สื่อการสอน ใบงาน ข้อสอบ สำหรับครู",
        description=brand.SITE_DESC,
        path="/",
    )
    return render_template("home.html", groups=groups, group_icons=catalog.GROUP_ICONS,
                           group_svg=brand.GROUP_SVG, unit_label=catalog.unit_label, meta=meta)


@app.get("/plan")
def plan_form():
    """Legacy lesson-plan order form (unchanged flow)."""
    from datetime import datetime
    be = datetime.now(store.TZ).year + 543
    svc = catalog.get_service("lesson_plan") or {}
    meta = brand.page_meta(
        title="ทำแผนการจัดการเรียนรู้ / แผนการสอนออนไลน์",
        description="อัปโหลดฟอร์มโรงเรียน แล้วให้ครูดีจัดทำแผนการจัดการเรียนรู้ Word ให้ — รองรับสื่อ ใบงาน ข้อสอบพร้อมเฉลย",
        path="/plan",
    )
    return render_template("index.html", fields=FIELDS, max_mb=MAX_MB, uploads=UPLOADS,
                           required_uploads=REQUIRED_UPLOADS, options=OPTIONS, min_instr=MIN_INSTRUCTIONS,
                           months=THAI_MONTHS, years=list(range(be - 1, be + 3)), this_year=be,
                           addons=svc.get("addons") or [], service=svc, meta=meta)


@app.post("/submit")
@login_required
def submit():
    ups = {}
    instructions = (request.form.get("instructions") or request.form.get("note") or "").strip()
    options = [o for o in OPTIONS if o in request.form.getlist("options")]
    addon_ids = request.form.getlist("addons")
    for kind, label in UPLOADS:
        f = request.files.get(kind)
        if not f or not f.filename:
            if kind not in REQUIRED_UPLOADS:
                continue
            flash(f"กรุณาเลือก{label.split(':')[0]} ({label.split(': ', 1)[1]})")
            return redirect(url_for("plan_form"))
        if os.path.splitext(f.filename)[1].lower() not in ALLOWED:
            flash(f"{label.split(':')[0]}: รองรับเฉพาะไฟล์ .doc, .docx และ .pdf เท่านั้น")
            return redirect(url_for("plan_form"))
        ups[kind] = (os.path.basename(f.filename), f.save)
    fields = {k: (request.form.get(k) or "").strip() for k in FIELD_KEYS}
    if fields["teach_month"] and fields["teach_month"] not in THAI_MONTHS:
        fields["teach_month"] = ""
    if "source" not in ups and len(instructions) < MIN_INSTRUCTIONS:
        flash("ไม่ได้แนบไฟล์ที่ 2 (ไฟล์ข้อมูล): กรุณาพิมพ์คำสั่งเพิ่มเติมถึงผู้จัดทำ "
              "โดยระบุอย่างน้อย วิชา / ชั้น / เรื่อง ที่ต้องการ (เช่น \"ทำแผนที่ 1 เรื่อง เศษส่วน ป.4\")")
        return redirect(url_for("plan_form"))
    u = current_user()
    job = store.create_job(ups, fields, instructions, plan_counter=detect_plans,
                           instructions=instructions, options=options, addons=addon_ids,
                           user_id=u["id"] if u else None)
    d = store.job_dir(job["id"])
    for kind in ("template", "source"):
        if job["files"].get(kind) and os.path.getsize(os.path.join(d, job["files"][kind])) > MAX_MB * 1024 * 1024:
            shutil.rmtree(d)
            flash(f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_MB} MB ต่อไฟล์)")
            return redirect(url_for("plan_form"))
    if job["status"] == "awaiting_choice":
        return redirect(url_for("choose_plan", job_id=job["id"]))
    if job["status"] == "awaiting_payment":
        return redirect(url_for("pay_page", job_id=job["id"]))
    # Only notify workers once the job is actually in the work queue
    if job["status"] == "queued":
        fire_webhook(job["id"])
    return redirect(url_for("job_page", job_id=job["id"]))



def _save_upload_factory(file_storage):
    """Return (basename, save_fn) for store helpers."""
    return (os.path.basename(file_storage.filename), file_storage.save)


def _parse_service_form(service):
    """Validate catalog form; return (inputs, uploads, error_message)."""
    inputs = {}
    uploads = {}
    for field in service.get("inputs") or []:
        fid = field["id"]
        ftype = field.get("type")
        required = bool(field.get("required"))
        if ftype in ("file", "files"):
            if ftype == "files":
                flist = request.files.getlist(fid)
            else:
                one = request.files.get(fid)
                flist = [one] if one and one.filename else []
            flist = [f for f in flist if f and f.filename]
            if required and not flist:
                return None, None, f"กรุณาอัปโหลด{field.get('label') or fid}"
            accept = {a.lower() for a in (field.get("accept") or [])}
            saved = []
            for f in flist:
                ext = os.path.splitext(f.filename)[1].lower()
                if accept and ext not in accept:
                    return None, None, f"{field.get('label')}: รองรับเฉพาะ {' '.join(sorted(accept))}"
                if ext not in ALLOWED_SERVICE:
                    return None, None, f"ชนิดไฟล์ไม่รองรับ: {ext}"
                saved.append(_save_upload_factory(f))
            if saved:
                uploads[fid] = saved if ftype == "files" else saved[0]
            continue
        raw = (request.form.get(fid) or "").strip()
        if ftype == "number":
            if raw == "":
                if required:
                    return None, None, f"กรุณากรอก{field.get('label') or fid}"
                if field.get("default") is not None:
                    inputs[fid] = field["default"]
                continue
            try:
                num = int(raw)
            except ValueError:
                try:
                    num = float(raw)
                except ValueError:
                    return None, None, f"{field.get('label')}: ต้องเป็นตัวเลข"
            if field.get("min") is not None and num < field["min"]:
                return None, None, f"{field.get('label')}: อย่างน้อย {field['min']}"
            if field.get("max") is not None and num > field["max"]:
                return None, None, f"{field.get('label')}: ไม่เกิน {field['max']}"
            inputs[fid] = num
        else:
            if required and not raw:
                return None, None, f"กรุณากรอก{field.get('label') or fid}"
            if raw:
                if ftype == "select" and field.get("choices") and raw not in field["choices"]:
                    return None, None, f"ค่าที่เลือกไม่ถูกต้อง: {field.get('label')}"
                inputs[fid] = raw
            elif field.get("default") is not None:
                inputs[fid] = field["default"]
    return inputs, uploads, None


@app.get("/services")
def services_all():
    groups = catalog.services_by_group(include_disabled=False, home=True)
    meta = brand.page_meta(
        title="บริการทั้งหมดสำหรับครู — แผนการสอน สื่อ ใบงาน แปลงไฟล์",
        description="รวมบริการครูดี: ทำแผนการจัดการเรียนรู้ สื่อการสอน ใบงาน ข้อสอบ ว.PA SAR แปลง PDF เป็น Word ภาษาไทย",
        path="/services",
    )
    return render_template("services_all.html", groups=groups, group_icons=catalog.GROUP_ICONS,
                           group_svg=brand.GROUP_SVG, meta=meta)


@app.get("/group/<path:group_name>")
def group_page(group_name):
    groups = dict(catalog.services_by_group(include_disabled=False, home=True))
    if group_name not in groups:
        abort(404)
    meta = brand.page_meta(
        title=f"{group_name} — บริการสำหรับครู",
        description=f"บริการ{group_name} บนครูดี: สะดวก รวดเร็ว สำหรับครูไทย",
        path=f"/group/{group_name}",
    )
    return render_template("group.html", group=group_name, services=groups[group_name],
                           icon=catalog.GROUP_ICONS.get(group_name, "📦"),
                           icon_svg=brand.group_icon(group_name),
                           unit_label=catalog.unit_label, meta=meta)


@app.get("/services/<service_id>")
def service_form(service_id):
    if service_id == "lesson_plan":
        return redirect(url_for("plan_form"))
    svc = catalog.get_service(service_id, include_disabled=False)
    if not svc or svc.get("special_form"):
        abort(404)
    # Split essential (required) vs optional fields for collapsible UI
    required, optional = [], []
    for f in svc.get("inputs") or []:
        (required if f.get("required") else optional).append(f)
    meta = brand.page_meta(
        title=f"{svc.get('name')} — สั่งงานออนไลน์สำหรับครู",
        description=(svc.get("description") or "")[:160] or brand.SITE_DESC,
        path=f"/services/{service_id}",
        og_type="product",
    )
    return render_template("service_form.html", service=svc, required_fields=required,
                           optional_fields=optional, max_mb=MAX_MB,
                           unit_label=catalog.unit_label,
                           show_price=bool(svc.get("collect_payment")),
                           meta=meta, jsonld_service=True)


@app.post("/services/<service_id>/submit")
@login_required
def service_submit(service_id):
    if service_id == "lesson_plan":
        return redirect(url_for("plan_form"))
    svc = catalog.get_service(service_id, include_disabled=False)
    if not svc or svc.get("special_form"):
        abort(404)
    inputs, uploads, err = _parse_service_form(svc)
    if err:
        flash(err)
        return redirect(url_for("service_form", service_id=service_id))
    u = current_user()
    cost = int(svc.get("points_cost") or 0)
    if cost > 0:
        bal = int((u or {}).get("points") or 0)
        if bal < cost:
            flash(f"พ้อยท์ไม่พอ — บริการนี้ใช้ {cost} พ้อยท์ (คุณมี {bal} พ้อยท์)")
            return redirect(url_for("service_form", service_id=service_id))
    # size check helper after create
    file_count = 0
    for v in (uploads or {}).values():
        file_count += len(v) if isinstance(v, list) else 1
    # Deduct points before creating job (atomic-ish under users lock)
    if cost > 0:
        try:
            users.ensure_points(u["id"], cost, reason=f"ใช้บริการ {svc.get('name')}", job_id=None)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("service_form", service_id=service_id))
    job = store.create_service_job(svc, inputs, uploads, file_count=max(1, file_count),
                                   user_id=u["id"] if u else None, points_spent=cost)
    if cost > 0 and job:
        # backfill job_id on latest ledger entry
        try:
            uu = users.load_user(u["id"])
            if uu and uu.get("ledger"):
                if not uu["ledger"][0].get("job_id"):
                    uu["ledger"][0]["job_id"] = job["id"]
                    users.save_user(uu)
        except Exception:
            pass
    d = store.job_dir(job["id"])
    # enforce per-file size
    for name in os.listdir(d):
        if name == "job.json":
            continue
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.path.getsize(p) > MAX_MB * 1024 * 1024:
            import shutil as _sh
            _sh.rmtree(d)
            if cost > 0 and u:
                try:
                    users.adjust_points(u["id"], cost, reason="คืนพ้อยท์ — ไฟล์ใหญ่เกินไป", job_id=None, typ="refund")
                except Exception:
                    pass
            flash(f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_MB} MB ต่อไฟล์)")
            return redirect(url_for("service_form", service_id=service_id))
    # Free auto services: fulfil immediately
    if job["status"] == "queued" and job.get("fulfil") == "auto":
        job = store.try_auto_fulfil(job["id"])
        return redirect(url_for("job_page", job_id=job["id"]))
    if job["status"] == "awaiting_payment":
        return redirect(url_for("pay_page", job_id=job["id"]))
    if job["status"] == "queued":
        fire_webhook(job["id"])
    return redirect(url_for("job_page", job_id=job["id"]))


@app.get("/track")
def track_lookup():
    """Simple job-id lookup for teachers."""
    q = (request.args.get("id") or "").strip()
    if q:
        try:
            j = store.load(q)
        except ValueError:
            j = None
        if j:
            return redirect(url_for("job_page", job_id=q))
        flash("ไม่พบรหัสงานนี้")
    meta = brand.page_meta(
        title="ติดตามงาน — เช็กสถานะแผนการสอนและเอกสารครู",
        description="กรอกรหัสงานเพื่อติดตามสถานะการจัดทำแผนการจัดการเรียนรู้ สื่อการสอน ใบงาน หรือเอกสารครูบนครูดี",
        path="/track",
    )
    return render_template("track.html", meta=meta)


def plan_choice_text(job):
    """Thai description of which plan(s) will be produced."""
    n = max(1, int(job.get("plan_count") or 1))
    if job.get("plan_mode") == "one" and job.get("plan_selected") is not None:
        return f"ทำแผนเดียว: แผนการจัดการเรียนรู้ที่ {job['plan_selected']} (จากทั้งหมด {n} แผนในไฟล์)"
    if n > 1:
        return f"ทำทั้ง {n} แผน (รวมเป็นไฟล์เดียว)"
    return ""


@app.route("/job/<job_id>/choose", methods=["GET", "POST"])
def choose_plan(job_id):
    try:
        job = store.load(job_id)
    except ValueError:
        abort(404)
    if not job:
        abort(404)
    if job["status"] != "awaiting_choice":
        return redirect(url_for("job_page", job_id=job_id))
    nums = job.get("plan_numbers") or []
    if request.method == "POST":
        mode = request.form.get("plan_mode")
        if mode == "one":
            try:
                sel = int(request.form.get("plan_selected") or "")
            except ValueError:
                sel = None
            if sel is None or (nums and sel not in nums):
                flash("กรุณาเลือกเลขแผนที่ต้องการ")
                return redirect(url_for("choose_plan", job_id=job_id))
            store.set_plan_choice(job_id, "one", sel)
        elif mode == "all":
            store.set_plan_choice(job_id, "all")
        else:
            flash("กรุณาเลือกว่าจะทำแผนเดียวหรือทำทั้งหมด")
            return redirect(url_for("choose_plan", job_id=job_id))
        return redirect(url_for("pay_page", job_id=job_id))
    avg = store.avg_minutes_per_plan()
    price = float(store.load_settings().get("price_per_plan") or 10)
    return render_template("choose.html", job=job, n=job.get("plan_count") or 1, nums=nums,
                           avg=round(avg, 1), price_per_plan=price)


# ---------------- payment (PromptPay slip) ----------------
@app.route("/job/<job_id>/pay", methods=["GET", "POST"])
def pay_page(job_id):
    try:
        job = store.load(job_id)
    except ValueError:
        abort(404)
    if not job:
        abort(404)
    if job["status"] == "awaiting_choice":
        return redirect(url_for("choose_plan", job_id=job_id))
    if job["status"] not in ("awaiting_payment", "payment_rejected", "payment_review"):
        return redirect(url_for("job_page", job_id=job_id))
    if not job.get("payment"):
        store.begin_payment(job_id)
        job = store.load(job_id)
    if request.method == "POST":
        f = request.files.get("slip")
        if not f or not f.filename:
            flash("กรุณาอัปโหลดสลิปการโอนเงิน")
            return redirect(url_for("pay_page", job_id=job_id))
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in store.SLIP_EXTS:
            flash("รองรับสลิปเป็นไฟล์รูป (.jpg .png .webp .gif) หรือ .pdf เท่านั้น")
            return redirect(url_for("pay_page", job_id=job_id))
        # size check after save
        try:
            job = store.save_slip(job_id, f.save, os.path.basename(f.filename))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("pay_page", job_id=job_id))
        d = store.job_dir(job_id)
        slip_path = os.path.join(d, job["payment"]["slip_file"])
        if os.path.getsize(slip_path) > SLIP_MAX_MB * 1024 * 1024:
            try:
                os.remove(slip_path)
            except OSError:
                pass
            flash(f"ไฟล์สลิปใหญ่เกินไป (สูงสุด {SLIP_MAX_MB} MB)")
            # revert to awaiting_payment
            with store.lock():
                j = store.load(job_id)
                j["status"] = "awaiting_payment"
                j["payment"]["slip_file"] = None
                j["files"]["slip"] = None
                store.save(j)
            return redirect(url_for("pay_page", job_id=job_id))
        flash("อัปโหลดสลิปแล้ว รอตรวจสอบการชำระเงิน")
        return redirect(url_for("job_page", job_id=job_id))
    settings = store.load_settings()
    pay = job["payment"]
    qr_path, qr_src = store.qr_image_path_for_display(amount=pay.get("amount_due"))
    return render_template("pay.html", job=job, pay=pay, settings=settings,
                           qr_src=qr_src, has_qr=bool(qr_path),
                           status_th=STATUS_TH, slip_max_mb=SLIP_MAX_MB,
                           plan_choice=plan_choice_text(job))


@app.get("/job/<job_id>/pay/qr")
def pay_qr(job_id):
    try:
        job = store.load(job_id)
    except ValueError:
        abort(404)
    if not job or not job.get("payment"):
        abort(404)
    amount = (job.get("payment") or {}).get("amount_due")
    path, src = store.qr_image_path_for_display(amount=amount)
    if not path:
        abort(404)
    return send_file(path, mimetype="image/png", download_name="promptpay_qr.png")


@app.get("/job/<job_id>/slip")
def job_slip(job_id):
    """Teacher/admin can view the uploaded slip (no auth on teacher link; id is unguessable)."""
    try:
        job = store.load(job_id)
    except ValueError:
        abort(404)
    if not job:
        abort(404)
    pay = job.get("payment") or {}
    name = pay.get("slip_file") or (job.get("files") or {}).get("slip")
    if not name:
        abort(404)
    path = os.path.join(store.job_dir(job_id), name)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, download_name=pay.get("slip_original_name") or name)


@app.get("/job/<job_id>")
def job_page(job_id):
    try:
        job = store.load(job_id)
    except ValueError:
        abort(404)
    if not job:
        abort(404)
    if job["status"] == "awaiting_choice":
        return redirect(url_for("choose_plan", job_id=job_id))
    if job["status"] in ("awaiting_payment", "payment_rejected"):
        return redirect(url_for("pay_page", job_id=job_id))
    f = job["fields"]
    teach_date = " ".join(x for x in (f.get("teach_day"), f.get("teach_month"), f.get("teach_year")) if x)
    return render_template("job.html", job=job, labels=LABELS, teach_date=teach_date,
                           plan_count=store.plan_count_of(job), plan_choice=plan_choice_text(job),
                           instructions=store.instructions_of(job), status_th=STATUS_TH)


@app.get("/api/job/<job_id>")
def job_status(job_id):
    try:
        info = store.status_info(job_id)
    except ValueError:
        info = None
    if not info:
        return jsonify({"error": "not found"}), 404
    info["status_th"] = STATUS_TH.get(info["status"], info["status"])
    info["plan_choice_th"] = plan_choice_text(store.load(job_id) or {})
    return jsonify(info)


@app.get("/job/<job_id>/download/<kind>")
def download(job_id, kind):
    try:
        job = store.load(job_id)
    except ValueError:
        abort(404)
    if not job:
        abort(404)
    # kind may be docx|pdf|pptx|xlsx|png|zip|txt or result index like r0
    name = None
    orig = None
    if kind.startswith("r") and kind[1:].isdigit():
        results = job.get("results") or []
        idx = int(kind[1:])
        if 0 <= idx < len(results):
            name = results[idx]["name"]
            orig = results[idx].get("original_name") or name
            kind = results[idx].get("kind") or os.path.splitext(name)[1].lstrip(".")
    else:
        name = (job.get("files") or {}).get(f"result_{kind}")
        if not name:
            for r in job.get("results") or []:
                if r.get("kind") == kind:
                    name = r["name"]
                    orig = r.get("original_name")
                    break
    if not name:
        abort(404)
    path = os.path.join(store.job_dir(job_id), name)
    if not os.path.isfile(path):
        abort(404)
    svc_name = job.get("service_name") or "ผลลัพธ์"
    plan = (job.get("fields") or {}).get("plan_no") or ""
    if (job.get("service_id") or "lesson_plan") == "lesson_plan" and kind in ("docx", "pdf"):
        dl = f"แผนการจัดการเรียนรู้{('ที่' + plan) if plan else ''}_{job_id}.{kind}"
    else:
        ext = os.path.splitext(name)[1] or ("." + kind if kind else "")
        dl = orig or f"{svc_name}_{job_id}{ext}"
    return send_file(path, as_attachment=True, download_name=dl)



# ---------------- auth (Google + test) ----------------
@app.get("/login")
def login():
    nxt = request.args.get("next") or session.get("after_login") or "/"
    session["after_login"] = nxt
    meta = brand.page_meta(title="เข้าสู่ระบบ", description="เข้าสู่ระบบครูดีด้วย Google", path="/login")
    return render_template("login.html", next=nxt, meta=meta,
                           oauth_ready=bool(_oauth), test_login=LP_TEST_LOGIN)


@app.get("/auth/google")
def auth_google():
    if not _oauth:
        flash("ยังไม่ได้ตั้งค่า Google Login — กรุณาติดต่อผู้ดูแลระบบ (ยังไม่มี GOOGLE_CLIENT_ID/SECRET)")
        return redirect(url_for("login"))
    nxt = request.args.get("next") or session.get("after_login") or "/"
    session["after_login"] = nxt
    redirect_uri = _public_url("/auth/google/callback")
    return _oauth.google.authorize_redirect(redirect_uri)


@app.get("/auth/google/callback")
def auth_google_callback():
    if not _oauth:
        flash("ระบบเข้าสู่ระบบด้วย Google ยังไม่พร้อม")
        return redirect(url_for("login"))
    try:
        token = _oauth.google.authorize_access_token()
    except Exception as e:
        log.warning("Google callback failed: %s", e)
        flash("เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่")
        return redirect(url_for("login"))
    info = token.get("userinfo") or {}
    if not info:
        try:
            info = _oauth.google.userinfo()
        except Exception:
            info = {}
    sub = info.get("sub")
    if not sub:
        flash("ไม่ได้รับข้อมูลผู้ใช้จาก Google")
        return redirect(url_for("login"))
    u = users.upsert_google_user(
        sub=sub,
        email=info.get("email"),
        name=info.get("name") or info.get("given_name"),
        picture=info.get("picture"),
    )
    session["user_id"] = u["id"]
    session.pop("_user_cached", None)
    nxt = _safe_next(session.pop("after_login", None)) or "/"
    flash(f"ยินดีต้อนรับ คุณ{u.get('name') or ''}")
    return redirect(nxt)


@app.post("/logout")
def logout():
    session.pop("user_id", None)
    flash("ออกจากระบบแล้ว")
    return redirect(url_for("index"))


@app.get("/auth/test-login")
def auth_test_login():
    """Test-only login. Enabled only when LP_TEST_LOGIN=1 (never in production)."""
    if not LP_TEST_LOGIN:
        abort(404)
    email = (request.args.get("email") or "teacher@example.com").strip()
    name = (request.args.get("name") or "ครูทดสอบ").strip()
    sub = "test_" + email
    u = users.upsert_google_user(sub=sub, email=email, name=name, picture="")
    session["user_id"] = u["id"]
    nxt = _safe_next(request.args.get("next")) or _safe_next(session.pop("after_login", None)) or "/"
    return redirect(nxt)


@app.get("/my-jobs")
@login_required
def my_jobs():
    u = current_user()
    jobs = store.jobs_for_user(u["id"])
    meta = brand.page_meta(title="งานของฉัน", description="รายการงานที่คุณสั่งกับครูดี", path="/my-jobs")
    return render_template("my_jobs.html", jobs=jobs, status_th=STATUS_TH, meta=meta, user=u)


@app.get("/points/topup")
@login_required
def points_topup():
    settings = store.load_settings()
    if not settings.get("points_topup_enabled"):
        flash("ยังไม่เปิดให้เติมพ้อยท์ในขณะนี้")
        return redirect(url_for("index"))
    meta = brand.page_meta(title="เติมพ้อยท์", description="ซื้อพ้อยท์ด้วย PromptPay", path="/points/topup")
    return render_template("points_topup.html", packages=settings.get("points_packages") or [],
                           settings=settings, meta=meta, user=current_user())


@app.post("/points/topup")
@login_required
def points_topup_submit():
    settings = store.load_settings()
    if not settings.get("points_topup_enabled"):
        flash("ยังไม่เปิดให้เติมพ้อยท์")
        return redirect(url_for("index"))
    pid = request.form.get("package_id") or ""
    pkg = next((p for p in (settings.get("points_packages") or []) if p.get("id") == pid), None)
    if not pkg:
        flash("ไม่พบแพ็กเกจที่เลือก")
        return redirect(url_for("points_topup"))
    u = current_user()
    job = store.create_topup_job(u["id"], pkg)
    return redirect(url_for("pay_page", job_id=job["id"]))



# ---------------- legal / public policy pages ----------------
@app.get("/privacy")
def privacy():
    meta = brand.page_meta(
        title="นโยบายความเป็นส่วนตัว",
        description="นโยบายความเป็นส่วนตัวของครูดี (krudee.cc): ข้อมูล Google ที่เก็บ การใช้ไฟล์ และการขอลบข้อมูล",
        path="/privacy",
    )
    return render_template("privacy.html", meta=meta)


@app.get("/terms")
def terms():
    meta = brand.page_meta(
        title="ข้อกำหนดการใช้บริการ",
        description="ข้อกำหนดการใช้บริการครูดี (krudee.cc) สำหรับการสั่งงานและใช้งานเว็บไซต์",
        path="/terms",
    )
    return render_template("terms.html", meta=meta)


# ---------------- SEO ----------------
@app.get("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /admin/",
        "Disallow: /job/",
        "Disallow: /auth/",
        "Disallow: /api/",
        f"Sitemap: {brand.SITE_URL}/sitemap.xml",
        "",
    ]
    return app.response_class(chr(10).join(lines), mimetype="text/plain; charset=utf-8")


@app.get("/sitemap.xml")
def sitemap_xml():
    urls = ["/"]
    urls.append("/services")
    urls.append("/plan")
    urls.append("/track")
    urls.append("/privacy")
    urls.append("/terms")
    for group, _svcs in catalog.services_by_group(include_disabled=False, home=True):
        urls.append(f"/group/{group}")
    for s in catalog.all_services(include_disabled=False):
        if s.get("special_form"):
            urls.append("/plan")
        else:
            urls.append(f"/services/{s['id']}")
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    items = []
    for path in ordered:
        loc = brand.SITE_URL.rstrip("/") + path
        items.append(f"  <url><loc>{loc}</loc><changefreq>weekly</changefreq></url>")
    nl = chr(10)
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + nl
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + nl
    xml += nl.join(items) + nl + "</urlset>" + nl
    return app.response_class(xml, mimetype="application/xml")


@app.get("/site.webmanifest")
def webmanifest():
    data = {
        "name": "ครูดี — บริการครู",
        "short_name": "ครูดี",
        "description": brand.SITE_DESC,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f1f5f9",
        "theme_color": "#22A386",
        "lang": "th",
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    return jsonify(data)


# ---------------- admin ----------------
def _admin_back(default_anchor):
    """Return to the top-up board (keeping its filter/page) when the form came from it."""
    if request.form.get("from_board"):
        args = {k: v for k in ("board", "board_page") if (v := request.form.get(k))}
        return url_for("admin", **args) + "#board"
    return url_for("admin") + default_anchor

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and request.form.get("action") == "login":
        if ADMIN_PASSWORD and hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
        else:
            flash("รหัสผ่านไม่ถูกต้อง")
        return redirect(url_for("admin"))
    if not session.get("admin"):
        return render_template("admin_login.html")
    action = request.form.get("action") if request.method == "POST" else None
    if action == "upload":
        f = request.files.get("template")
        if not f or not f.filename.lower().endswith(".docx"):
            flash("กรุณาเลือกไฟล์แม่แบบ .docx")
        else:
            tmp = store.TEMPLATE_PATH + ".tmp"
            f.save(tmp)
            if os.path.exists(store.TEMPLATE_PATH):
                shutil.copy2(store.TEMPLATE_PATH, store.TEMPLATE_PATH + ".bak")
            os.replace(tmp, store.TEMPLATE_PATH)
            flash("อัปโหลดแม่แบบใหม่เรียบร้อยแล้ว")
        return redirect(url_for("admin"))
    if action == "settings":
        store.save_settings({
            "price_per_plan": request.form.get("price_per_plan"),
            "payee_name": request.form.get("payee_name"),
            "promptpay_id": request.form.get("promptpay_id"),
        })
        flash("บันทึกการตั้งค่าเรียบร้อยแล้ว")
        return redirect(url_for("admin") + "#settings")
    if action == "save_services":
        updates = {}
        for s in catalog.all_services(include_disabled=True):
            sid = s["id"]
            patch = {
                "enabled": request.form.get(f"enabled_{sid}") == "1",
                "collect_payment": request.form.get(f"pay_{sid}") == "1",
            }
            price_raw = request.form.get(f"price_{sid}")
            if price_raw is not None and price_raw != "":
                patch["price"] = price_raw
            pts_raw = request.form.get(f"points_{sid}")
            if pts_raw is not None and pts_raw != "":
                patch["points_cost"] = pts_raw
            desc = request.form.get(f"desc_{sid}")
            if desc is not None:
                patch["description"] = desc
            updates[sid] = patch
        catalog.save_service_overrides(updates)
        flash("บันทึกบริการเรียบร้อยแล้ว")
        return redirect(url_for("admin") + "#services")
    if action == "points_settings":
        enabled = request.form.get("points_topup_enabled") == "1"
        packages = []
        for i in range(8):
            baht = request.form.get(f"pkg_baht_{i}")
            pts = request.form.get(f"pkg_points_{i}")
            label = request.form.get(f"pkg_label_{i}")
            if not baht and not pts:
                continue
            try:
                packages.append({
                    "id": request.form.get(f"pkg_id_{i}") or f"p{int(float(baht))}",
                    "baht": float(baht),
                    "points": int(pts),
                    "label": (label or f"{pts} พ้อยท์").strip(),
                })
            except (TypeError, ValueError):
                continue
        store.save_settings({
            "points_topup_enabled": enabled,
            "points_packages": packages or store.DEFAULT_POINTS_PACKAGES,
        })
        flash("บันทึกตั้งค่าพ้อยท์เรียบร้อยแล้ว")
        return redirect(url_for("admin") + "#users")
    if action == "points_adjust":
        uid = request.form.get("user_id") or ""
        try:
            amount = int(request.form.get("amount") or 0)
        except ValueError:
            amount = 0
        reason = (request.form.get("reason") or "").strip() or "ปรับโดยแอดมิน"
        try:
            u, entry = users.adjust_points(uid, amount, reason=reason, admin="admin", typ="admin")
            flash(f"ปรับพ้อยท์ {u.get('email') or uid}: {amount:+d} → คงเหลือ {u.get('points')}")
        except (KeyError, ValueError) as e:
            flash(f"ปรับพ้อยท์ไม่สำเร็จ: {e}")
        return redirect(url_for("admin", user_q=request.form.get("user_q") or "", user_id=uid) + "#users")
    if action == "upload_qr":
        f = request.files.get("qr_image")
        if not f or not f.filename:
            flash("กรุณาเลือกไฟล์รูป QR PromptPay")
        else:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in QR_UPLOAD_EXTS:
                flash("รองรับเฉพาะไฟล์รูป .png .jpg .webp .gif")
            else:
                s = store.set_qr_image(f.save, os.path.basename(f.filename))
                msg = "อัปโหลด QR PromptPay เรียบร้อยแล้ว"
                if s.get("qr_decoded_id"):
                    msg += f" (ถอดรหัสได้ PromptPay ID: …{str(s['qr_decoded_id'])[-4:]})"
                else:
                    msg += " (ยังถอดรหัส ID จากรูปไม่ได้ — กรอก PromptPay ID เองได้)"
                flash(msg)
        return redirect(url_for("admin") + "#settings")
    if action == "clear_qr":
        store.clear_qr_image()
        flash("ลบรูป QR แล้ว")
        return redirect(url_for("admin") + "#settings")
    if action == "pay_approve":
        jid = request.form.get("job_id") or ""
        try:
            j = store.approve_payment(
                jid,
                slip_ref=request.form.get("slip_ref") or None,
                amount=request.form.get("amount") or None,
                transfer_time=request.form.get("transfer_time") or None,
                payer_name=request.form.get("payer_name") or None,
                payee_name=request.form.get("payee_name") or None,
                note=request.form.get("note") or "admin override",
                by="admin",
            )
            if j.pop("_run_auto", False) or j.get("fulfil") == "auto":
                j = store.try_auto_fulfil(j["id"])
                flash(f"อนุมัติงาน {jid} แล้ว — ทำอัตโนมัติเสร็จ")
            else:
                fire_webhook(j["id"])
                flash(f"อนุมัติการชำระเงินงาน {jid} แล้ว — เข้าคิวแล้ว")
        except (KeyError, ValueError) as e:
            flash(f"อนุมัติไม่สำเร็จ: {e}")
        return redirect(_admin_back("#payments"))
    if action == "pay_reject":
        jid = request.form.get("job_id") or ""
        reason = (request.form.get("reason") or "").strip() or "สลิปไม่ถูกต้อง"
        try:
            store.reject_payment(jid, reason, by="admin")
            flash(f"ปฏิเสธสลิปงาน {jid}: {reason}")
        except (KeyError, ValueError) as e:
            flash(f"ปฏิเสธไม่สำเร็จ: {e}")
        return redirect(_admin_back("#payments"))
    tpl = None
    if os.path.exists(store.TEMPLATE_PATH):
        st = os.stat(store.TEMPLATE_PATH)
        from datetime import datetime
        tpl = {"size_kb": round(st.st_size / 1024),
               "mtime": datetime.fromtimestamp(st.st_mtime, store.TZ).strftime("%d/%m/%Y %H:%M")}
    svc_filter = request.args.get("service") or ""
    allj = store.all_jobs()
    jobs = list(reversed(allj))
    if svc_filter:
        jobs = [j for j in jobs if (j.get("service_id") or "lesson_plan") == svc_filter]
    jobs = jobs[:50]
    pay_filter = request.args.get("pay_status") or ""
    if pay_filter:
        pay_jobs = [j for j in reversed(allj) if j["status"] == pay_filter]
    else:
        pay_jobs = [j for j in reversed(allj)
                    if j["status"] in store.PAYMENT_STATUSES
                    or (j.get("payment") and j["status"] in ("queued", "processing", "done", "failed"))]
    if svc_filter:
        pay_jobs = [j for j in pay_jobs if (j.get("service_id") or "lesson_plan") == svc_filter]
    pay_jobs = pay_jobs[:100]
    settings = store.load_settings()
    totals = store.payment_totals()
    has_qr = os.path.isfile(store.QR_IMAGE_PATH)
    try:
        board_page = int(request.args.get("board_page") or 1)
    except ValueError:
        board_page = 1
    board = store.topup_board(request.args.get("board") or "all", board_page)
    services = catalog.all_services(include_disabled=True)
    # simple per-service job counts
    svc_stats = {}
    for j in allj:
        sid = j.get("service_id") or "lesson_plan"
        svc_stats[sid] = svc_stats.get(sid, 0) + 1
    user_q = request.args.get("user_q") or ""
    user_id = request.args.get("user_id") or ""
    user_list = users.search_users(user_q)
    selected_user = users.load_user(user_id) if user_id else None
    pts_totals = users.points_totals()
    return render_template("admin.html", board=board, tpl=tpl, jobs=jobs, status_th=STATUS_TH,
                           pay_jobs=pay_jobs, pay_filter=pay_filter, settings=settings,
                           totals=totals, has_qr=has_qr, services=services,
                           svc_filter=svc_filter, svc_stats=svc_stats,
                           unit_label=catalog.unit_label,
                           user_list=user_list, selected_user=selected_user,
                           user_q=user_q, pts_totals=pts_totals)


@app.get("/admin/qr")
def admin_qr():
    if not session.get("admin"):
        abort(403)
    if not os.path.isfile(store.QR_IMAGE_PATH):
        abort(404)
    return send_file(store.QR_IMAGE_PATH, mimetype="image/png", download_name="promptpay_qr.png")


@app.get("/admin/template")
def admin_template():
    if not session.get("admin"):
        abort(403)
    return send_file(store.TEMPLATE_PATH, as_attachment=True, download_name="main.docx")


@app.post("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin"))


# ---------------- worker API ----------------
def require_worker():
    tok = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() \
        or request.headers.get("X-Worker-Token", "")
    if not WORKER_TOKEN or not hmac.compare_digest(tok, WORKER_TOKEN):
        abort(401)


WORKER_FILE_KINDS = ("template", "source", "result_docx", "result_pdf", "slip")


def worker_view(job):
    """Job JSON + local paths + token-protected download URLs for remote workers."""
    j = store.with_paths(job)
    j["service_id"] = job.get("service_id") or "lesson_plan"
    j["service_name"] = job.get("service_name") or "แผนการจัดการเรียนรู้"
    j["fulfil"] = job.get("fulfil") or "worker"
    j["inputs"] = job.get("inputs") or {}
    j["addons"] = job.get("addons") or []
    j["results"] = job.get("results") or []
    j["plan_count"] = max(1, int(job.get("plan_count") or 1))  # detected in source file
    j["plan_numbers"] = job.get("plan_numbers") or []
    j["plan_mode"] = job.get("plan_mode") or "all"
    j["plan_selected"] = job.get("plan_selected")
    j["effective_plan_count"] = store.plan_count_of(job)
    j["plan_choice_th"] = plan_choice_text(job)
    j["instructions"] = store.instructions_of(job)
    j["options"] = job.get("options") or []
    j["from_scratch"] = bool(job.get("from_scratch"))
    j["eta_factor"] = store.eta_factor(job)
    j["payment"] = job.get("payment")
    files = job.get("files") or {}
    # slip may live only under payment.slip_file
    if job.get("payment") and job["payment"].get("slip_file") and not files.get("slip"):
        files = dict(files)
        files["slip"] = job["payment"]["slip_file"]
        j["files"] = files
    j["urls"] = {k: url_for("worker_file", job_id=job["id"], kind=k, _external=True)
                 for k in WORKER_FILE_KINDS if files.get(k)}
    # upload file URLs (generic services)
    for i, u in enumerate(files.get("uploads") or []):
        j["urls"][f"upload_{i}"] = url_for("worker_file", job_id=job["id"], kind=f"upload_{i}", _external=True)
    j["urls"]["page"] = url_for("job_page", job_id=job["id"], _external=True)
    return j


def load_or_404(job_id):
    try:
        j = store.load(job_id)
    except ValueError:
        j = None
    if not j:
        abort(404)
    return j


@app.get("/api/worker/next")
def worker_next():
    require_worker()
    service = request.args.get("service") or None
    j = store.claim_next(service_id=service)
    return jsonify({"job": worker_view(j) if j else None})


@app.get("/api/worker/jobs")
def worker_jobs():
    require_worker()
    st = request.args.get("status")
    service = request.args.get("service") or None
    jobs = []
    for j in store.all_jobs():
        if st and j["status"] != st:
            continue
        if service and (j.get("service_id") or "lesson_plan") != service:
            continue
        if j.get("fulfil") == "auto" and j["status"] in ("queued", "processing"):
            continue
        jobs.append(j)
    return jsonify({"jobs": [worker_view(j) for j in jobs]})


@app.get("/api/worker/<job_id>")
def worker_show(job_id):
    require_worker()
    return jsonify({"job": worker_view(load_or_404(job_id))})


@app.post("/api/worker/<job_id>/claim")
def worker_claim(job_id):
    require_worker()
    load_or_404(job_id)
    try:
        j = store.claim(job_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"job": worker_view(j)})


@app.post("/api/worker/<job_id>/requeue")
def worker_requeue(job_id):
    require_worker()
    load_or_404(job_id)
    return jsonify({"job": worker_view(store.requeue(job_id))})


@app.get("/api/worker/<job_id>/file/<kind>")
def worker_file(job_id, kind):
    require_worker()
    j = load_or_404(job_id)
    name = None
    orig = None
    if kind.startswith("upload_") and kind.split("_", 1)[1].isdigit():
        idx = int(kind.split("_", 1)[1])
        uploads = (j.get("files") or {}).get("uploads") or []
        if 0 <= idx < len(uploads):
            name = uploads[idx]["stored"]
            orig = uploads[idx].get("original_name") or name
    elif kind in WORKER_FILE_KINDS:
        name = j["files"].get(kind)
        if kind == "slip" and not name:
            name = (j.get("payment") or {}).get("slip_file")
        if kind == "slip":
            orig = (j.get("payment") or {}).get("slip_original_name") or name
        else:
            orig = j["files"].get(kind + "_original_name") or name
    else:
        return jsonify({"error": f"unknown file kind: {kind}"}), 404
    if not name or not os.path.isfile(os.path.join(store.job_dir(job_id), name)):
        msg = "no source file (job is from_scratch: use instructions)" if kind == "source" else f"no {kind} file"
        return jsonify({"error": msg, "kind": kind, "from_scratch": bool(j.get("from_scratch"))}), 404
    return send_file(os.path.join(store.job_dir(job_id), name), as_attachment=True,
                     download_name=orig or name)


@app.post("/api/worker/<job_id>/complete")
def worker_complete(job_id):
    require_worker()
    job = load_or_404(job_id)
    data = request.form if request.form else (request.get_json(silent=True) or {})
    docx_f, pdf_f = request.files.get("docx"), request.files.get("pdf")
    docx_path, pdf_path = data.get("docx_path"), data.get("pdf_path")
    for p in (docx_path, pdf_path):
        if p and not os.path.isfile(p):
            return jsonify({"error": f"file not found on server: {p}"}), 400
    # Multi result files: result / result[] / result_0..
    multi = []
    for key in list(request.files.keys()):
        if key in ("docx", "pdf"):
            continue
        if key == "result" or key.startswith("result"):
            for f in request.files.getlist(key):
                if f and f.filename:
                    multi.append(f)
    sid = job.get("service_id") or "lesson_plan"
    if sid == "lesson_plan":
        if not docx_f and not docx_path and not multi:
            return jsonify({"error": "multipart field 'docx' (or docx_path) required"}), 400
        if docx_f and not docx_f.filename.lower().endswith(".docx"):
            return jsonify({"error": "docx must be a .docx file"}), 400
    else:
        if not docx_f and not docx_path and not pdf_f and not pdf_path and not multi:
            return jsonify({"error": "need at least one result file"}), 400
    extras = []
    for i, f in enumerate(multi):
        ext = os.path.splitext(f.filename)[1].lower()
        stored = f"result_{i}{ext}" if ext else f"result_{i}"
        kind = store.RESULT_KIND_BY_EXT.get(ext) or (ext.lstrip(".") if ext else "bin")
        # capture file storage before loop ends
        extras.append((f.save, stored, kind, f.filename))
    j = store.complete(job_id, docx_src=docx_path, pdf_src=pdf_path,
                       docx_writer=docx_f.save if docx_f else None,
                       pdf_writer=pdf_f.save if pdf_f else None,
                       extra_files=extras or None)
    return jsonify({"job": worker_view(j)})


@app.post("/api/worker/<job_id>/fail")
def worker_fail(job_id):
    require_worker()
    load_or_404(job_id)
    data = request.form if request.form else (request.get_json(silent=True) or {})
    return jsonify({"job": worker_view(store.fail(job_id, data.get("message") or "เกิดข้อผิดพลาด"))})


@app.get("/api/worker/payments")
def worker_payments():
    """List jobs awaiting slip verification (payment_review by default)."""
    require_worker()
    st = request.args.get("status") or "payment_review"
    jobs = [j for j in store.all_jobs() if j["status"] == st]
    return jsonify({"jobs": [worker_view(j) for j in jobs], "settings": {
        "price_per_plan": store.load_settings().get("price_per_plan"),
        "payee_name": store.load_settings().get("payee_name"),
        "promptpay_id": store.load_settings().get("promptpay_id") or store.load_settings().get("qr_decoded_id"),
    }})


@app.post("/api/worker/<job_id>/pay-ok")
def worker_pay_ok(job_id):
    require_worker()
    load_or_404(job_id)
    data = request.form if request.form else (request.get_json(silent=True) or {})
    try:
        j = store.approve_payment(
            job_id,
            slip_ref=data.get("slip_ref") or data.get("ref"),
            amount=data.get("amount"),
            transfer_time=data.get("transfer_time") or data.get("time"),
            payer_name=data.get("payer_name") or data.get("payer"),
            payee_name=data.get("payee_name") or data.get("payee"),
            note=data.get("note"),
            by="worker",
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    fire_webhook(j["id"])
    return jsonify({"job": worker_view(j)})


@app.post("/api/worker/<job_id>/pay-reject")
def worker_pay_reject(job_id):
    require_worker()
    load_or_404(job_id)
    data = request.form if request.form else (request.get_json(silent=True) or {})
    reason = data.get("reason") or data.get("message") or "สลิปไม่ถูกต้อง"
    try:
        j = store.reject_payment(job_id, reason, by="worker")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"job": worker_view(j)})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "template": os.path.exists(store.TEMPLATE_PATH)})


if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 8080))
    print(f"Serving on http://0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port, threads=8, max_request_body_size=(2 * MAX_MB + 2) * 1024 * 1024)
