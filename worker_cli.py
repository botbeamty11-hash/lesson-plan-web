#!/usr/bin/env python3
"""Worker CLI — ทำงานกับคิวโดยตรงบนดิสก์ (ไม่ต้องผ่าน HTTP)

  python3 worker_cli.py list [--all]          แสดงงาน (ค่าเริ่มต้น: เฉพาะที่ยังไม่เสร็จ)
  python3 worker_cli.py claim [<id>]          รับงานเก่าสุดที่รอคิว (หรือระบุ id) -> พิมพ์ JSON พร้อม path ไฟล์
  python3 worker_cli.py show <id>             แสดง JSON ของงาน
  python3 worker_cli.py complete <id> <docx> [pdf]
  python3 worker_cli.py fail <id> <ข้อความ>
  python3 worker_cli.py requeue <id>          ส่งงานกลับเข้าคิว
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        jobs = store.all_jobs()
        if "--all" not in args:
            jobs = [j for j in jobs if j["status"] in ("queued", "processing")]
        for j in jobs:
            f = j["fields"]
            print(f'{j["id"]}  {j["status"]:<10}  {j["created_at"]}  จำนวนแผน={j.get("plan_count") or 1}  ทำ={("แผนที่ " + str(j.get("plan_selected"))) if j.get("plan_mode") == "one" else "ทั้งหมด"}  แผนที่={f.get("plan_no") or "-"}  ผู้สอน={f.get("teacher") or "-"}  ฟอร์ม={j["files"].get("template_original_name") or "-"}  ข้อมูล={j["files"]["source_original_name"]}')
        if not jobs:
            print("(ไม่มีงาน)")
        return 0
    if cmd == "claim":
        j = store.claim(args[0]) if args else store.claim_next()
        if not j:
            print("null"); return 1
        out(store.with_paths(j)); return 0
    if cmd == "show" and args:
        j = store.load(args[0])
        if not j:
            print("not found", file=sys.stderr); return 1
        out(store.with_paths(j)); return 0
    if cmd == "complete" and len(args) >= 2:
        for p in args[1:3]:
            if not os.path.isfile(p):
                print(f"file not found: {p}", file=sys.stderr); return 1
        j = store.complete(args[0], docx_src=args[1], pdf_src=args[2] if len(args) > 2 else None)
        out(store.with_paths(j)); return 0
    if cmd == "fail" and len(args) >= 2:
        out(store.fail(args[0], " ".join(args[1:]))); return 0
    if cmd == "requeue" and args:
        out(store.requeue(args[0])); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyError as e:
        print(f"job not found: {e}", file=sys.stderr); sys.exit(1)
