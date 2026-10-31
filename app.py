import hmac, json, logging, os, shutil, threading, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
try:  # local development only; on Render, env vars come from the dashboard
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE, ".env"))
except ImportError:
    pass

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for, flash)
from werkzeug.middleware.proxy_fix import ProxyFix
import store
from plancount import detect_plans

ALLOWED = {".doc", ".docx", ".pdf"}
MAX_MB = 20
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()

log = logging.getLogger("lp-web")
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Render/Cloudflare HTTPS proxy
_secret = os.environ.get("SECRET_KEY", "")
if len(_secret) < 16:
    log.warning("SECRET_KEY missing/short: using a random key (admin sessions reset on restart)")
    _secret = os.urandom(32)
app.secret_key = _secret
app.config["MAX_CONTENT_LENGTH"] = (2 * MAX_MB + 2) * 1024 * 1024  # two files per submission
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
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
STATUS_TH = {"awaiting_choice": "รอเลือกแผน", "queued": "รอคิว", "processing": "กำลังทำ", "done": "เสร็จแล้ว", "failed": "ผิดพลาด"}


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
    flash(f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_MB} MB)")
    return redirect(url_for("index"))


@app.get("/")
def index():
    from datetime import datetime
    be = datetime.now(store.TZ).year + 543
    return render_template("index.html", fields=FIELDS, max_mb=MAX_MB, uploads=UPLOADS,
                           required_uploads=REQUIRED_UPLOADS, options=OPTIONS, min_instr=MIN_INSTRUCTIONS,
                           months=THAI_MONTHS, years=list(range(be - 1, be + 3)), this_year=be)


@app.post("/submit")
def submit():
    ups = {}
    instructions = (request.form.get("instructions") or request.form.get("note") or "").strip()
    options = [o for o in OPTIONS if o in request.form.getlist("options")]
    for kind, label in UPLOADS:
        f = request.files.get(kind)
        if not f or not f.filename:
            if kind not in REQUIRED_UPLOADS:
                continue
            flash(f"กรุณาเลือก{label.split(':')[0]} ({label.split(': ', 1)[1]})")
            return redirect(url_for("index"))
        if os.path.splitext(f.filename)[1].lower() not in ALLOWED:
            flash(f"{label.split(':')[0]}: รองรับเฉพาะไฟล์ .doc, .docx และ .pdf เท่านั้น")
            return redirect(url_for("index"))
        ups[kind] = (os.path.basename(f.filename), f.save)
    fields = {k: (request.form.get(k) or "").strip() for k in FIELD_KEYS}
    if fields["teach_month"] and fields["teach_month"] not in THAI_MONTHS:
        fields["teach_month"] = ""
    if "source" not in ups and len(instructions) < MIN_INSTRUCTIONS:
        flash("ไม่ได้แนบไฟล์ที่ 2 (ไฟล์ข้อมูล): กรุณาพิมพ์คำสั่งเพิ่มเติมถึงผู้จัดทำ "
              "โดยระบุอย่างน้อย วิชา / ชั้น / เรื่อง ที่ต้องการ (เช่น \"ทำแผนที่ 1 เรื่อง เศษส่วน ป.4\")")
        return redirect(url_for("index"))
    job = store.create_job(ups, fields, instructions, plan_counter=detect_plans,
                           instructions=instructions, options=options)
    d = store.job_dir(job["id"])
    for kind in ("template", "source"):
        if job["files"].get(kind) and os.path.getsize(os.path.join(d, job["files"][kind])) > MAX_MB * 1024 * 1024:
            shutil.rmtree(d)
            flash(f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_MB} MB ต่อไฟล์)")
            return redirect(url_for("index"))
    if job["status"] == "awaiting_choice":
        return redirect(url_for("choose_plan", job_id=job["id"]))
    fire_webhook(job["id"])
    return redirect(url_for("job_page", job_id=job["id"]))


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
        fire_webhook(job_id)
        return redirect(url_for("job_page", job_id=job_id))
    avg = store.avg_minutes_per_plan()
    return render_template("choose.html", job=job, n=job.get("plan_count") or 1, nums=nums,
                           avg=round(avg, 1))


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
    f = job["fields"]
    teach_date = " ".join(x for x in (f.get("teach_day"), f.get("teach_month"), f.get("teach_year")) if x)
    return render_template("job.html", job=job, labels=LABELS, teach_date=teach_date,
                           plan_count=store.plan_count_of(job), plan_choice=plan_choice_text(job),
                           instructions=store.instructions_of(job))


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
    if not job or kind not in ("docx", "pdf"):
        abort(404)
    name = job["files"].get(f"result_{kind}")
    if not name:
        abort(404)
    plan = job["fields"].get("plan_no") or ""
    dl = f"แผนการจัดการเรียนรู้{('ที่' + plan) if plan else ''}_{job_id}.{kind}"
    return send_file(os.path.join(store.job_dir(job_id), name), as_attachment=True, download_name=dl)


# ---------------- admin ----------------
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
    if request.method == "POST" and request.form.get("action") == "upload":
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
    tpl = None
    if os.path.exists(store.TEMPLATE_PATH):
        st = os.stat(store.TEMPLATE_PATH)
        from datetime import datetime
        tpl = {"size_kb": round(st.st_size / 1024),
               "mtime": datetime.fromtimestamp(st.st_mtime, store.TZ).strftime("%d/%m/%Y %H:%M")}
    jobs = list(reversed(store.all_jobs()))[:50]
    return render_template("admin.html", tpl=tpl, jobs=jobs, status_th=STATUS_TH)


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


WORKER_FILE_KINDS = ("template", "source", "result_docx", "result_pdf")


def worker_view(job):
    """Job JSON + local paths + token-protected download URLs for remote workers."""
    j = store.with_paths(job)
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
    j["urls"] = {k: url_for("worker_file", job_id=job["id"], kind=k, _external=True)
                 for k in WORKER_FILE_KINDS if job["files"].get(k)}
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
    j = store.claim_next()
    return jsonify({"job": worker_view(j) if j else None})


@app.get("/api/worker/jobs")
def worker_jobs():
    require_worker()
    st = request.args.get("status")
    jobs = [j for j in store.all_jobs() if not st or j["status"] == st]
    return jsonify({"jobs": [worker_view(j) for j in jobs]})


@app.get("/api/worker/<job_id>")
def worker_show(job_id):
    require_worker()
    return jsonify({"job": worker_view(load_or_404(job_id))})


@app.post("/api/worker/<job_id>/claim")
def worker_claim(job_id):
    require_worker()
    load_or_404(job_id)
    return jsonify({"job": worker_view(store.claim(job_id))})


@app.post("/api/worker/<job_id>/requeue")
def worker_requeue(job_id):
    require_worker()
    load_or_404(job_id)
    return jsonify({"job": worker_view(store.requeue(job_id))})


@app.get("/api/worker/<job_id>/file/<kind>")
def worker_file(job_id, kind):
    require_worker()
    j = load_or_404(job_id)
    if kind not in WORKER_FILE_KINDS:
        return jsonify({"error": f"unknown file kind: {kind}"}), 404
    if not j["files"].get(kind) or not os.path.isfile(os.path.join(store.job_dir(job_id), j["files"][kind])):
        msg = "no source file (job is from_scratch: use instructions)" if kind == "source" else f"no {kind} file"
        return jsonify({"error": msg, "kind": kind, "from_scratch": bool(j.get("from_scratch"))}), 404
    name = j["files"][kind]
    orig = j["files"].get(kind + "_original_name") or name
    return send_file(os.path.join(store.job_dir(job_id), name), as_attachment=True,
                     download_name=orig)


@app.post("/api/worker/<job_id>/complete")
def worker_complete(job_id):
    require_worker()
    load_or_404(job_id)
    data = request.form if request.form else (request.get_json(silent=True) or {})
    docx_f, pdf_f = request.files.get("docx"), request.files.get("pdf")
    docx_path, pdf_path = data.get("docx_path"), data.get("pdf_path")
    for p in (docx_path, pdf_path):
        if p and not os.path.isfile(p):
            return jsonify({"error": f"file not found on server: {p}"}), 400
    if not docx_f and not docx_path:
        return jsonify({"error": "multipart field 'docx' (or docx_path) required"}), 400
    if docx_f and not docx_f.filename.lower().endswith(".docx"):
        return jsonify({"error": "docx must be a .docx file"}), 400
    j = store.complete(job_id, docx_src=docx_path, pdf_src=pdf_path,
                       docx_writer=docx_f.save if docx_f else None,
                       pdf_writer=pdf_f.save if pdf_f else None)
    return jsonify({"job": worker_view(j)})


@app.post("/api/worker/<job_id>/fail")
def worker_fail(job_id):
    require_worker()
    load_or_404(job_id)
    data = request.form if request.form else (request.get_json(silent=True) or {})
    return jsonify({"job": worker_view(store.fail(job_id, data.get("message") or "เกิดข้อผิดพลาด"))})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "template": os.path.exists(store.TEMPLATE_PATH)})


if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 8080))
    print(f"Serving on http://0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port, threads=8, max_request_body_size=(2 * MAX_MB + 2) * 1024 * 1024)
