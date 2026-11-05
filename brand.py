"""Brand constants + SVG icon helpers for ครูดี / krudee.cc."""
SITE_NAME = "ครูดี"
SITE_HOST = "krudee.cc"
SITE_URL = "https://krudee.cc"
SITE_TAGLINE = "บริการแผนการสอน สื่อ และเอกสารครู — ง่าย เร็ว มืออาชีพ"
TEAL = "#22A386"
TEAL_DARK = "#1A7A66"
TEAL_SOFT = "#E6F6F2"

SITE_DESC = (
    "ครูดี (krudee.cc) บริการทำแผนการจัดการเรียนรู้ แผนการสอน สื่อการสอน "
    "ใบงาน ข้อสอบพร้อมเฉลย ว.PA SAR วิจัยในชั้นเรียน และแปลง PDF เป็น Word ภาษาไทย สำหรับครู — ทดลองใช้ฟรี"
)

# Inline SVG icons (24x24 viewBox) for groups — simple line style
GROUP_SVG = {
    "แผนการสอน": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h7l5 5v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5z"/><path d="M13 3v5h5M8 13h8M8 17h6"/></svg>',
    "สื่อการสอน": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><path d="M8 9l2.5 2L14 8l3 4"/></svg>',
    "แปลงและจัดการไฟล์": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/><path d="M9 14h6M12 11v6"/></svg>',
    "งานเอกสารครู": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M8 4h8a2 2 0 0 1 2 2v14l-6-3-6 3V6a2 2 0 0 1 2-2z"/><path d="M9 9h6M9 13h4"/></svg>',
    "งานวัดผลและผู้ปกครอง": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 19V9l4 3 4-6 4 4 4-2v11H4z"/><path d="M4 19h16"/></svg>',
}

# Colorful 3D group icons (from sprite sheet) — webp preferred, png fallback
GROUP_IMG = {
    "แผนการสอน": "plan",
    "สื่อการสอน": "media",
    "แปลงและจัดการไฟล์": "convert",
    "งานเอกสารครู": "docs",
    "งานวัดผลและผู้ปกครอง": "assess",
    "งานวัดผล": "assess",
    "สำหรับผู้ปกครอง/นักเรียน": "assess",
}
GROUP_TINT = {
    "plan": "#D8F3EC",      # soft teal
    "media": "#F0E6F6",    # soft purple
    "convert": "#DFF3F5",  # soft cyan
    "docs": "#FFE8D9",     # soft orange
    "assess": "#FFE8F0",   # soft pink
    "track": "#E3EEF9",    # soft blue
}
GROUP_TINT_ACCENT = {
    "plan": "#1A7A66",
    "media": "#7C3AED",
    "convert": "#0E7490",
    "docs": "#C2410C",
    "assess": "#DB2777",
    "track": "#2563EB",
}


def group_img_key(name: str) -> str:
    if name in GROUP_TINT:  # already a key like "plan" / "track"
        return name
    return GROUP_IMG.get(name, "plan")


def group_img_html(name: str, css_class: str = "gimg", size: int = 72) -> str:
    """Responsive <picture> for a group icon (Thai group name or key)."""
    key = group_img_key(name)
    base = f"/static/icons/groups/{key}"
    return (
        f'<picture class="{css_class}">'
        f'<source type="image/webp" srcset="{base}.webp">'
        f'<img src="{base}.png" width="{size}" height="{size}" alt="" loading="lazy" decoding="async">'
        f"</picture>"
    )


LOGO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="ครูดี">
  <rect width="64" height="64" rx="14" fill="#22A386"/>
  <path d="M45.31058020477816 22.040955631399317V46.0H37.44709897610922V22.839590443686006Q37.44709897610922 19.706484641638227 35.26621160409556 17.92491467576792Q33.08532423208191 16.14334470989761 29.27645051194539 16.14334470989761Q25.098976109215016 16.14334470989761 22.67235494880546 18.04778156996587Q20.245733788395903 19.95221843003413 20.245733788395903 23.331058020477816Q20.245733788395903 25.296928327645052 20.92150170648464 29.351535836177476Q21.965870307167236 25.726962457337883 24.085324232081913 23.73037542662116Q26.20477815699659 21.733788395904437 29.215017064846418 21.733788395904437Q32.225255972696246 21.733788395904437 33.91467576791809 23.26962457337884Q35.604095563139936 24.805460750853243 35.604095563139936 27.56996587030717Q35.604095563139936 30.273037542662117 34.00682593856656 31.80887372013652Q32.40955631399318 33.344709897610926 29.64505119453925 33.344709897610926Q28.2320819112628 33.344709897610926 27.034129692832764 32.85324232081911Q25.83617747440273 32.3617747440273 25.160409556313994 31.44027303754266Q24.177474402730375 32.85324232081911 23.563139931740615 34.91126279863481Q22.948805460750854 36.96928327645051 22.948805460750854 38.996587030716725V46.0H15.331058020477816V36.784982935153586Q15.331058020477816 35.43344709897611 14.16382252559727 31.255972696245735Q13.426621160409557 28.30716723549488 13.058020477815699 26.58703071672355Q12.689419795221843 24.86689419795222 12.689419795221843 23.392491467576793Q12.689419795221843 17.24914675767918 17.081911262798634 13.62457337883959Q21.474402730375427 10.0 29.27645051194539 10.0Q36.7098976109215 10.0 41.01023890784983 13.225255972696246Q45.31058020477816 16.450511945392492 45.31058020477816 22.040955631399317ZM27.003412969283275 27.50853242320819Q27.003412969283275 28.675767918088738 27.7098976109215 29.351535836177476Q28.41638225255973 30.027303754266214 29.522184300341298 30.027303754266214Q30.627986348122867 30.027303754266214 31.303754266211605 29.351535836177476Q31.97952218430034 28.675767918088738 31.97952218430034 27.50853242320819Q31.97952218430034 26.40273037542662 31.303754266211605 25.726962457337883Q30.627986348122867 25.05119453924915 29.522184300341298 25.05119453924915Q28.41638225255973 25.05119453924915 27.7098976109215 25.726962457337883Q27.003412969283275 26.40273037542662 27.003412969283275 27.50853242320819Z" fill="#FFFFFF"/>
  <polygon points="42.507,39.915 48.824,45.602 50.831,43.373 44.514,37.685" fill="#F2B61F"/>
  <polygon points="48.824,45.602 51.555,47.052 52.559,45.938 50.831,43.373" fill="#F5E6C8"/>
  <polygon points="51.555,47.052 53.543,47.833 52.559,45.938" fill="#4A3428"/>
</svg>'''


def group_icon(name):
    """Legacy line SVG (fallback). Prefer group_img_html for UI."""
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
        "og_image": SITE_URL + "/static/og-image.png?v=2",
    }
