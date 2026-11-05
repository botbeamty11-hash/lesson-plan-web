# ระบบส่งข้อมูลจัดทำแผนการจัดการเรียนรู้ (lp-web)

เว็บแอป Flask (UI ภาษาไทย) รับไฟล์ .doc/.docx/.pdf ≤ 20MB ต่อไฟล์:
1. ฟอร์มแผนการสอนของโรงเรียน (template, บังคับ) → เก็บเป็น `template.<ext>`
2. ไฟล์ข้อมูล (เช่น แผนจาก พว., ไม่บังคับ) → เก็บเป็น `source.<ext>` — ถ้าไม่แนบ ต้องพิมพ์คำสั่งเพิ่มเติม (≥10 ตัวอักษร: วิชา/ชั้น/เรื่อง) และงานจะมี `from_scratch: true`

ช่อง "คำสั่งเพิ่มเติมถึงผู้จัดทำ" เก็บใน `instructions` (และ `note` เพื่อความเข้ากันได้) ตัวเลือกด่วนเก็บใน `options` (รายการข้อความไทย)
ETA = จำนวนแผน × เวลาเฉลี่ยต่อแผน × 1.5 (ถ้า from_scratch หรือเลือก "ทำภาพประกอบเพิ่ม" — คูณครั้งเดียว)
ช่องรายละเอียดทั้งหมดไม่บังคับ (ช่องว่าง = เว้นว่างไว้ในฟอร์ม) วันที่สอนเก็บเป็น teach_day / teach_month (ชื่อเดือนไทย) / teach_year (พ.ศ.)
worker ภายนอก (ผู้ช่วย AI) ดึงงานไปจัดทำ แล้วส่งผลลัพธ์กลับ

## การรัน (เครื่อง local)
    ./start.sh          # gunicorn เบื้องหลังที่พอร์ต $PORT (ค่าเริ่มต้น 8080) log: data/server.log
    ./start.sh stop     # หยุด
    ./start.sh fg       # รันแบบ foreground

ค่าตั้งค่าอ่านจาก env vars (เครื่อง local โหลดจาก `.env` ซึ่งไม่ถูก commit). ถ้าไม่ตั้งค่า ระบบปิดส่วนนั้นอย่างปลอดภัย: ADMIN_PASSWORD (<8 ตัว) → ปิดการเข้า /admin, WORKER_TOKEN (<16 ตัว) → worker API ตอบ 401, SECRET_KEY → สุ่มใหม่ทุกครั้งที่บูต
| ตัวแปร | ความหมาย |
|---|---|
| ADMIN_PASSWORD | รหัสผ่านหน้า /admin |
| WORKER_TOKEN | โทเคนสำหรับ Worker API (`Authorization: Bearer <token>` หรือ `X-Worker-Token`) |
| SECRET_KEY | คีย์ session ของ Flask |
| PORT | พอร์ต (8080) |
| WEBHOOK_URL | (ไม่บังคับ) URL ที่จะถูก POST `{"job_id": "..."}` เมื่อมีงานใหม่ |
| LP_DATA_DIR | (ไม่บังคับ) โฟลเดอร์ข้อมูล ค่าเริ่มต้น `./data` |

## หน้าเว็บ
- `/` ส่งงาน · `/job/<id>/choose` เลือกจำนวนแผน · `/job/<id>/pay` ชำระ PromptPay + อัปโหลดสลิป · `/job/<id>` สถานะ (poll ทุก 5 วิ) · `/admin` งาน + การเงิน + ตั้งค่า QR/ราคา
- งานเข้าคิว `queued` **หลังตรวจสลิปผ่านเท่านั้น** · ราคา = ราคาต่อแผน (ค่าเริ่มต้น 10) × จำนวนแผนที่ครูเลือก
- `GET /api/job/<id>` สถานะ JSON: status, queue_position, jobs_ahead, eta_minutes, avg_minutes, has_docx, has_pdf
- `GET /job/<id>/download/docx|pdf`

ETA = (จำนวนงานข้างหน้า + 1) × เวลาเฉลี่ย (เฉลี่ยจากงานที่เสร็จจริง 20 งานล่าสุดที่ใช้เวลา ≥ 1 นาที; ถ้าไม่มี = 8 นาที)
งานที่กำลังทำ: ETA = เวลาเฉลี่ย − เวลาที่ใช้ไปแล้ว

## โครงสร้างข้อมูล
    data/template/main.docx           แม่แบบสำรองภายใน (ใช้เฉพาะงานที่ไม่มีฟอร์มแนบ; template_is_default=true)
    data/jobs/<id>/job.json           ข้อมูลงาน (status: awaiting_choice|awaiting_payment|payment_review|payment_rejected|queued|processing|done|failed)
    data/jobs/<id>/slip.<ext>         สลิป PromptPay ที่ครูอัปโหลด
    data/settings.json                ตั้งค่าราคา / ชื่อผู้รับ / PromptPay ID
    data/promptpay_qr.png             รูป QR ที่แอดมินอัปโหลด
    data/jobs/<id>/source.<ext>       ไฟล์ต้นฉบับที่อัปโหลด
    data/jobs/<id>/template.<ext>     ฟอร์มโรงเรียนที่ผู้ใช้อัปโหลด (paths.template)
    data/jobs/<id>/result.docx/.pdf   ผลลัพธ์

## Worker CLI (ทำงานกับดิสก์โดยตรง ไม่ต้องใช้ HTTP)
    python3 worker_cli.py list [--all]
    python3 worker_cli.py claim [<id>]            # รับงานเก่าสุด -> JSON พร้อม paths.source / paths.template
    python3 worker_cli.py show <id>
    python3 worker_cli.py complete <id> <result.docx> [result.pdf]
    python3 worker_cli.py fail <id> "ข้อความ"
    python3 worker_cli.py requeue <id>
(ใช้ `.venv/bin/python` หรือ python3 ระบบก็ได้ — CLI ใช้แค่ไลบรารีมาตรฐาน)

## Deploy บน Render (Python web service, free plan)
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
  (ใช้ worker เดียว เพื่อให้การล็อกคิวบนดิสก์สอดคล้องกัน)
- Health check path: `/healthz`
- Env vars: `ADMIN_PASSWORD`, `WORKER_TOKEN`, `SECRET_KEY` (บังคับ), `WEBHOOK_URL` (ไม่บังคับ)
- มี `render.yaml` (Blueprint) ให้ด้วย
- ข้อควรรู้ของ free plan: ดิสก์ชั่วคราว **ไม่มี persistent disk ใน render.yaml** (งาน/สลิป/รูป QR/settings.json หายเมื่อ redeploy/restart) และหลับเมื่อว่าง ~15 นาที
  (ปลุกครั้งแรก ~1 นาที) → หน้าเสร็จแล้วจะเตือนให้ดาวน์โหลดทันที; `default_template/main.docx`
  จะถูกคัดลอกไปที่ data/template/ อัตโนมัติตอนบูต

## Remote worker (stdlib เท่านั้น) — สำหรับผู้ช่วย AI บนเครื่องอื่น
    export LP_BASE_URL=https://<app>.onrender.com LP_WORKER_TOKEN=<token>   # LP_WORK_DIR=./lp_jobs (ไม่บังคับ)
    python3 remote_worker.py list [--all]
    python3 remote_worker.py claim [<id>]     # ดาวน์โหลดฟอร์ม+ไฟล์ข้อมูลไป $LP_WORK_DIR/<id>/ แล้วพิมพ์ JSON (fields, local_paths)
    python3 remote_worker.py show <id>
    python3 remote_worker.py complete <id> <result.docx> [result.pdf]
    python3 remote_worker.py fail <id> "ข้อความ"
    python3 remote_worker.py requeue <id>
    python3 remote_worker.py health
    python3 remote_worker.py payments [--status payment_review]
    python3 remote_worker.py slip <id> [outfile]
    python3 remote_worker.py pay-ok <id> --ref R --amount A --time T --payer N --payee N --note N
    python3 remote_worker.py pay-reject <id> "เหตุผล"

## Worker HTTP API (ต้องมีโทเคน `Authorization: Bearer <WORKER_TOKEN>`)
| Method | Path | หมายเหตุ |
|---|---|---|
| GET | /api/worker/jobs[?status=queued] | รายการงาน (มี urls) |
| GET | /api/worker/next | รับงานเก่าสุด → status=processing, คืน job + urls.template/urls.source |
| GET | /api/worker/<id> | ดูงาน |
| POST | /api/worker/<id>/claim | รับงานที่ระบุ |
| POST | /api/worker/<id>/requeue | คืนเข้าคิว |
| GET | /api/worker/<id>/file/<template\|source\|result_docx\|result_pdf> | ดาวน์โหลดไฟล์ของงาน |
| POST | /api/worker/<id>/complete | multipart `docx` (บังคับ) + `pdf` (ไม่บังคับ) |
| POST | /api/worker/<id>/fail | form หรือ JSON `message` |
| GET | /api/worker/payments[?status=payment_review] | งานรอตรวจสลิป + settings สรุป |
| GET | /api/worker/<id>/file/slip | ดาวน์โหลดสลิป |
| POST | /api/worker/<id>/pay-ok | JSON: slip_ref, amount, transfer_time, payer_name, payee_name, note → queued |
| POST | /api/worker/<id>/pay-reject | JSON/form: reason |
| GET | /healthz | ไม่ต้องใช้โทเคน |

ตัวอย่าง curl:
    curl -H "Authorization: Bearer $WORKER_TOKEN" http://localhost:8080/api/worker/next
    curl -H "Authorization: Bearer $WORKER_TOKEN" http://localhost:8080/api/worker/jobs
    curl -H "Authorization: Bearer $WORKER_TOKEN" -F docx=@out.docx -F pdf=@out.pdf http://localhost:8080/api/worker/<id>/complete
    curl -H "Authorization: Bearer $WORKER_TOKEN" -F docx_path=/abs/out.docx http://localhost:8080/api/worker/<id>/complete
    curl -H "Authorization: Bearer $WORKER_TOKEN" -F message="เหตุผล" http://localhost:8080/api/worker/<id>/fail

## เปิดสู่อินเทอร์เน็ต (ถ้าเครือข่ายอนุญาต)
    ~/.local/bin/cloudflared tunnel --no-autoupdate --protocol http2 --url http://localhost:8080
หมายเหตุ: บนเครื่อง box นี้ใช้ไม่ได้ เพราะ egress ผ่าน proxy (198.18.0.1) ที่ปิดการเชื่อมต่อ TLS ไปยัง Cloudflare edge (พอร์ต 7844) และ SSH
