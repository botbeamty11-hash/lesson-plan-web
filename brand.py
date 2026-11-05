"""Brand constants + SVG icon helpers for ครูดี / krudee.cc."""
SITE_NAME = "ครูดี"
SITE_HOST = "krudee.cc"
SITE_URL = "https://krudee.cc"
SITE_TAGLINE = "บริการแผนการสอน สื่อ และเอกสารครู — ง่าย เร็ว มืออาชีพ"
SITE_DESC = (
    "ครูดี (krudee.cc) บริการทำแผนการจัดการเรียนรู้ แผนการสอน สื่อการสอน "
    "ใบงาน ข้อสอบพร้อมเฉลย ว.PA SAR วิจัยในชั้นเรียน และแปลง PDF เป็น Word ภาษาไทย สำหรับครู"
)

# Inline SVG icons (24x24 viewBox) for groups — simple line style
GROUP_SVG = {
    "แผนการสอน": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h7l5 5v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5z"/><path d="M13 3v5h5M8 13h8M8 17h6"/></svg>',
    "สื่อการสอน": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><path d="M8 9l2.5 2L14 8l3 4"/></svg>',
    "แปลงและจัดการไฟล์": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/><path d="M9 14h6M12 11v6"/></svg>',
    "งานเอกสารครู": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M8 4h8a2 2 0 0 1 2 2v14l-6-3-6 3V6a2 2 0 0 1 2-2z"/><path d="M9 9h6M9 13h4"/></svg>',
    "งานวัดผลและผู้ปกครอง": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 19V9l4 3 4-6 4 4 4-2v11H4z"/><path d="M4 19h16"/></svg>',
}

LOGO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="ครูดี">
  <defs><linearGradient id="kg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#2563eb"/><stop offset="100%" stop-color="#0ea5e9"/></linearGradient></defs>
  <rect width="64" height="64" rx="14" fill="url(#kg)"/>
  <text x="32" y="44" text-anchor="middle" font-family="Sarabun,Noto Sans Thai,sans-serif" font-size="34" font-weight="700" fill="#fff">ค</text>
</svg>'''


def group_icon(name):
    return GROUP_SVG.get(name) or GROUP_SVG["แผนการสอน"]


def page_meta(title=None, description=None, path="/", og_type="website"):
    t = title or f"{SITE_NAME} — {SITE_TAGLINE}"
    if title and SITE_NAME not in title:
        t = f"{title} | {SITE_NAME}"
    d = description or SITE_DESC
    canonical = SITE_URL.rstrip("/") + (path if path.startswith("/") else "/" + path)
    return {
        "title": t,
        "description": d,
        "canonical": canonical,
        "og_type": og_type,
        "site_name": SITE_NAME,
        "site_url": SITE_URL,
        "og_image": SITE_URL + "/static/og-image.png",
    }
