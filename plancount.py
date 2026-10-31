"""Estimate how many distinct lesson plans a source file (.docx/.pdf/.doc) contains.

Counts distinct numbers after 'แผนการจัดการเรียนรู้ที่' / 'แผนการสอนที่' / 'แผนที่'
(Thai or Arabic digits). Never raises; returns 1 when nothing can be extracted.
"""
import logging, os, re, shutil, subprocess

log = logging.getLogger("lp-web.plancount")
MAX_PLANS = 30
MAX_CHARS = 3_000_000
PDF_MAX_PAGES = 300
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
PLAN_RE = re.compile(r"แผน(?:การจัดการเรียนรู้|การเรียนรู้|การสอน)?\s*ที่\s*([0-9๐-๙]{1,3})(?![0-9๐-๙])")


def _docx_text(path):
    import docx  # python-docx
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs]

    def tables(ts, depth=0):
        for t in ts:
            for row in t.rows:
                for cell in row.cells:
                    parts.append(cell.text)
                    if depth < 3 and cell.tables:
                        tables(cell.tables, depth + 1)
    tables(d.tables)
    for s in d.sections:  # headers often carry 'แผนการจัดการเรียนรู้ที่ N'
        for hf in (s.header, s.first_page_header, s.even_page_header):
            try:
                if hf is not None and not hf.is_linked_to_previous:
                    parts.extend(p.text for p in hf.paragraphs)
            except Exception:
                pass
    return "\n".join(parts)


def _pdf_text(path):
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", "-l", str(PDF_MAX_PAGES), path, "-"],
                               capture_output=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace")
        except Exception as e:
            log.info("pdftotext failed: %s", e)
    from pypdf import PdfReader
    reader = PdfReader(path)
    out = []
    for i, page in enumerate(reader.pages):
        if i >= PDF_MAX_PAGES:
            break
        try:
            out.append(page.extract_text() or "")
        except Exception:
            pass
    return "\n".join(out)


def _doc_text(path):
    if shutil.which("antiword"):
        try:
            r = subprocess.run(["antiword", "-m", "UTF-8.txt", path], capture_output=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace")
        except Exception as e:
            log.info("antiword failed: %s", e)
    # Fallback without external tools: Word 97-2003 stores Unicode (Thai) text as UTF-16LE.
    with open(path, "rb") as f:
        raw = f.read(40 * 1024 * 1024)
    return raw.decode("utf-16-le", "ignore") + "\n" + raw[1:].decode("utf-16-le", "ignore")


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    fn = {".docx": _docx_text, ".pdf": _pdf_text, ".doc": _doc_text}.get(ext)
    return fn(path) if fn else ""


def count_plans_in_text(text):
    nums = set()
    for m in PLAN_RE.finditer(text[:MAX_CHARS]):
        n = int(m.group(1).translate(THAI_DIGITS))
        if 1 <= n <= 200:
            nums.add(n)
    return nums


def detect_plans(path):
    """(count, sorted plan numbers). count clamped 1..MAX_PLANS; never raises."""
    try:
        nums = sorted(count_plans_in_text(extract_text(path)))
        return max(1, min(MAX_PLANS, len(nums))), nums[:MAX_PLANS]
    except Exception as e:
        log.warning("plan detection failed for %s: %s", os.path.basename(path), e)
        return 1, []


def estimate_plan_count(path):
    """Distinct plan numbers in the file, clamped to 1..MAX_PLANS. Default 1; never raises."""
    try:
        nums = count_plans_in_text(extract_text(path))
        return max(1, min(MAX_PLANS, len(nums)))
    except Exception as e:
        log.warning("plan count failed for %s: %s", os.path.basename(path), e)
        return 1


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p, estimate_plan_count(p), sorted(count_plans_in_text(extract_text(p))))
