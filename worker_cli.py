#!/usr/bin/env python3
"""Worker CLI — ทำงานกับคิวโดยตรงบนดิสก์ (ไม่ต้องผ่าน HTTP)

  python3 worker_cli.py list [--all]          แสดงงาน (ค่าเริ่มต้น: queued/processing)
  python3 worker_cli.py claim [<id>]          รับงานเก่าสุดที่รอคิว (หรือระบุ id) -> JSON + paths
  python3 worker_cli.py show <id>
  python3 worker_cli.py complete <id> <docx> [pdf]
  python3 worker_cli.py fail <id> <ข้อความ>
  python3 worker_cli.py requeue <id>
  python3 worker_cli.py payments [--status payment_review]
  python3 worker_cli.py slip <id> [outpath]
  python3 worker_cli.py pay-ok <id> [--ref R] [--amount A] [--time T] [--payer N] [--payee N] [--note N]
  python3 worker_cli.py pay-reject <id> <เหตุผล>
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))



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
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        jobs = store.all_jobs()
        if "--all" not in args:
            jobs = [j for j in jobs if j["status"] in ("queued", "processing")]
        for j in jobs:
            f = j["fields"]
            print(f'{j["id"]}  {j["status"]:<10}  {j["created_at"]}  จำนวนแผน={j.get("plan_count") or 1}  ทำ={("แผนที่ " + str(j.get("plan_selected"))) if j.get("plan_mode") == "one" else "ทั้งหมด"}  แผนที่={f.get("plan_no") or "-"}  ผู้สอน={f.get("teacher") or "-"}  ฟอร์ม={j["files"].get("template_original_name") or "-"}  ข้อมูล={j["files"].get("source_original_name") or "-"}  {short_flags(j)}'.rstrip())
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
    if cmd == "payments":
        st = "payment_review"
        if "--status" in args:
            i = args.index("--status")
            if i + 1 < len(args):
                st = args[i + 1]
        jobs = [j for j in store.all_jobs() if j["status"] == st]
        for j in jobs:
            pay = j.get("payment") or {}
            f = j["fields"]
            print(f'{j["id"]}  {j["status"]:<16}  due={pay.get("amount_due")}  plans={pay.get("plan_count_billed")}  '
                  f'slip={pay.get("slip_file") or "-"}  ผู้สอน={f.get("teacher") or "-"}')
        if not jobs:
            print("(ไม่มีงาน)")
        return 0
    if cmd == "slip" and args:
        j = store.load(args[0])
        if not j:
            print("not found", file=sys.stderr); return 1
        pay = j.get("payment") or {}
        name = pay.get("slip_file") or (j.get("files") or {}).get("slip")
        if not name:
            print("no slip", file=sys.stderr); return 1
        src = os.path.join(store.job_dir(args[0]), name)
        outp = args[1] if len(args) > 1 else src
        if outp != src:
            import shutil
            os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
            shutil.copy2(src, outp)
        print(outp); return 0
    if cmd == "pay-ok" and args:
        jid = args[0]
        flags = {}
        i = 1
        while i < len(args):
            a = args[i]
            if a in ("--ref", "--amount", "--time", "--payer", "--payee", "--note") and i + 1 < len(args):
                flags[a[2:]] = args[i + 1]; i += 2
            else:
                i += 1
        j = store.approve_payment(
            jid, slip_ref=flags.get("ref"), amount=flags.get("amount"),
            transfer_time=flags.get("time"), payer_name=flags.get("payer"),
            payee_name=flags.get("payee"), note=flags.get("note"), by="worker")
        out(store.with_paths(j)); return 0
    if cmd == "pay-reject" and len(args) >= 2:
        out(store.reject_payment(args[0], " ".join(args[1:]), by="worker")); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyError as e:
        print(f"job not found: {e}", file=sys.stderr); sys.exit(1)
    except ValueError as e:
        print(str(e), file=sys.stderr); sys.exit(1)
