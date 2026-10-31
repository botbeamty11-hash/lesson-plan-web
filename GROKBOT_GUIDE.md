# คู่มือส่งต่องาน: ระบบเว็บจัดทำแผนการสอน (lesson-plan-web)

> สำหรับบอท/ผู้ดูแลคนใหม่ที่จะรับช่วงดูแลเว็บและประมวลผลคิวงาน
> ปรับปรุงล่าสุด: 31 ต.ค. 2569 (เวลาไทย)

---

## 1. ภาพรวมระบบ

- **เว็บแอป:** https://lesson-plan-web.onrender.com
- **เทคโนโลยี:** Flask + gunicorn (worker เดียว, 4 threads) โฮสต์บน **Render free plan (Singapore)**
  - Service ID: `srv-dbic8vuc6qcc73d8nbvg`
  - **ดิสก์ชั่วคราว:** ทุกครั้งที่ deploy/restart งานและไฟล์บนเว็บ **หายหมด**
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
| `app.py` | เว็บ Flask (หน้า `/`, `/job/<id>`, `/admin`, Worker API) |
| `store.py` | จัดการคิว/ไฟล์งานบนดิสก์ |
| `plancount.py` | นับจำนวนแผนในไฟล์ข้อมูล (ใช้ถาม "1 แผน หรือทั้งหมด N แผน") |
| `templates/` | หน้า HTML ภาษาไทย |
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

1. **ตรวจคิว:** `python3 remote_worker.py list` — ถ้าไม่มีงาน `queued` ให้หยุดเงียบ ๆ
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

## 4. คำสั่ง remote_worker

ตั้งค่า environment ก่อน (อย่าพิมพ์ค่าโทเคนออกหน้าจอ):
```bash
cd /workspace/lp-web
export LP_BASE_URL=https://lesson-plan-web.onrender.com
export LP_WORKER_TOKEN="$(grep '^WORKER_TOKEN=' .env | cut -d= -f2-)"
```

| คำสั่ง | ความหมาย |
|---|---|
| `python3 remote_worker.py list [--all]` | งานที่ยังไม่เสร็จ (หรือทั้งหมดถ้าใส่ `--all`) |
| `python3 remote_worker.py claim [id]` | รับงานเก่าสุด หรือระบุ id + ดาวน์โหลดฟอร์มและไฟล์ข้อมูล |
| `python3 remote_worker.py show <id>` | ดูสถานะ/รายละเอียดงาน |
| `python3 remote_worker.py complete <id> <docx> [pdf]` | ส่งผลลัพธ์ (**ใช้ทับงานที่ done แล้วได้** เพื่อส่งฉบับแก้) |
| `python3 remote_worker.py fail <id> "ข้อความ"` | ปิดงานเป็นล้มเหลว พร้อมเหตุผล |
| `python3 remote_worker.py requeue <id>` | คืนงานเข้าคิว |
| `python3 remote_worker.py health` | ตรวจว่าเว็บตื่น/ทำงานอยู่ |

ตัวแปรเสริม: `LP_WORK_DIR` (ค่าเริ่มต้น `./lp_jobs`)

---

## 5. กติกาสำคัญ

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

How: on my computer, in /workspace/lp-web, run remote_worker.py with LP_BASE_URL=https://lesson-plan-web.onrender.com and LP_WORKER_TOKEN set from WORKER_TOKEN in /workspace/lp-web/.env (never print or reveal secret values). First check for queued jobs (the free Render instance may take ~1 minute to wake; the script retries). If none are queued, stop silently.

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
