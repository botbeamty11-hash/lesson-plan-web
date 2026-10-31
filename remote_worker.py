#!/usr/bin/env python3
"""remote_worker.py — ไคลเอนต์ worker ระยะไกล (stdlib เท่านั้น) คุยกับเว็บแอปผ่าน HTTPS

ตั้งค่า env:
  LP_BASE_URL      เช่น https://lesson-plan-web.onrender.com
  LP_WORKER_TOKEN  โทเคนเดียวกับ WORKER_TOKEN ของเซิร์ฟเวอร์
  LP_WORK_DIR      (ไม่บังคับ) โฟลเดอร์เก็บไฟล์ที่ดาวน์โหลด ค่าเริ่มต้น ./lp_jobs

คำสั่ง:
  python3 remote_worker.py list [--all]          งานที่ยังไม่เสร็จ (หรือทั้งหมด)
  python3 remote_worker.py claim [<id>]          รับงานเก่าสุด (หรือระบุ id) + ดาวน์โหลดฟอร์มและไฟล์ข้อมูล -> JSON
  python3 remote_worker.py show <id>
  python3 remote_worker.py complete <id> <result.docx> [result.pdf]
  python3 remote_worker.py fail <id> <ข้อความ>
  python3 remote_worker.py requeue <id>
  python3 remote_worker.py health
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
    for kind in ("template", "source"):
        url = job.get("urls", {}).get(kind)
        name = (job.get("files") or {}).get(kind)
        if not url or not name:
            continue  # e.g. from_scratch jobs have no source file
        body = request("GET", url, raw=True, soft404=True)
        if body is None:
            print(f"warning: {kind} file not available on server, skipped", file=sys.stderr)
            continue
        dest = os.path.join(d, kind + os.path.splitext(name)[1])
        with open(dest, "wb") as f:
            f.write(body)
        local[kind] = dest
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return d, local



def short_flags(j):
    """Compact markers for list output: [ไม่มีไฟล์ข้อมูล] [ภาพ] [ใบงาน] [แก้คำ] [คำสั่ง: ...]"""
    opts = j.get("options") or []
    fl = []
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
    cmd, args = argv[0], argv[1:]
    if cmd == "health":
        pr(request("GET", "/healthz")); return 0
    if cmd == "list":
        jobs = request("GET", "/api/worker/jobs")["jobs"]
        if "--all" not in args:
            jobs = [j for j in jobs if j["status"] in ("queued", "processing")]
        for j in jobs:
            f = j["fields"]
            print(f'{j["id"]}  {j["status"]:<10}  {j["created_at"]}  จำนวนแผน={j.get("plan_count") or 1}  '
                  f'ทำ={("แผนที่ " + str(j.get("plan_selected"))) if j.get("plan_mode") == "one" else "ทั้งหมด"}  แผนที่={f.get("plan_no") or "-"}  '
                  f'ผู้สอน={f.get("teacher") or "-"}  ฟอร์ม={j["files"].get("template_original_name") or "-"}  '
                  f'ข้อมูล={j["files"].get("source_original_name") or "-"}  {short_flags(j)}'.rstrip())
        if not jobs:
            print("(ไม่มีงาน)")
        return 0
    if cmd == "claim":
        job = (request("POST", f"/api/worker/{args[0]}/claim", data=b"") if args
               else request("GET", "/api/worker/next"))["job"]
        if not job:
            print("null"); return 1
        d, local = download_inputs(job)
        pr({"id": job["id"], "status": job["status"], "fields": job["fields"], "note": job.get("note") or "",
            "plan_count": job.get("plan_count") or 1, "plan_numbers": job.get("plan_numbers") or [],
            "plan_mode": job.get("plan_mode") or "all", "plan_selected": job.get("plan_selected"),
            "effective_plan_count": job.get("effective_plan_count") or 1,
            "plan_choice_th": job.get("plan_choice_th") or "",
            "from_scratch": bool(job.get("from_scratch")),
            "instructions": job.get("instructions") or job.get("note") or "",
            "options": job.get("options") or [], "eta_factor": job.get("eta_factor") or 1.0,
            "original_names": {"template": job["files"].get("template_original_name"),
                               "source": job["files"].get("source_original_name")},
            "local_dir": d, "local_paths": local}); return 0
    if cmd == "show" and args:
        pr(request("GET", f"/api/worker/{args[0]}")["job"]); return 0
    if cmd == "complete" and len(args) >= 2:
        files = {"docx": args[1]}
        if len(args) > 2:
            files["pdf"] = args[2]
        for p in files.values():
            if not os.path.isfile(p):
                die(f"file not found: {p}")
        body, ctype = multipart({}, files)
        j = request("POST", f"/api/worker/{args[0]}/complete", data=body, headers={"Content-Type": ctype})["job"]
        pr({"id": j["id"], "status": j["status"], "page": j["urls"].get("page"),
            "has_pdf": bool(j["files"].get("result_pdf"))}); return 0
    if cmd == "fail" and len(args) >= 2:
        j = request("POST", f"/api/worker/{args[0]}/fail", data=json.dumps({"message": " ".join(args[1:])}).encode(),
                    headers={"Content-Type": "application/json"})["job"]
        pr({"id": j["id"], "status": j["status"], "error": j["error"]}); return 0
    if cmd == "requeue" and args:
        j = request("POST", f"/api/worker/{args[0]}/requeue", data=b"")["job"]
        pr({"id": j["id"], "status": j["status"]}); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
