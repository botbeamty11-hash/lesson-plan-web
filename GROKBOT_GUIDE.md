# คู่มือส่งต่องาน: ระบบเว็บจัดทำแผนการสอน (lesson-plan-web)

> สำหรับบอท/ผู้ดูแลคนใหม่ที่จะรับช่วงดูแลเว็บและประมวลผลคิวงาน
> ปรับปรุงล่าสุด: 5 พ.ย. 2569 (เวลาไทย) — ร้านบริการครูหลายบริการ (ยังไม่เก็บเงินบริการใหม่) + PromptPay สำหรับแผนการสอน

---

## 1. ภาพรวมระบบ

- **เว็บแอป:** https://lesson-plan-web.onrender.com
- **เทคโนโลยี:** Flask + gunicorn (worker เดียว, 4 threads) โฮสต์บน **Render free plan (Singapore)**
  - Service ID: `srv-dbic8vuc6qcc73d8nbvg`
  - **ดิสก์ชั่วคราว (ไม่มี persistent disk ใน render.yaml):** ทุกครั้งที่ deploy/restart งาน ไฟล์สลิป รูป QR และการตั้งค่าใน `data/` บนเว็บ **หายหมด** — ควรอัปโหลด QR ใหม่หลัง redeploy หรือเพิ่ม Render Disk ภายหลัง
  - หลับเมื่อว่าง ~15 นาที ปลุกครั้งแรกใช้เวลา ~1 นาที (สคริปต์ worker retry ให้เอง)
- **โค้ด:** `/workspace/lp-web` · Repo: https://github.com/botbeamty11-hash/lesson-plan-web
  - GitHub auto-deploy **ไม่ทำงาน** → ต้อง deploy เองผ่าน Render และทำ **เฉพาะตอนคิวว่าง** เท่านั้น

### สิ่งที่ครูส่งเข้ามา
1. **ไฟล์ที่ 1 = ฟอร์มแผนการสอนของโรงเรียน** (บังคับ) → เก็บเป็น `template.<ext>`
2. **ไฟล์ที่ 2 = ไฟล์ข้อมูล** (ไม่บังคับ เช่น แผนจากสำนักพิมพ์ .doc/.docx/.pdf) → เก็บเป็น `source.<ext>`
   - ถ้าไม่แนบ งานจะเป็น `from_scratch: true` และต้องพิมพ์คำสั่งเพิ่มเติม (วิชา/ชั้น/เรื่อง)
3. **ช่องคำสั่งเพิ่มเติม** (`instructions` และ `note`)
4. **ตัวเลือกด่วน 3 ข้อ** (`options`): ทำภาพประกอบเพิ่ม · ทำใบงาน/ใบความรู้ · แก้ไขข้อผิดพลาด
5. **ช่องรายละเอียด (ไม่บังคับ):** ชื่อครู, วันที่สอน (`teach_day` / `teach_month` ชื่อเดือนไทย / `teach_year` พ.ศ.), แผนที่, หน่วย, ภาคเรียน, ปีการศึกษา — ช่องที่เว้นว่าง ให้เว้นว่างในฟอร์มด้วย
6. **จำนวนแผน:** `plan_mode` = `one` (ทำเฉพาะแผนใน `plan_selected`) หรือ `all` (ทำทุกแผน N แผน รวมเป็น .docx เดียว)
7. **ชำระเงิน PromptPay (เฉพาะบริการแผนการจัดการเรียนรู้):** หลังเลือกแผน (หรือส่งงานแผนเดียว) ครูต้องสแกน QR + อัปโหลดสลิป — **งานจะเข้าคิว `queued` หลังตรวจสลิปผ่านเท่านั้น**
   - ราคา = (ราคาต่อแผน จากตั้งค่าแอดมิน, ค่าเริ่มต้น 10 บาท) × จำนวนแผนที่ครูเลือก
   - สถานะ: `awaiting_payment` → `payment_review` (อัปโหลดสลิปแล้ว) → `queued` หรือ `payment_rejected` (อัปโหลดใหม่ได้)

### ร้านบริการครูหลายบริการ (ใหม่)
หน้าแรกแสดง **กลุ่มบริการไม่เกิน 5 ใบ** → กดกลุ่มแล้วเห็นรายการบริการสั้น ๆ → กรอกฟอร์มเฉพาะช่องจำเป็น (ช่องอื่นอยู่ใน "ตัวเลือกเพิ่มเติม")

| กลุ่ม | ตัวอย่างบริการ | ทำโดย | เก็บเงินตอนนี้ |
|---|---|---|---|
| แผนการสอน | แผนการจัดการเรียนรู้ (`lesson_plan`) | worker | **ใช่** (PromptPay เดิม) |
| สื่อการสอน | สไลด์ / ใบงาน / ข้อสอบ / บัตรคำ / แผนภาพ | worker | ไม่ (เข้าคิวตรง) |
| แปลงและจัดการไฟล์ | รวม/แยก/บีบอัด PDF, OCR, แปลงไฟล์ | **อัตโนมัติ** (รวม/แยก/บีบอัด) หรือ worker | ไม่ |
| งานเอกสารครู | บันทึกประชุม, รายงาน, หนังสือราชการ, … | worker | ไม่ |
| งานวัดผลและผู้ปกครอง | เกณฑ์ประเมิน, จดหมายผู้ปกครอง, … | worker | ไม่ |

- ราคาอยู่ในแคตตาล็อก (`catalog.py` + `data/services.json`) แต่ **ซ่อนจากครู** จนกว่าแอดมินจะเปิดสวิตช์ **เก็บเงิน** ต่อบริการ (ค่าเริ่มต้นปิด)
- งานที่ `fulfil=auto` (เช่น `pdf_merge`, `pdf_split`, `pdf_compress`) ทำเสร็จทันทีหลังส่ง — **อย่า claim**
- งานบริการใหม่เก็บไฟล์อัปโหลดใน `files.uploads[]` และผลลัพธ์ใน `results[]` (หลายไฟล์ได้)
- กรองคิวตามบริการ: `python3 remote_worker.py list --service slides` / `claim --service slides`

### การคำนวณเวลารอ (ETA)
```
ETA = จำนวนแผนที่ต้องทำจริง × เวลาเฉลี่ยต่อแผน (เฉลี่ย 20 งานล่าสุด, ค่าเริ่มต้น 8 นาที)
      × 1.5 (ถ้า from_scratch หรือเลือก "ทำภาพประกอบเพิ่ม" — คูณครั้งเดียว)
      + เวลาของงานที่รออยู่ข้างหน้า
```

### ผู้ประมวลผลงาน
บอท Grok Bot เป็น worker: ดึงงานจากคิวผ่าน `remote_worker.py` แล้ว **เขียนข้อมูลลงในฟอร์มของโรงเรียนผู้ส่งเอง** (คงรูปแบบ หัวข้อ ฟอนต์ TH Sarabun) จากนั้นส่งผลลัพธ์ .docx + .pdf กลับขึ้นเว็บ

---

## 2. ไฟล์และโฟลเดอร์สำคัญ

### `/workspace/lp-web` (ตัวเว็บ)
| ไฟล์ | หน้าที่ |
|---|---|
| `app.py` | เว็บ Flask (หน้า `/`, `/plan`, `/services/...`, `/job/<id>`, `/admin`, Worker API) |
| `store.py` | จัดการคิว/ไฟล์งานบนดิสก์ (รองรับหลายบริการ + ผลลัพธ์หลายไฟล์) |
| `catalog.py` | แคตตาล็อกบริการ + ราคา + สวิตช์เก็บเงิน |
| `autofulfil.py` | ทำอัตโนมัติ PDF รวม/แยก/บีบอัด |
| `plancount.py` | นับจำนวนแผนในไฟล์ข้อมูล (ใช้ถาม "1 แผน หรือทั้งหมด N แผน") |
| `templates/` | หน้า HTML ภาษาไทย (home/group/service_form/track + แผนเดิม) |
| `remote_worker.py` | ไคลเอนต์ worker ระยะไกล (stdlib ล้วน) |
| `worker_cli.py` | worker แบบทำงานกับดิสก์ตรง (ใช้เมื่อรันเว็บในเครื่อง) |
| `default_template/main.docx` | แม่แบบสำรอง |
| `render.yaml`, `requirements.txt`, `start.sh` | ตั้งค่า deploy / รันในเครื่อง |
| `README.md` | เอกสารเทคนิค (API, โครงสร้างข้อมูล) |
| `.env` | **ความลับ — ห้ามเปิดเผย/ห้าม commit** |
| `lp_jobs/<id>/` | งานที่ดาวน์โหลดมาทำ (job.json, template, source, build/) — ไม่ commit |

ตัวอย่างสคริปต์สร้างแผนของแต่ละงาน (ดูเป็นแบบอย่างได้):
- `lp_jobs/20261030-232705-5e63a5/build/build_plan.py` — ฟอร์มโรงเรียนแบบอื่น (ไม่ใช่ GPAS)
- `lp_jobs/20261031-213111-ea96bd/build/` — งานหลายแผน (แผน 5-8 การละลาย)
- `lp_jobs/20261031-222350-77bab6/build/` และ `web2/` — งานใหญ่ 16 แผน (แผน 24-39 หิน) ที่แบ่งทำ 2 บอท

### `/workspace/lp` (เครื่องมือทำแผน)
| ไฟล์ | หน้าที่ |
|---|---|
| `main.docx` | แม่แบบเริ่มต้น (คณิตศาสตร์ ม.3 รูปแบบ GPAS 5 Steps) |
| `fill_template.py` | ตัวอย่างการเติมข้อมูลลงแม่แบบ GPAS |
| `sample_inequality.json` | ข้อมูลตัวอย่าง (เรื่องอสมการ) |
| `render.sh` | แปลง .docx → PDF ด้วย soffice |
| `word_compat.py` | แก้ตารางให้แสดงถูกใน Microsoft Word (**ต้องรันก่อนส่งทุกครั้ง**) |
| `WORD_COMPAT_NOTES.md` | ข้อควรระวังเรื่องความเข้ากันได้กับ Word |

---

## 3. ขั้นตอนทำงานแต่ละงาน

0. **ตรวจสลิป (ถ้ามี):** `python3 remote_worker.py payments` — ถ้ามีงาน `payment_review` ให้ตรวจสลิปก่อน (ดูหัวข้อ 3.1) แล้ว `pay-ok` / `pay-reject`
1. **ตรวจคิวงานจัดทำ:** `python3 remote_worker.py list` — ถ้าไม่มีงาน `queued` (และไม่มีสลิปรอตรวจ) ให้หยุดเงียบ ๆ
   - `list` / `claim` **จะไม่หยิบงานที่ยังไม่จ่าย** (`awaiting_payment` / `payment_review` / `payment_rejected`)
2. **รับงาน (claim):** `python3 remote_worker.py claim <id>` → ดาวน์โหลดไฟล์ไปที่ `lp_jobs/<id>/` และพิมพ์ JSON ของงาน
   - claim คือ "ตัวล็อก" — ใคร claim ได้ คนนั้นรับผิดชอบงาน
3. **อ่านคำสั่งก่อนเสมอ:** `instructions`/`note`, `options`, `plan_mode`/`plan_selected`, ช่องรายละเอียด
4. **อ่านไฟล์:** แปลง .doc/.pdf ด้วย soffice เมื่อจำเป็น อ่านข้อมูลด้วยวิจารณญาณ (แต่ละคนมีรูปแบบต่างกัน อย่ายึดการจับคู่ช่องแบบตายตัว)
5. **เขียนลงฟอร์มของผู้ส่ง:** คงเลย์เอาต์ หัวข้อ ฟอนต์ TH Sarabun และสไตล์ของฟอร์ม
   - ถ้าคำสั่งขัดกับฟอร์ม → ยึดฟอร์ม และแจ้งในผลลัพธ์ว่าทำอะไรไป
   - ไม่มีไฟล์ข้อมูล → เขียนแผนเองตามคำสั่ง ให้เนื้อหาเหมาะกับวัย สอดคล้องตัวชี้วัดหลักสูตรไทย
   - แก้ข้อผิดพลาดทางเนื้อหา/คณิตศาสตร์ที่เห็นชัด และใช้ภาษาไทยให้เป็นธรรมชาติ
6. **ทำให้เข้ากับ Word:** ทำตาม `WORD_COMPAT_NOTES.md` แล้วรัน `python3 /workspace/lp/word_compat.py <ไฟล์.docx>`
7. **ตรวจงาน (QA):** แปลงเป็น PDF ด้วย `/workspace/lp/render.sh` แล้ว **ดูทุกหน้า** ว่าไม่มีอะไรเพี้ยน (ดูหัวข้อ 7)
8. **ตรวจสถานะซ้ำก่อนส่ง:** `python3 remote_worker.py show <id>` — ถ้าไม่ใช่ `processing` แล้ว (เช่น แอดมินยกเลิก) **ห้ามอัปโหลด**
9. **ส่งงาน:** `python3 remote_worker.py complete <id> <ไฟล์.docx> <ไฟล์.pdf>`
   - ทำไม่ได้จริง → `python3 remote_worker.py fail <id> "เหตุผลภาษาไทยที่ครูเข้าใจได้"`
10. **รายงานผู้ใช้เป็นภาษาไทย:** 1 บรรทัดต่องาน (รหัสงาน, ชื่อแผน, เสร็จ/ล้มเหลวเพราะอะไร)

---

## 3.1 ตรวจสลิป PromptPay (บังคับก่อนเข้าคิว)

งานจะเข้า `queued` **หลังสลิปผ่านการตรวจเท่านั้น** บอท worker เป็นผู้ตรวจ (มองเห็นรูป) หรือแอดมินกดอนุมัติเองที่ `/admin`

```bash
python3 remote_worker.py payments                 # รายการงาน payment_review
python3 remote_worker.py slip <id> [outfile]      # ดาวน์โหลดรูปสลิป
python3 remote_worker.py pay-ok <id> --ref <เลขอ้างอิง> --amount <ยอด> --time "<วันเวลาโอน>" \
        --payer "<ชื่อผู้โอน>" --payee "<ชื่อผู้รับบนสลิป>" --note "..."
python3 remote_worker.py pay-reject <id> "เหตุผลภาษาไทยที่ครูเข้าใจได้"
```

### เช็คลิสต์ก่อน `pay-ok` (ต้องผ่านทุกข้อ)
1. **ชื่อผู้รับบนสลิป** ตรงกับชื่อบัญชีที่ตั้งไว้ (ค่าเริ่มต้น `พิภูษณ ยิ้มหนองโพธิ์` — ดูจาก `payments` หรือ `/admin`)
2. **ยอดเงิน** เท่ากับ `amount_due` ของงาน (= ราคาต่อแผน × จำนวนแผนที่ครูเลือก)
3. **เวลาโอน** ต้อง**หลัง** `payment.requested_at` (เวลาสร้างคำขอชำระ) และควรเป็นช่วงเวลาใกล้เคียง (ไม่ใช่สลิปเก่าหลายวัน)
4. **เลขที่อ้างอิงสลิป (slip ref)** ยังไม่เคยใช้กับงานอื่น — ถ้าซ้ำ เซิร์ฟเวอร์จะปฏิเสธ `pay-ok` (HTTP 409) ให้ `pay-reject` แทน
5. **หมายเลข PromptPay / เบอร์ผู้รับ** (ถ้าสลิปมี แสดงบางหลัก) สอดคล้องกับ PromptPay ID ของ QR เมื่อทราบค่า
6. **สลิปดูของจริง** — ไม่ใช่ภาพตัดต่อ/ซ้ำกับสลิปงานอื่นอย่างชัดเจน

ถ้าข้อใดไม่ผ่าน → `pay-reject` พร้อมเหตุผลสั้น ๆ ภาษาไทย (ครูจะอัปโหลดสลิปใหม่ได้)

หลัง `pay-ok` งานจะเป็น `queued` และบอทจัดทำแผนดึงด้วย `list` / `claim` ตามปกติ

---

## 4. คำสั่ง remote_worker

ตั้งค่า environment ก่อน (อย่าพิมพ์ค่าโทเคนออกหน้าจอ):
```bash
cd /workspace/lp-web
export LP_BASE_URL=https://lesson-plan-web.onrender.com
export LP_WORKER_TOKEN="$(grep '^WORKER_TOKEN=' .env | cut -d= -f2-)"
```

| คำสั่ง | ความหมาย |
|---|---|
| `python3 remote_worker.py list [--all] [--service ID]` | งานที่ยังไม่เสร็จ (หรือทั้งหมดถ้าใส่ `--all`) กรองบริการได้ |
| `python3 remote_worker.py claim [id] [--service ID]` | รับงานเก่าสุด หรือระบุ id + ดาวน์โหลดไฟล์อินพุต |
| `python3 remote_worker.py show <id>` | ดูสถานะ/รายละเอียดงาน |
| `python3 remote_worker.py complete <id> <file> [file…]` | ส่งผลลัพธ์ (แผน: docx [pdf] · บริการอื่น: ไฟล์ใดก็ได้หลายไฟล์) |
| `python3 remote_worker.py fail <id> "ข้อความ"` | ปิดงานเป็นล้มเหลว พร้อมเหตุผล |
| `python3 remote_worker.py requeue <id>` | คืนงานเข้าคิว |
| `python3 remote_worker.py health` | ตรวจว่าเว็บตื่น/ทำงานอยู่ |
| `python3 remote_worker.py payments [--status …]` | งานรอตรวจสลิป (ค่าเริ่มต้น `payment_review`) |
| `python3 remote_worker.py slip <id> [out]` | ดาวน์โหลดสลิป |
| `python3 remote_worker.py pay-ok <id> --ref …` | อนุมัติสลิป → งานเข้า `queued` |
| `python3 remote_worker.py pay-reject <id> "เหตุผล"` | ปฏิเสธสลิป → ครูอัปโหลดใหม่ได้ |

ตัวแปรเสริม: `LP_WORK_DIR` (ค่าเริ่มต้น `./lp_jobs`)

---

## 4.1 วิธีทำแต่ละประเภทบริการ (สำหรับ worker)

อ่าน `service_id` จาก JSON หลัง `claim` แล้วทำตามนี้:

| service_id | ผลลัพธ์ที่ต้องอัปโหลด | หมายเหตุ |
|---|---|---|
| `lesson_plan` | `result.docx` + แนะนำ `result.pdf` | เหมือนเดิมทุกประการ รวม PromptPay |
| `slides` | `.pptx` (+ ทางเลือก PDF) | อ่านหัวข้อจาก `inputs` / ไฟล์ใน `uploads` |
| `worksheet` / `quiz` / `flashcards` / `infographic` | `.docx` หรือ `.pdf` / ภาพ ตามที่ตกลงในคำสั่ง | |
| `pdf_ocr` / `pdf_convert` / `image_to_pdf` ฯลฯ | ไฟล์ผลตามชนิด | |
| `pdf_merge` / `pdf_split` / `pdf_compress` | — | **อัตโนมัติ** เว็บทำให้แล้ว ห้าม claim |
| งานเอกสารครู / ผู้ปกครอง | `.docx` (+ PDF ถ้าทำได้) | ใช้ `inputs.instructions` เป็นหลัก |

ดาวน์โหลดไฟล์อินพุตบริการทั่วไปจาก `local_paths.uploads[]` (หรือ URL `upload_0`, `upload_1`, …)

---

## 5. กติกาสำคัญ
- **บริการใหม่ไม่เก็บเงิน (ตอนนี้):** งานที่ไม่ใช่ `lesson_plan` จะเข้า `queued` ทันทีหลังครูส่ง — ไม่มี QR/สลิป จนกว่าแอดมินจะเปิด "เก็บเงิน" ใน `/admin#services`
- **งาน `fulfil=auto`:** ห้าม claim / complete — ระบบทำและปิดงานเอง
- **ผลลัพธ์หลายไฟล์:** `complete <id> a.pptx b.pdf …` ได้ — เก็บใน `results[]`


1. **ห้ามเปิดเผยค่าใน `.env`** (ADMIN_PASSWORD, WORKER_TOKEN, SECRET_KEY) — ห้ามพิมพ์ ห้ามใส่ในแชต ห้าม commit ห้ามอัปโหลด
2. **ห้าม deploy ขณะมีงานในคิวหรือกำลังทำ** — ดิสก์ชั่วคราว งานของครูจะหายหมด
3. **ตรวจสถานะซ้ำก่อน complete ทุกครั้ง** — ถ้าไม่ใช่ `processing` อย่าอัปโหลด
4. **การยกเลิกงาน = `fail` พร้อมเหตุผลภาษาไทย** (ไม่มีคำสั่ง cancel แยก)
5. **ถ้าครูสั่ง "ทำตามฟอร์มเป๊ะ ๆ" ต้องทำตามเคร่งครัด** — ห้ามเพิ่มหัวข้อ/ตาราง/สไตล์ที่ฟอร์มไม่มี
6. **ตอบผู้ใช้เป็นภาษาไทยเสมอ**
7. **ถ้างานหนักเกินไป (คิวยาว/งานใหญ่หลายแผน) ให้แจ้งผู้ใช้** เพื่อพิจารณาแบ่งงานหรือแจ้งครู
8. ผลลัพธ์ต้องดูถูกต้องใน **Microsoft Word** ไม่ใช่แค่ LibreOffice → รัน `word_compat.py` ทุกครั้ง

---

## 6. การทำงานหลายบอท

- มี 2 บอทเฝ้าคิว สลับนาทีกันไม่ให้ชน:
  - **web** ตรวจที่นาที 1, 6, 11, 16, ... (ทุก 5 นาที)
  - **Web2** ตรวจที่นาที 3, 8, 13, 18, ...
- **claim คือตัวล็อก:** บอทที่ claim สำเร็จเป็นเจ้าของงาน บอทอื่นห้ามแตะ
- **งานใหญ่:** บอทที่ claim ต้อง **ประกาศการแบ่งงานก่อนเริ่มทำ** (เช่น เขียน `lp_jobs/<id>/SPLIT_NOTE.txt`: "web ทำแผน 1-8, Web2 ทำแผน 9-16")
- **1 ไฟล์ผลลัพธ์ต่อ 1 งาน:** บอทผู้ช่วยวางไฟล์ส่วนของตัวเองไว้ (เช่น `web2/plans_9-16.docx` หรือ `part2/`) แล้ว **บอทที่ claim เป็นคนรวมไฟล์** รัน `word_compat.py` แล้ว complete เพียงครั้งเดียว
- ตัวอย่างจริง: งาน `20261031-222350-77bab6` (แผน 24-39 เรื่องหิน วัฏจักรหิน และซากดึกดำบรรพ์)

---

## 7. ปัญหาที่เจอบ่อยและวิธีแก้

| ปัญหา | วิธีแก้ |
|---|---|
| ช่องลงชื่อ (signature block) หลุดไปอยู่หน้าใหม่เดี่ยว ๆ | ย้ายช่องลงชื่อเข้าไปในแถวสุดท้ายของตาราง rubric และตั้ง `cantSplit` ให้แถวนั้น |
| เฉลยหลุดไปอยู่ในภาพประกอบ/ใบงาน | ทำภาพแยก 2 ชุด (มีเฉลย/ไม่มีเฉลย เช่น `img_rockcycle_blank.png`) ตรวจว่าใบงานนักเรียนใช้ภาพที่ไม่มีเฉลย |
| เลขข้อซ้อนกัน เช่น `- 1)` | อย่าใส่ทั้ง bullet และเลขข้อ — เลือกอย่างใดอย่างหนึ่ง/ลบ "- " ที่นำหน้าเลข |
| ตัว `ๆ` ตกไปขึ้นบรรทัดใหม่เดี่ยว ๆ | ใช้ NBSP (`\u00A0`) เชื่อมคำกับ `ๆ` |
| สัญลักษณ์ Wingdings (เช่น ☐ ✓) กลายเป็นตัวอักษรแปลก | ใช้อักขระ Unicode ตรง ๆ หรือคงฟอนต์ Wingdings ของฟอร์มเดิมไว้ (ตรวจใน Word) |
| ตารางเพี้ยนใน Word | ทำตาม `WORD_COMPAT_NOTES.md` แล้วรัน `word_compat.py` |
| เว็บไม่ตอบ | free plan หลับอยู่ รอ ~1 นาที (`remote_worker.py health`) |
| งานหายจากเว็บ | มีการ deploy/restart — ดิสก์ชั่วคราว ไฟล์ในเครื่อง `lp_jobs/` ยังอยู่ |

---

## 8. วิธีตั้ง routine ให้บอทใหม่

ชื่อ routine เดิม: **เฝ้าคิวเว็บแผนการสอน** — รันทุก 5 นาที ช่วง 07:00–22:55 (เวลาไทย)
(ถ้ามีหลายบอท ให้เลื่อนนาทีไม่ให้ตรงกัน ดูหัวข้อ 6)

**ข้อความ prompt ที่ใช้ (คัดลอกทั้งหมดให้บอทใหม่ตามนี้):**

```
Check the lesson-plan web app queue at https://lesson-plan-web.onrender.com and process any waiting submissions.

How: on my computer, in /workspace/lp-web, run remote_worker.py with LP_BASE_URL=https://lesson-plan-web.onrender.com and LP_WORKER_TOKEN set from WORKER_TOKEN in /workspace/lp-web/.env (never print or reveal secret values). First run `payments` and verify any PromptPay slips in payment_review (see GROKBOT_GUIDE.md §3.1: payee name, amount_due, transfer time after requested_at, unique slip ref, PromptPay digits, genuine slip) with pay-ok or pay-reject. Then check for queued jobs (the free Render instance may take ~1 minute to wake; the script retries). If none are queued and no slips need review, stop silently. Unpaid jobs must never be claimed.

For each queued job, hand the work to a background executor with a self-contained brief: claim the job, download the files (file 1 = that submitter's school lesson-plan form/template, always present; file 2 = their source data file, optional, .doc/.docx/.pdf), read the data with judgment (sources vary between people, so don't assume a fixed field mapping), and rewrite the content into the submitter's own school form, keeping that form's layout, headings, fonts (TH Sarabun), and styling. Read the submitter's free-text instructions (instructions/note) and ticked options (e.g. extra illustrations, worksheets/knowledge sheets, fix errors) first and follow them; if an instruction conflicts with the school form, keep the form and say what was done in the result. If there is no data file (from_scratch), write the plan yourself from the instructions (subject, grade, topic, plan number) with sound, age-appropriate content aligned to Thai curriculum indicators. A data file may hold several plans: if the job says plan_mode 'one', produce only the plan in plan_selected; if 'all' (or the field is missing and the file has several plans), produce every plan in one combined .docx. Convert .doc/.pdf with soffice where needed. Fill the optional details the submitter typed (teacher name, teaching date day/month/year in Thai, plan number, unit, semester, academic year); any detail they left blank stays blank as in the form. Fix obvious factual or math errors and keep the Thai language natural. For reference, /workspace/lp/fill_template.py and /workspace/lp/sample_inequality.json show a worked example for the default GPAS 5 Steps template (/workspace/lp/main.docx), and /workspace/lp-web/lp_jobs/20261030-232705-5e63a5/build/build_plan.py is a worked example for a different school form. The output must look right in Microsoft Word, not just LibreOffice: follow /workspace/lp/WORD_COMPAT_NOTES.md and run /workspace/lp/word_compat.py on the final .docx before saving. Render the result to PDF (/workspace/lp/render.sh) and look at the pages to check nothing is broken. Right before completing, re-check the job's status on the site: if it is no longer 'processing' (for example the admin cancelled it as failed), do not upload anything. Otherwise complete the job with the .docx and .pdf. If a job truly can't be done (unreadable files, no usable data or instructions), mark it failed with a short Thai reason the submitter can understand.

Result goes to the user in this chat, in Thai: one short line per finished or failed job (job id, the plan title, done or why it failed). When no jobs were queued, send nothing.
```

> หมายเหตุ: ถ้าบอทใหม่ทำงานบนเครื่องอื่น ต้องมีไฟล์ `/workspace/lp-web` และ `/workspace/lp` (ใช้ไฟล์ backup) และสร้าง `.env` เอง (ดู `.env.example`) — ขอค่าโทเคนจากเจ้าของระบบโดยตรง ห้ามส่งผ่านแชตสาธารณะ

---

## 9. การ deploy

1. ตรวจคิวก่อน: `python3 remote_worker.py list` — ต้อง **ไม่มีงาน queued/processing**
2. commit และ push โค้ดขึ้น GitHub (`main`) — ห้าม force push, ห้าม commit `.env` / `lp_jobs/` / `data/`
3. เข้า Render Dashboard → service `srv-dbic8vuc6qcc73d8nbvg` → **Manual Deploy → Deploy latest commit**
   (GitHub auto-deploy ไม่ทำงาน ต้องกดเอง หรือใช้ Render MCP/CLI สั่ง deploy)
4. รอจน deploy เสร็จ แล้วตรวจ `https://lesson-plan-web.onrender.com/healthz` หรือ `remote_worker.py health`
5. ค่าตั้งค่าบน Render: Build `pip install -r requirements.txt`, Start `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`, Health check `/healthz`
6. ข้อควรจำ: deploy แล้วงานเก่าบนเว็บหายหมด — ครูที่งานเสร็จแล้วต้องดาวน์โหลดก่อน

---

## 10. ตำแหน่งความลับ (บอกเฉพาะที่อยู่ ไม่มีค่า)

| ความลับ | อยู่ที่ |
|---|---|
| ADMIN_PASSWORD, WORKER_TOKEN, SECRET_KEY, PORT, WEBHOOK_URL | `/workspace/lp-web/.env` (สิทธิ์ 600) |
| ค่าเดียวกันฝั่งเซิร์ฟเวอร์ | Render Dashboard → service `srv-dbic8vuc6qcc73d8nbvg` → Environment |
| สิทธิ์ GitHub | `gh` CLI ที่ล็อกอินไว้บนเครื่อง (บัญชี botbeamty11-hash) |

ใน backup มีเฉพาะ `.env.example` (ชื่อตัวแปร ไม่มีค่า) — **ห้ามใส่ค่าจริงลงในไฟล์ที่แชร์**

---

## Google Login + พ้อยท์ + SEO (รอบล่าสุด)

### Env ใหม่
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — ถ้าขาด หน้า login แจ้งภาษาไทย ไม่ crash
- `LP_TEST_LOGIN=1` — เปิด `/auth/test-login` สำหรับทดสอบเท่านั้น (ค่าเริ่มต้นปิด / 404)
- `LP_COOKIE_SECURE` — ค่าเริ่มต้นเปิด Secure cookie; ตั้ง `0` เมื่อทดสอบ HTTP local

### Google Cloud Console (สรุปภาษาไทย)
1. Consent screen แบบ External ชื่อแอป「ครูดี」 โดเมน `krudee.cc` + `onrender.com`
2. สร้าง OAuth Client แบบ **Web application**
3. Authorized redirect URIs:
   - `https://krudee.cc/auth/google/callback`
   - `https://lesson-plan-web.onrender.com/auth/google/callback`
4. ใส่ Client ID/Secret ใน Render env → รีสตาร์ท

Callback สร้างจาก `request` host + `ProxyFix` เพื่อรองรับทั้ง custom domain และ onrender.com (HTTPS)

### พฤติกรรมล็อกอิน
- ทุกหน้าดูได้โดยไม่ล็อกอิน
- POST ส่งฟอร์ม / งานของฉัน / เติมพ้อยท์ → ต้องล็อกอิน แล้วกลับหน้าที่ค้างไว้
- เก็บผู้ใช้ใน `data/users/<id>.json` (google_sub, email, name, picture, points, ledger)
- งานเก็บ `user_id` · หน้า `/my-jobs`
- แอดมินยังเป็นรหัสผ่านแยก

### พ้อยท์
- Admin: ผู้ใช้ & พ้อยท์ (ค้นหา / ปรับยอด / ledger / totals)
- `points_cost` ต่อบริการ (default 0 ทั้งแคตตาล็อก — ยังไม่เปิดเก็บ)
- Top-up PromptPay ปิดด้วย `points_topup_enabled` (default false); อนุมัติสลิปแล้วเข้าพ้อยท์ งานเป็น `done`
- Worker `payments` / `pay-ok` ใช้กับ top-up ได้ (approve_payment แยกทาง fulfil=topup)

### แบรนด์
- ชื่อ「ครูดี」/ krudee.cc · ธีม Sarabun · favicon/og/manifest/robots/sitemap/JSON-LD
