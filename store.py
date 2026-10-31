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
DEFAULT_MINUTES = 8.0
OPTIONS = ["ทำภาพประกอบเพิ่ม", "ทำใบงาน/ใบความรู้แนบท้าย", "แก้คำผิดและเนื้อหาที่ผิด"]
OPT_ILLUSTRATIONS = OPTIONS[0]
SLOW_FACTOR = 1.5  # from-scratch jobs or extra illustrations take longer (applied once)
TZ = timezone(timedelta(hours=7))

DEFAULT_TEMPLATE_SRC = os.path.join(BASE, "default_template", "main.docx")

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


def create_job(uploads, fields, note, plan_counter=None, instructions=None, options=None):
    """uploads: {"template": (filename, save_fn), "source": (filename, save_fn)}.
    save_fn(dest_path) writes the uploaded file. If no template upload is given,
    the admin default template (data/template/main.docx) is copied as a fallback."""
    job_id = new_job_id()
    d = job_dir(job_id)
    os.makedirs(d)
    files = {"source": None, "source_original_name": None,
             "template": None, "template_original_name": None,
             "template_is_default": False,
             "result_docx": None, "result_pdf": None}
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
    job = {
        "id": job_id,
        "status": "queued",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "fields": fields,
        "note": note,               # legacy name, same text as instructions
        "instructions": instructions if instructions is not None else note,
        "options": list(options or []),
        "from_scratch": not files["source"],
        "files": files,
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
    if job["plan_count"] > 1:
        job["status"] = "awaiting_choice"  # submitter must choose one plan vs all before queuing
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
        j["status"] = "queued"
        j["queued_at"] = now_iso()
        save(j)
        return j


def with_paths(job):
    d = job_dir(job["id"])
    j = dict(job)
    j["paths"] = {k: (os.path.join(d, v) if v else None)
                  for k, v in job["files"].items()
                  if k in ("source", "template", "result_docx", "result_pdf")}
    j["paths"]["job_dir"] = d
    return j


def claim_next():
    with lock():
        for j in all_jobs():
            if j["status"] == "queued":
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
        j["status"] = "processing"
        j["started_at"] = j["started_at"] or now_iso()
        save(j)
        return j


def complete(job_id, docx_src=None, pdf_src=None, docx_writer=None, pdf_writer=None):
    with lock():
        j = load(job_id)
        if not j:
            raise KeyError(job_id)
        d = job_dir(job_id)
        if docx_src or docx_writer:
            dest = os.path.join(d, "result.docx")
            docx_writer(dest) if docx_writer else shutil.copy2(docx_src, dest)
            j["files"]["result_docx"] = "result.docx"
        if pdf_src or pdf_writer:
            dest = os.path.join(d, "result.pdf")
            pdf_writer(dest) if pdf_writer else shutil.copy2(pdf_src, dest)
            j["files"]["result_pdf"] = "result.pdf"
        if not j["files"]["result_docx"]:
            raise ValueError("result docx required")
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
    info = {"id": j["id"], "status": j["status"], "created_at": j["created_at"],
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
            "has_docx": bool(j["files"]["result_docx"]),
            "has_pdf": bool(j["files"]["result_pdf"]),
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
