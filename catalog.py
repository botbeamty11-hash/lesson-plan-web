"""Service catalog: defaults in code, overrides in data/services.json."""
import json, os, copy

import store

def services_path():
    return os.path.join(store.DATA_DIR, "services.json")

# Pricing units (Thai labels for UI)
UNIT_LABELS = {
    "per_plan": "ต่อแผน",
    "per_page": "ต่อหน้า",
    "per_file": "ต่อไฟล์",
    "per_set": "ต่อชุด",
    "per_document": "ต่อเอกสาร",
    "per_job": "ต่องาน",
}

GROUP_ORDER = [
    "แผนการสอน",
    "สื่อการสอน",
    "แปลงและจัดการไฟล์",
    "งานเอกสารครู",
    "งานวัดผลและผู้ปกครอง",
]

GROUP_ICONS = {
    "แผนการสอน": "📘",
    "สื่อการสอน": "🎨",
    "แปลงและจัดการไฟล์": "🗂️",
    "งานเอกสารครู": "📋",
    "งานวัดผลและผู้ปกครอง": "📊",
}

# Map original fine-grained groups -> home card group
GROUP_HOME_MAP = {
    "แผนการสอน": "แผนการสอน",
    "สื่อการสอน": "สื่อการสอน",
    "แปลงและจัดการไฟล์": "แปลงและจัดการไฟล์",
    "งานเอกสารครู": "งานเอกสารครู",
    "งานวัดผล": "งานวัดผลและผู้ปกครอง",
    "สำหรับผู้ปกครอง/นักเรียน": "งานวัดผลและผู้ปกครอง",
}

# Field type: text | textarea | number | file | files | select | checkbox_group
# file fields: accept = list of extensions like [".pdf", ".docx"]

DEFAULT_SERVICES = [
    # ---- แผนการสอน (legacy, special form) ----
    {
        "id": "lesson_plan",
        "name": "แผนการจัดการเรียนรู้",
        "group": "แผนการสอน",
        "description": "จัดทำแผนการสอนตามฟอร์มของโรงเรียน (Word) จากไฟล์ข้อมูลหรือคำสั่งของคุณ",
        "unit": "per_plan",
        "price": 10.0,
        "icon": "📘",
        "enabled": True,
        "collect_payment": True,
        "points_cost": 0,  # lesson-plan keeps PromptPay flow
        "fulfil": "worker",
        "special_form": True,  # uses existing /plan form
        "inputs": [],
        "outputs": ["docx", "pdf"],
        "addons": [
            {"id": "addon_slides", "name": "เพิ่มสไลด์ประกอบการสอน (pptx)", "price": 20.0, "unit": "per_set"},
            {"id": "addon_worksheet", "name": "เพิ่มใบงาน/ใบความรู้พร้อมเฉลย", "price": 15.0, "unit": "per_set"},
            {"id": "addon_test", "name": "เพิ่มข้อสอบก่อน-หลังเรียนพร้อมเฉลย", "price": 20.0, "unit": "per_set"},
        ],
    },
    # ---- สื่อการสอน ----
    {
        "id": "slides",
        "name": "สไลด์ประกอบการสอน",
        "group": "สื่อการสอน",
        "description": "สร้างไฟล์ PowerPoint (pptx) ประกอบการสอนตามหัวข้อ/แผนที่แนบ — ฟอนต์ไทย อ่านง่าย",
        "unit": "per_set",
        "price": 20.0,
        "icon": "🖥️",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "topic", "label": "หัวข้อ / เรื่อง", "type": "text", "required": True},
            {"id": "grade", "label": "ชั้น", "type": "text", "required": False, "placeholder": "เช่น ม.2"},
            {"id": "subject", "label": "วิชา", "type": "text", "required": False},
            {"id": "slides_count", "label": "จำนวนสไลด์โดยประมาณ", "type": "number", "required": False, "min": 5, "max": 40, "default": 12},
            {"id": "instructions", "label": "รายละเอียด / จุดเน้น", "type": "textarea", "required": False},
            {"id": "source", "label": "ไฟล์อ้างอิง (แผน/เนื้อหา)", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".pptx", ".txt"]},
        ],
        "outputs": ["pptx"],
    },
    {
        "id": "worksheet",
        "name": "ใบงาน / ใบความรู้พร้อมเฉลย",
        "group": "สื่อการสอน",
        "description": "ใบงานหรือใบความรู้ภาษาไทย พร้อมเฉลยแยกชุด — จัดหน้า TH Sarabun",
        "unit": "per_set",
        "price": 15.0,
        "icon": "📝",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "topic", "label": "หัวข้อ / เรื่อง", "type": "text", "required": True},
            {"id": "grade", "label": "ชั้น", "type": "text", "required": False},
            {"id": "subject", "label": "วิชา", "type": "text", "required": False},
            {"id": "kind", "label": "ประเภท", "type": "select", "required": True,
             "choices": ["ใบงาน", "ใบความรู้", "ใบงาน+ใบความรู้"], "default": "ใบงาน"},
            {"id": "qty", "label": "จำนวนชุด", "type": "number", "required": True, "min": 1, "max": 10, "default": 1},
            {"id": "instructions", "label": "รายละเอียดเพิ่มเติม", "type": "textarea", "required": False},
            {"id": "source", "label": "ไฟล์อ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "test",
        "name": "ข้อสอบ / แบบทดสอบก่อน-หลังเรียนพร้อมเฉลย",
        "group": "สื่อการสอน",
        "description": "สร้างแบบทดสอบก่อนเรียน/หลังเรียน หรือข้อสอบ พร้อมเฉลยและเกณฑ์",
        "unit": "per_set",
        "price": 20.0,
        "icon": "✍️",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "topic", "label": "หัวข้อ / เรื่อง", "type": "text", "required": True},
            {"id": "grade", "label": "ชั้น", "type": "text", "required": False},
            {"id": "subject", "label": "วิชา", "type": "text", "required": False},
            {"id": "kind", "label": "ประเภท", "type": "select", "required": True,
             "choices": ["ก่อนเรียน", "หลังเรียน", "ก่อน+หลังเรียน", "ข้อสอบกลางภาค/ปลายภาค"], "default": "ก่อน+หลังเรียน"},
            {"id": "item_count", "label": "จำนวนข้อโดยประมาณ", "type": "number", "required": False, "min": 5, "max": 50, "default": 10},
            {"id": "instructions", "label": "รายละเอียด / รูปแบบข้อสอบ", "type": "textarea", "required": False},
            {"id": "source", "label": "ไฟล์อ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "game",
        "name": "เกม / ควิซในห้องเรียน",
        "group": "สื่อการสอน",
        "description": "ชุดคำถามสไตล์ Kahoot/Wordwall, แฟลชการ์ด หรือบิงโก — ส่งเป็นไฟล์พร้อมคำตอบ",
        "unit": "per_set",
        "price": 25.0,
        "icon": "🎮",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "topic", "label": "หัวข้อ / เรื่อง", "type": "text", "required": True},
            {"id": "grade", "label": "ชั้น", "type": "text", "required": False},
            {"id": "game_type", "label": "รูปแบบ", "type": "select", "required": True,
             "choices": ["ควิซหลายตัวเลือก (Kahoot-style)", "แฟลชการ์ด", "บิงโก", "จับคู่"], "default": "ควิซหลายตัวเลือก (Kahoot-style)"},
            {"id": "item_count", "label": "จำนวนข้อ/การ์ด", "type": "number", "required": False, "min": 8, "max": 40, "default": 15},
            {"id": "instructions", "label": "รายละเอียด", "type": "textarea", "required": False},
            {"id": "source", "label": "ไฟล์อ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".txt", ".xlsx"]},
        ],
        "outputs": ["docx", "xlsx", "pdf"],
    },
    {
        "id": "posters",
        "name": "ป้ายนิเทศ / ป้ายห้อง / เกียรติบัตร",
        "group": "สื่อการสอน",
        "description": "ออกแบบป้ายนิเทศ ป้ายชื่อห้อง หรือเกียรติบัตร (ส่งเป็นภาพ/PDF พร้อมพิมพ์)",
        "unit": "per_set",
        "price": 30.0,
        "icon": "🏅",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "kind", "label": "ประเภท", "type": "select", "required": True,
             "choices": ["ป้ายนิเทศ", "ป้ายห้อง", "เกียรติบัตร"], "default": "ป้ายนิเทศ"},
            {"id": "title", "label": "ข้อความหลัก / หัวข้อ", "type": "text", "required": True},
            {"id": "subtitle", "label": "ข้อความรอง", "type": "text", "required": False},
            {"id": "qty", "label": "จำนวนชิ้น", "type": "number", "required": True, "min": 1, "max": 20, "default": 1},
            {"id": "instructions", "label": "รายละเอียด / สี / สไตล์", "type": "textarea", "required": False},
            {"id": "source", "label": "ไฟล์ตัวอย่างหรือโลโก้", "type": "file", "required": False,
             "accept": [".png", ".jpg", ".jpeg", ".pdf", ".docx"]},
        ],
        "outputs": ["pdf", "png", "zip"],
    },
    # ---- แปลงและจัดการไฟล์ ----
    {
        "id": "pdf2word",
        "name": "PDF → Word ภาษาไทย",
        "group": "แปลงและจัดการไฟล์",
        "description": "แปลงไฟล์ PDF เป็น Word (.docx) รักษาเนื้อหาภาษาไทยให้มากที่สุด",
        "unit": "per_page",
        "price": 5.0,
        "icon": "📄",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "pages", "label": "จำนวนหน้า (โดยประมาณ)", "type": "number", "required": True, "min": 1, "max": 200, "default": 1},
            {"id": "instructions", "label": "หมายเหตุ", "type": "textarea", "required": False},
            {"id": "source", "label": "ไฟล์ PDF", "type": "file", "required": True, "accept": [".pdf"]},
        ],
        "outputs": ["docx"],
    },
    {
        "id": "ocr",
        "name": "OCR รูปเอกสาร → Word / ข้อความ",
        "group": "แปลงและจัดการไฟล์",
        "description": "อ่านข้อความจากรูปถ่าย/สแกนเอกสารภาษาไทย แล้วส่งเป็น Word หรือข้อความ",
        "unit": "per_page",
        "price": 5.0,
        "icon": "🔍",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "pages", "label": "จำนวนหน้า/รูป", "type": "number", "required": True, "min": 1, "max": 50, "default": 1},
            {"id": "out_format", "label": "รูปแบบผลลัพธ์", "type": "select", "required": True,
             "choices": ["Word (.docx)", "ข้อความล้วน"], "default": "Word (.docx)"},
            {"id": "instructions", "label": "หมายเหตุ", "type": "textarea", "required": False},
            {"id": "source", "label": "รูปเอกสาร (หรือ PDF สแกน)", "type": "files", "required": True,
             "accept": [".jpg", ".jpeg", ".png", ".webp", ".pdf", ".tif", ".tiff"]},
        ],
        "outputs": ["docx"],
    },
    {
        "id": "format_doc",
        "name": "จัดหน้าเอกสารตามฟอร์มโรงเรียน",
        "group": "แปลงและจัดการไฟล์",
        "description": "จัดฟอนต์ TH Sarabun, ระยะขอบ, เลขหน้า และรูปแบบตามฟอร์มที่แนบ",
        "unit": "per_document",
        "price": 30.0,
        "icon": "📐",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "instructions", "label": "รายละเอียดที่ต้องการ", "type": "textarea", "required": False},
            {"id": "template", "label": "ฟอร์ม/ตัวอย่างของโรงเรียน", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf"]},
            {"id": "source", "label": "เอกสารที่ต้องการจัดหน้า", "type": "file", "required": True,
             "accept": [".doc", ".docx", ".pdf", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "pdf_merge",
        "name": "รวม PDF",
        "group": "แปลงและจัดการไฟล์",
        "description": "รวมหลายไฟล์ PDF เป็นไฟล์เดียว (ทำอัตโนมัติหลังชำระเงิน)",
        "unit": "per_job",
        "price": 5.0,
        "icon": "🔗",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "auto",
        "inputs": [
            {"id": "source", "label": "ไฟล์ PDF ที่ต้องการรวม (เลือกหลายไฟล์ ตามลำดับ)", "type": "files", "required": True,
             "accept": [".pdf"]},
        ],
        "outputs": ["pdf"],
    },
    {
        "id": "pdf_split",
        "name": "แยก PDF",
        "group": "แปลงและจัดการไฟล์",
        "description": "แยกหน้าจาก PDF ตามช่วงที่ระบุ (ทำอัตโนมัติหลังชำระเงิน)",
        "unit": "per_job",
        "price": 5.0,
        "icon": "✂️",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "auto",
        "inputs": [
            {"id": "source", "label": "ไฟล์ PDF", "type": "file", "required": True, "accept": [".pdf"]},
            {"id": "ranges", "label": "ช่วงหน้า (เช่น 1-3,5,8-10)", "type": "text", "required": False,
             "placeholder": "ว่าง = ทุกหน้า", "hint": "ไม่กรอก = แยกทุกหน้า"},
        ],
        "outputs": ["pdf", "zip"],
    },
    {
        "id": "pdf_compress",
        "name": "ย่อขนาด PDF",
        "group": "แปลงและจัดการไฟล์",
        "description": "ลดขนาดไฟล์ PDF (ทำอัตโนมัติหลังชำระเงิน — ระดับพื้นฐาน)",
        "unit": "per_job",
        "price": 5.0,
        "icon": "📦",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "auto",
        "inputs": [
            {"id": "source", "label": "ไฟล์ PDF", "type": "file", "required": True, "accept": [".pdf"]},
        ],
        "outputs": ["pdf"],
    },
    # ---- งานเอกสารครู ----
    {
        "id": "sar",
        "name": "รายงานผลการปฏิบัติงาน / SAR",
        "group": "งานเอกสารครู",
        "description": "ร่างรายงานประเมินตนเอง (SAR) หรือรายงานผลการปฏิบัติงาน ตามข้อมูลที่ให้",
        "unit": "per_document",
        "price": 200.0,
        "icon": "📑",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "school", "label": "โรงเรียน / สังกัด", "type": "text", "required": False},
            {"id": "year", "label": "ปีการศึกษา", "type": "text", "required": False},
            {"id": "instructions", "label": "ข้อมูล / จุดที่ต้องเน้น", "type": "textarea", "required": True},
            {"id": "template", "label": "ฟอร์มของโรงเรียน", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf"]},
            {"id": "source", "label": "ไฟล์ข้อมูลอ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".xlsx", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "pa",
        "name": "ว.PA / ข้อตกลงพัฒนางาน (PA)",
        "group": "งานเอกสารครู",
        "description": "จัดทำเอกสาร ว.PA หรือข้อตกลงในการพัฒนางาน ตามแบบของโรงเรียน",
        "unit": "per_document",
        "price": 200.0,
        "icon": "🤝",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "teacher", "label": "ชื่อครู", "type": "text", "required": False},
            {"id": "year", "label": "ปีการศึกษา", "type": "text", "required": False},
            {"id": "instructions", "label": "รายละเอียดข้อตกลง / เป้าหมาย", "type": "textarea", "required": True},
            {"id": "template", "label": "แบบฟอร์ม ว.PA ของโรงเรียน", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf"]},
            {"id": "source", "label": "ไฟล์อ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "research",
        "name": "วิจัยในชั้นเรียน (ฉบับสั้น)",
        "group": "งานเอกสารครู",
        "description": "ร่างวิจัยในชั้นเรียนฉบับสั้น (ความเป็นมา วัตถุประสงค์ วิธี ผล สรุป)",
        "unit": "per_document",
        "price": 250.0,
        "icon": "🔬",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "topic", "label": "หัวข้อวิจัย", "type": "text", "required": True},
            {"id": "grade", "label": "ชั้นที่ทดลอง", "type": "text", "required": False},
            {"id": "subject", "label": "วิชา", "type": "text", "required": False},
            {"id": "instructions", "label": "รายละเอียด / ข้อมูลที่มี", "type": "textarea", "required": True},
            {"id": "source", "label": "ไฟล์อ้างอิง / ข้อมูล", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".xlsx", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "memo",
        "name": "บันทึกหลังสอน / บันทึกข้อความ / หนังสือราชการ",
        "group": "งานเอกสารครู",
        "description": "ร่างบันทึกหลังสอน บันทึกข้อความ หรือหนังสือราชการโทนสุภาพ ถูกต้องตามระเบียบ",
        "unit": "per_document",
        "price": 50.0,
        "icon": "✉️",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "kind", "label": "ประเภท", "type": "select", "required": True,
             "choices": ["บันทึกหลังสอน", "บันทึกข้อความ", "หนังสือราชการ"], "default": "บันทึกหลังสอน"},
            {"id": "qty", "label": "จำนวนฉบับ", "type": "number", "required": True, "min": 1, "max": 20, "default": 1},
            {"id": "instructions", "label": "เนื้อหา / ประเด็น", "type": "textarea", "required": True},
            {"id": "template", "label": "ฟอร์มตัวอย่าง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf"]},
            {"id": "source", "label": "ไฟล์อ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "project_report",
        "name": "รายงานโครงการ / สรุปกิจกรรมพร้อมจัดรูป",
        "group": "งานเอกสารครู",
        "description": "จัดทำรายงานโครงการหรือสรุปกิจกรรม พร้อมจัดรูปภาพประกอบ",
        "unit": "per_document",
        "price": 150.0,
        "icon": "📌",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "title", "label": "ชื่อโครงการ / กิจกรรม", "type": "text", "required": True},
            {"id": "date_range", "label": "วันเวลาจัด", "type": "text", "required": False},
            {"id": "instructions", "label": "รายละเอียด / ผลที่เกิดขึ้น", "type": "textarea", "required": True},
            {"id": "photos", "label": "รูปภาพประกอบ (เลือกได้หลายไฟล์)", "type": "files", "required": False,
             "accept": [".jpg", ".jpeg", ".png", ".webp"]},
            {"id": "source", "label": "ไฟล์ข้อมูล / โครงร่าง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".txt"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "pp5",
        "name": "ปพ.5 / เกณฑ์ประเมิน rubric",
        "group": "งานเอกสารครู",
        "description": "จัดทำ ปพ.5 หรือตารางเกณฑ์ประเมิน (rubric) ตามรายวิชา",
        "unit": "per_document",
        "price": 100.0,
        "icon": "✅",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "subject", "label": "วิชา", "type": "text", "required": True},
            {"id": "grade", "label": "ชั้น", "type": "text", "required": False},
            {"id": "kind", "label": "ประเภท", "type": "select", "required": True,
             "choices": ["ปพ.5", "Rubric / เกณฑ์ประเมิน", "ทั้งสอง"], "default": "Rubric / เกณฑ์ประเมิน"},
            {"id": "instructions", "label": "รายละเอียดตัวชี้วัด / เกณฑ์", "type": "textarea", "required": True},
            {"id": "template", "label": "ฟอร์มโรงเรียน", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".xlsx"]},
            {"id": "source", "label": "ไฟล์อ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".xlsx", ".txt"]},
        ],
        "outputs": ["docx", "xlsx", "pdf"],
    },
    # ---- งานวัดผล ----
    {
        "id": "grade_mcq",
        "name": "ตรวจข้อสอบปรนัยจากรูป + วิเคราะห์",
        "group": "งานวัดผล",
        "description": "ตรวจคำตอบปรนัยจากรูปกระดาษคำตอบ และวิเคราะห์ค่าความยาก / อำนาจจำแนก",
        "unit": "per_set",
        "price": 30.0,
        "icon": "🧮",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "item_count", "label": "จำนวนข้อ", "type": "number", "required": True, "min": 1, "max": 100, "default": 20},
            {"id": "student_count", "label": "จำนวนนักเรียนโดยประมาณ", "type": "number", "required": False, "min": 1, "max": 200},
            {"id": "answer_key", "label": "เฉลย (เช่น 1A 2C 3B … หรืออัปโหลดไฟล์)", "type": "textarea", "required": False},
            {"id": "instructions", "label": "หมายเหตุ", "type": "textarea", "required": False},
            {"id": "source", "label": "รูปกระดาษคำตอบ / ไฟล์", "type": "files", "required": True,
             "accept": [".jpg", ".jpeg", ".png", ".pdf", ".xlsx", ".csv"]},
        ],
        "outputs": ["xlsx", "docx", "pdf"],
    },
    {
        "id": "score_sheet",
        "name": "ตารางคะแนน / สรุปผลการเรียน (Excel)",
        "group": "งานวัดผล",
        "description": "สร้างตารางคะแนน สรุปเกรด หรือรายงานผลการเรียนเป็นไฟล์ Excel",
        "unit": "per_document",
        "price": 50.0,
        "icon": "📊",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "subject", "label": "วิชา / รายวิชา", "type": "text", "required": False},
            {"id": "grade", "label": "ชั้น", "type": "text", "required": False},
            {"id": "instructions", "label": "รูปแบบตาราง / เกณฑ์คิดเกรด", "type": "textarea", "required": True},
            {"id": "source", "label": "ไฟล์คะแนนดิบ / รายชื่อ", "type": "file", "required": False,
             "accept": [".xlsx", ".xls", ".csv", ".docx", ".pdf", ".txt"]},
        ],
        "outputs": ["xlsx", "pdf"],
    },
    # ---- ผู้ปกครอง / นักเรียน ----
    {
        "id": "parent_letter",
        "name": "จดหมายผู้ปกครอง",
        "group": "สำหรับผู้ปกครอง/นักเรียน",
        "description": "ร่างจดหมายถึงผู้ปกครอง (นัดหมาย แจ้งข่าว ขอความอนุเคราะห์ ฯลฯ) โทนสุภาพ",
        "unit": "per_document",
        "price": 30.0,
        "icon": "💌",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "purpose", "label": "วัตถุประสงค์", "type": "text", "required": True,
             "placeholder": "เช่น แจ้งกำหนดการประชุมผู้ปกครอง"},
            {"id": "qty", "label": "จำนวนฉบับ / ฉบับย่อย", "type": "number", "required": False, "min": 1, "max": 10, "default": 1},
            {"id": "instructions", "label": "รายละเอียดเนื้อหา", "type": "textarea", "required": True},
            {"id": "template", "label": "ฟอร์ม / หัวจดหมายโรงเรียน", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf"]},
        ],
        "outputs": ["docx", "pdf"],
    },
    {
        "id": "google_form",
        "name": "แบบสอบถาม Google Form + สรุปผล",
        "group": "สำหรับผู้ปกครอง/นักเรียน",
        "description": "ออกแบบชุดคำถามสำหรับ Google Form และไฟล์สรุปผล/คู่มือการสร้างฟอร์ม",
        "unit": "per_set",
        "price": 80.0,
        "icon": "📋",
        "enabled": True,
        "collect_payment": False,
        "points_cost": 0,
        "fulfil": "worker",
        "inputs": [
            {"id": "topic", "label": "หัวข้อแบบสอบถาม", "type": "text", "required": True},
            {"id": "audience", "label": "กลุ่มเป้าหมาย", "type": "text", "required": False,
             "placeholder": "เช่น ผู้ปกครองนักเรียน ป.4"},
            {"id": "item_count", "label": "จำนวนข้อโดยประมาณ", "type": "number", "required": False, "min": 5, "max": 40, "default": 10},
            {"id": "instructions", "label": "รายละเอียด / ประเด็นที่ต้องการถาม", "type": "textarea", "required": True},
            {"id": "source", "label": "ไฟล์อ้างอิง", "type": "file", "required": False,
             "accept": [".doc", ".docx", ".pdf", ".xlsx", ".txt"]},
        ],
        "outputs": ["docx", "xlsx"],
    },
]


def _defaults_by_id():
    return {s["id"]: copy.deepcopy(s) for s in DEFAULT_SERVICES}


def _load_overrides():
    if not os.path.isfile(services_path()):
        return {}
    try:
        with open(services_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "services" in data:
            data = data["services"]
        if isinstance(data, list):
            return {s["id"]: s for s in data if isinstance(s, dict) and "id" in s}
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def all_services(include_disabled=False):
    """Merged catalog: defaults + overrides (price/description/enabled)."""
    overrides = _load_overrides()
    out = []
    for s in DEFAULT_SERVICES:
        item = copy.deepcopy(s)
        ov = overrides.get(s["id"]) or {}
        if "price" in ov:
            try:
                item["price"] = max(0.0, float(ov["price"]))
            except (TypeError, ValueError):
                pass
        if "description" in ov and ov["description"] is not None:
            item["description"] = str(ov["description"])
        if "enabled" in ov:
            item["enabled"] = bool(ov["enabled"])
        if "collect_payment" in ov:
            item["collect_payment"] = bool(ov["collect_payment"])
        if "points_cost" in ov:
            try:
                item["points_cost"] = max(0, int(ov["points_cost"]))
            except (TypeError, ValueError):
                pass
        if "name" in ov and ov["name"]:
            item["name"] = str(ov["name"])
        if include_disabled or item.get("enabled", True):
            out.append(item)
    return out


def get_service(service_id, include_disabled=True):
    for s in all_services(include_disabled=True):
        if s["id"] == service_id:
            if not include_disabled and not s.get("enabled", True):
                return None
            return s
    return None


def services_by_group(include_disabled=False, home=False):
    """Return [(group_name, [services])]. If home=True, collapse into ≤5 home cards."""
    groups = {g: [] for g in GROUP_ORDER}
    for s in all_services(include_disabled=include_disabled):
        raw = s.get("group") or "อื่น ๆ"
        g = GROUP_HOME_MAP.get(raw, raw) if home else raw
        if g not in groups:
            groups[g] = []
        groups[g].append(s)
    order = GROUP_ORDER if home else list(dict.fromkeys(
        [s.get("group") for s in all_services(include_disabled=include_disabled) if s.get("group")]
    ))
    return [(g, groups[g]) for g in order if groups.get(g)]


def save_service_overrides(updates):
    """updates: {service_id: {price?, description?, enabled?}} — merge into services.json."""
    os.makedirs(store.DATA_DIR, exist_ok=True)
    cur = _load_overrides()
    for sid, patch in (updates or {}).items():
        base = cur.get(sid) or {"id": sid}
        if "price" in patch:
            try:
                base["price"] = max(0.0, float(patch["price"]))
            except (TypeError, ValueError):
                pass
        if "description" in patch and patch["description"] is not None:
            base["description"] = str(patch["description"])
        if "enabled" in patch:
            base["enabled"] = bool(patch["enabled"])
        if "collect_payment" in patch:
            base["collect_payment"] = bool(patch["collect_payment"])
        if "points_cost" in patch:
            try:
                base["points_cost"] = max(0, int(patch["points_cost"]))
            except (TypeError, ValueError):
                pass
        if "name" in patch and patch["name"]:
            base["name"] = str(patch["name"])
        base["id"] = sid
        cur[sid] = base
    # keep as list for readability
    payload = {"services": [cur[s["id"]] for s in DEFAULT_SERVICES if s["id"] in cur]}
    # also keep any unknown ids
    known = {s["id"] for s in DEFAULT_SERVICES}
    for sid, v in cur.items():
        if sid not in known:
            payload["services"].append(v)
    path = services_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return all_services(include_disabled=True)


def unit_label(unit):
    return UNIT_LABELS.get(unit, unit or "")


def qty_from_inputs(service, inputs):
    """How many pricing units to bill for this order."""
    unit = service.get("unit")
    inputs = inputs or {}
    if unit == "per_page":
        try:
            return max(1, int(inputs.get("pages") or 1))
        except (TypeError, ValueError):
            return 1
    if unit == "per_set":
        for key in ("qty", "slides_count", "item_count"):
            if inputs.get(key) not in (None, ""):
                try:
                    return max(1, int(inputs.get(key)))
                except (TypeError, ValueError):
                    pass
        return 1
    if unit == "per_document":
        try:
            return max(1, int(inputs.get("qty") or 1))
        except (TypeError, ValueError):
            return 1
    if unit == "per_file":
        files = inputs.get("_file_count") or inputs.get("file_count") or 1
        try:
            return max(1, int(files))
        except (TypeError, ValueError):
            return 1
    if unit == "per_plan":
        try:
            return max(1, int(inputs.get("effective_plan_count") or inputs.get("plan_count") or 1))
        except (TypeError, ValueError):
            return 1
    # per_job
    return 1


def compute_amount(service, inputs, addons=None):
    """Return (amount, qty, unit_price, breakdown_list)."""
    qty = qty_from_inputs(service, inputs)
    price = float(service.get("price") or 0)
    amount = round(price * qty, 2)
    breakdown = [{
        "id": service["id"],
        "name": service["name"],
        "qty": qty,
        "unit": service.get("unit"),
        "unit_price": price,
        "amount": amount,
    }]
    for ad in addons or []:
        ad_price = float(ad.get("price") or 0)
        ad_qty = 1
        ad_amt = round(ad_price * ad_qty, 2)
        amount = round(amount + ad_amt, 2)
        breakdown.append({
            "id": ad.get("id"),
            "name": ad.get("name"),
            "qty": ad_qty,
            "unit": ad.get("unit") or "per_set",
            "unit_price": ad_price,
            "amount": ad_amt,
        })
    return amount, qty, price, breakdown
