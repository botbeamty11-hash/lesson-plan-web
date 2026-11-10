#!/usr/bin/env python3
"""remote_worker.py — ไคลเอนต์ worker ระยะไกล (stdlib เท่านั้น) คุยกับเว็บแอปผ่าน HTTPS

ตั้งค่า env:
  LP_BASE_URL      เช่น https://lesson-plan-web.onrender.com
  LP_WORKER_TOKEN  โทเคนเดียวกับ WORKER_TOKEN ของเซิร์ฟเวอร์
  LP_WORK_DIR      (ไม่บังคับ) โฟลเดอร์เก็บไฟล์ที่ดาวน์โหลด ค่าเริ่มต้น ./lp_jobs

คำสั่ง:
  python3 remote_worker.py list [--all] [--service ID]   งานที่ยังไม่เสร็จ (queued/processing) หรือทั้งหมด
  python3 remote_worker.py claim [<id>] [--service ID]   รับงานเก่าสุดที่ queued (หรือระบุ id) + ดาวน์โหลดไฟล์ -> JSON
  python3 remote_worker.py show <id>
  python3 remote_worker.py complete <id> <file> [file...]  อัปโหลดผล (docx/pdf หรือหลายไฟล์)
  python3 remote_worker.py fail <id> <ข้อความ>
  python3 remote_worker.py requeue <id>
  python3 remote_worker.py health
  python3 remote_worker.py payments [--status payment_review]
  python3 remote_worker.py slip <id> [outpath]   ดาวน์โหลดสลิป
  python3 remote_worker.py pay-ok <id> [--ref R] [--amount A] [--time T] [--payer N] [--payee N] [--note N]
  python3 remote_worker.py pay-reject <id> <เหตุผล>
"""
import json, mimetypes, os, sys, time, urllib.error, urllib.request, uuid

BASE = os.environ.get("LP_BASE_URL", "").rstrip("/")
TOKEN = os.environ.get("LP_WORKER_TOKEN", "")
WORK_DIR = os.environ.get("LP_WORK_DIR", os.path.join(os.getcwd(), "lp_jobs"))
TIMEOUT = 180  # Render free instances may need ~1 min to wake up


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def request(method, path_or_url, data=None, headers=None, raw=False, retries=3, soft404=False):
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    h = {"Authorization": f"Bearer {TOKEN}", "User-Agent": "lp-remote-worker/1"}
    h.update(headers or {})
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read()
                return body if raw else json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if soft404 and e.code == 404:
                return None
            if e.code in (502, 503, 504) and attempt < retries - 1:
                time.sleep(10); continue
            die(f"HTTP {e.code} {method} {url}: {e.read().decode('utf-8', 'replace')[:500]}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(10); continue
            die(f"connection error {method} {url}: {e}")


def multipart(fields, files):
    boundary = "----lp" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode(), str(v).encode(), b"\r\n"]
    for k, path in files.items():
        name = os.path.basename(path)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            content = f.read()
        out += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{name}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n".encode(), content, b"\r\n"]
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def pr(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def download_inputs(job):
    d = os.path.join(WORK_DIR, job["id"])
    os.makedirs(d, exist_ok=True)
    local = {}
    # template (always at most one)
    url = job.get("urls", {}).get("template")
    name = (job.get("files") or {}).get("template")
    if url and name:
        body = request("GET", url, raw=True, soft404=True)
        if body is None:
            print("warning: template file not available on server, skipped", file=sys.stderr)
        else:
            dest = os.path.join(d, "template" + os.path.splitext(name)[1])
            with open(dest, "wb") as f:
                f.write(body)
            local["template"] = dest
    # source file(s): files.sources[] for new jobs; files.source for older single-file jobs
    sources = list((job.get("files") or {}).get("sources") or [])
    if not sources and (job.get("files") or {}).get("source"):
        sources = [{"stored": job["files"]["source"],
                    "original_name": (job.get("files") or {}).get("source_original_name"),
                    "index": 0}]
    local_sources = []
    for i, s in enumerate(sources):
        url = (job.get("urls") or {}).get("source" if i == 0 else f"source_{i}")
        stored = (s or {}).get("stored") if isinstance(s, dict) else None
        if not url or not stored:
            continue
        body = request("GET", url, raw=True, soft404=True)
        if body is None:
            print(f"warning: source file {stored} not available on server, skipped", file=sys.stderr)
            continue
        dest = os.path.join(d, stored)
        with open(dest, "wb") as f:
            f.write(body)
        entry = {"path": dest, "original_name": (s or {}).get("original_name") or stored, "index": i}
        local_sources.append(entry)
        if i == 0:
            local["source"] = dest  # backward compatible single path
    local["sources"] = local_sources
    # generic service uploads
    uploads = (job.get("files") or {}).get("uploads") or []
    local_uploads = []
    for i, u in enumerate(uploads):
        url = (job.get("urls") or {}).get(f"upload_{i}")
        if not url:
            continue
        body = request("GET", url, raw=True, soft404=True)
        if body is None:
            continue
        dest = os.path.join(d, u.get("stored") or f"upload_{i}")
        with open(dest, "wb") as f:
            f.write(body)
        local_uploads.append({"field": u.get("field"), "path": dest, "original_name": u.get("original_name")})
    local["uploads"] = local_uploads
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return d, local


def take_flag(args, name):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            val = args[i + 1]
            del args[i:i + 2]
            return val
        del args[i]
    return None



def short_flags(j):
    """Compact markers for list output: [ไม่มีไฟล์ข้อมูล] [ภาพ] [ใบงาน] [แก้คำ] [คำสั่ง: ...]"""
    opts = j.get("options") or []
    fl = []
    sid = j.get("service_id") or "lesson_plan"
    if sid != "lesson_plan": fl.append(f"[{sid}]")
    if j.get("from_scratch"): fl.append("[ไม่มีไฟล์ข้อมูล]")
    for full, short in (("ทำภาพประกอบเพิ่ม", "ภาพ"), ("ทำใบงาน/ใบความรู้แนบท้าย", "ใบงาน"),
                        ("แก้คำผิดและเนื้อหาที่ผิด", "แก้คำ")):
        if full in opts: fl.append(f"[{short}]")
    ins = (j.get("instructions") or j.get("note") or "").replace("\n", " ").strip()
    if ins: fl.append("[คำสั่ง: " + (ins[:40] + "…" if len(ins) > 40 else ins) + "]")
    return " ".join(fl)

def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); return 0
    if not BASE or not TOKEN:
        die("ต้องตั้งค่า LP_BASE_URL และ LP_WORKER_TOKEN")
    cmd, args = argv[0], list(argv[1:])
    service = take_flag(args, "--service")
    if cmd == "health":
        pr(request("GET", "/healthz")); return 0
    if cmd == "list":
        q = "/api/worker/jobs"
        params = []
        if service:
            params.append("service=" + service)
        if params:
            q += "?" + "&".join(params)
        jobs = request("GET", q)["jobs"]
        if "--all" not in args:
            jobs = [j for j in jobs if j["status"] in ("queued", "processing")]
        for j in jobs:
            f = j.get("fields") or {}
            sid = j.get("service_id") or "lesson_plan"
            sname = j.get("service_name") or sid
            teacher = f.get("teacher") or (j.get("inputs") or {}).get("teacher_name") or (j.get("inputs") or {}).get("name") or "-"
            print(f'{j["id"]}  {j["status"]:<10}  {j.get("created_at") or "-"}  svc={sname}  '
                  f'ผู้สอน={teacher}  {short_flags(j)}'.rstrip())
        if not jobs:
            print("(ไม่มีงาน)")
        return 0
    if cmd == "claim":
        if args and not args[0].startswith("--"):
            job = request("POST", f"/api/worker/{args[0]}/claim", data=b"")["job"]
        else:
            q = "/api/worker/next"
            if service:
                q += "?service=" + service
            job = request("GET", q)["job"]
        if not job:
            print("null"); return 1
        d, local = download_inputs(job)
        pr({"id": job["id"], "status": job["status"],
            "service_id": job.get("service_id") or "lesson_plan",
            "service_name": job.get("service_name") or "",
            "inputs": job.get("inputs") or {},
            "fields": job.get("fields") or {}, "note": job.get("note") or "",
            "plan_count": job.get("plan_count") or 1, "plan_numbers": job.get("plan_numbers") or [],
            "plan_mode": job.get("plan_mode") or "all", "plan_selected": job.get("plan_selected"),
            "effective_plan_count": job.get("effective_plan_count") or 1,
            "plan_choice_th": job.get("plan_choice_th") or "",
            "from_scratch": bool(job.get("from_scratch")),
            "instructions": job.get("instructions") or job.get("note") or "",
            "options": job.get("options") or [], "eta_factor": job.get("eta_factor") or 1.0,
            "original_names": {"template": (job.get("files") or {}).get("template_original_name"),
                               "source": (job.get("files") or {}).get("source_original_name"),
                               "sources": [((s or {}).get("original_name") if isinstance(s, dict) else s)
                                           for s in ((job.get("files") or {}).get("sources") or [])]
                                          or ([ (job.get("files") or {}).get("source_original_name") ]
                                              if (job.get("files") or {}).get("source") else [])},
            "local_dir": d, "local_paths": local}); return 0
    if cmd == "show" and args:
        pr(request("GET", f"/api/worker/{args[0]}")["job"]); return 0
    if cmd == "complete" and len(args) >= 2:
        jid = args[0]
        paths = args[1:]
        for p in paths:
            if not os.path.isfile(p):
                die(f"file not found: {p}")
        files = {}
        # classic: docx [pdf]
        if (len(paths) <= 2 and paths[0].lower().endswith(".docx")
                and (len(paths) == 1 or paths[1].lower().endswith(".pdf"))):
            files["docx"] = paths[0]
            if len(paths) > 1:
                files["pdf"] = paths[1]
        else:
            used_docx = used_pdf = False
            ri = 0
            for p in paths:
                ext = os.path.splitext(p)[1].lower()
                if ext == ".docx" and not used_docx:
                    files["docx"] = p; used_docx = True
                elif ext == ".pdf" and not used_pdf:
                    files["pdf"] = p; used_pdf = True
                else:
                    files[f"result_{ri}"] = p
                    ri += 1
        body, ctype = multipart({}, files)
        j = request("POST", f"/api/worker/{jid}/complete", data=body, headers={"Content-Type": ctype})["job"]
        pr({"id": j["id"], "status": j["status"], "page": (j.get("urls") or {}).get("page"),
            "results": j.get("results") or [],
            "has_pdf": bool((j.get("files") or {}).get("result_pdf"))}); return 0
    if cmd == "fail" and len(args) >= 2:
        j = request("POST", f"/api/worker/{args[0]}/fail", data=json.dumps({"message": " ".join(args[1:])}).encode(),
                    headers={"Content-Type": "application/json"})["job"]
        pr({"id": j["id"], "status": j["status"], "error": j["error"]}); return 0
    if cmd == "requeue" and args:
        j = request("POST", f"/api/worker/{args[0]}/requeue", data=b"")["job"]
        pr({"id": j["id"], "status": j["status"]}); return 0
    if cmd == "payments":
        st = "payment_review"
        if "--status" in args:
            i = args.index("--status")
            if i + 1 < len(args):
                st = args[i + 1]
        data = request("GET", f"/api/worker/payments?status={st}")
        jobs = data.get("jobs") or []
        settings = data.get("settings") or {}
        print(f"# payee={settings.get('payee_name') or '-'}  price/plan={settings.get('price_per_plan')}  "
              f"promptpay_id={settings.get('promptpay_id') or '(empty)'}  count={len(jobs)}")
        for j in jobs:
            pay = j.get("payment") or {}
            f = j.get("fields") or {}
            print(f'{j["id"]}  {j["status"]:<16}  due={pay.get("amount_due")}  plans={pay.get("plan_count_billed")}  '
                  f'req={pay.get("requested_at") or "-"}  slip={pay.get("slip_file") or "-"}  '
                  f'ผู้สอน={f.get("teacher") or "-"}  ref={pay.get("slip_ref") or "-"}')
        if not jobs:
            print("(ไม่มีงานรอตรวจสลิป)" if st == "payment_review" else "(ไม่มีงาน)")
        return 0
    if cmd == "slip" and args:
        jid = args[0]
        out = args[1] if len(args) > 1 else os.path.join(WORK_DIR, jid, "slip.bin")
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        # discover extension via Content-Disposition is hard with urllib; fetch job first
        job = request("GET", f"/api/worker/{jid}")["job"]
        pay = job.get("payment") or {}
        name = pay.get("slip_file") or (job.get("files") or {}).get("slip")
        if not name:
            die("no slip on this job")
        url = (job.get("urls") or {}).get("slip") or f"/api/worker/{jid}/file/slip"
        body = request("GET", url, raw=True)
        # fix extension from server filename
        if out.endswith("slip.bin"):
            out = os.path.join(WORK_DIR, jid, name)
            os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(body)
        print(out)
        return 0
    if cmd == "pay-ok" and args:
        jid = args[0]
        flags = {}
        i = 1
        while i < len(args):
            a = args[i]
            if a in ("--ref", "--amount", "--time", "--payer", "--payee", "--note") and i + 1 < len(args):
                flags[a[2:]] = args[i + 1]
                i += 2
            else:
                i += 1
        payload = {
            "slip_ref": flags.get("ref"),
            "amount": flags.get("amount"),
            "transfer_time": flags.get("time"),
            "payer_name": flags.get("payer"),
            "payee_name": flags.get("payee"),
            "note": flags.get("note"),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        j = request("POST", f"/api/worker/{jid}/pay-ok",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"})["job"]
        pay = j.get("payment") or {}
        pr({"id": j["id"], "status": j["status"], "slip_ref": pay.get("slip_ref"),
            "amount_due": pay.get("amount_due"), "verified_at": pay.get("verified_at")})
        return 0
    if cmd == "pay-reject" and len(args) >= 2:
        j = request("POST", f"/api/worker/{args[0]}/pay-reject",
                    data=json.dumps({"reason": " ".join(args[1:])}).encode(),
                    headers={"Content-Type": "application/json"})["job"]
        pay = j.get("payment") or {}
        pr({"id": j["id"], "status": j["status"], "reject_reason": pay.get("reject_reason")})
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
