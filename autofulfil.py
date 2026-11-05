"""Instant server-side fulfilment for PDF merge / split / compress (pypdf)."""
import os, re, zipfile, tempfile, shutil

def _pdf_reader(path):
    from pypdf import PdfReader
    return PdfReader(path)


def _pdf_writer():
    from pypdf import PdfWriter
    return PdfWriter()


def merge_pdfs(paths, dest):
    writer = _pdf_writer()
    for p in paths:
        reader = _pdf_reader(p)
        for page in reader.pages:
            writer.add_page(page)
    with open(dest, "wb") as f:
        writer.write(f)
    return dest


def parse_ranges(spec, max_page):
    """Parse '1-3,5,8-10' (1-based inclusive) into sorted unique 0-based indexes."""
    pages = set()
    for part in (spec or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a), int(b)
            except ValueError:
                raise ValueError(f"ช่วงหน้าไม่ถูกต้อง: {part}")
            if start < 1 or end < start:
                raise ValueError(f"ช่วงหน้าไม่ถูกต้อง: {part}")
            for i in range(start, min(end, max_page) + 1):
                pages.add(i - 1)
        else:
            try:
                n = int(part)
            except ValueError:
                raise ValueError(f"เลขหน้าไม่ถูกต้อง: {part}")
            if n < 1 or n > max_page:
                raise ValueError(f"หน้า {n} อยู่นอกไฟล์ (มี {max_page} หน้า)")
            pages.add(n - 1)
    if not pages:
        raise ValueError("กรุณาระบุช่วงหน้า เช่น 1-3,5,8-10")
    return sorted(pages)


def split_pdf(path, ranges_spec, dest_dir):
    reader = _pdf_reader(path)
    n = len(reader.pages)
    indexes = parse_ranges(ranges_spec, n)
    os.makedirs(dest_dir, exist_ok=True)
    # Group contiguous ranges into separate files when possible; otherwise one page per file
    # Simpler: one PDF with selected pages + zip of individual pages if many
    writer = _pdf_writer()
    for i in indexes:
        writer.add_page(reader.pages[i])
    combined = os.path.join(dest_dir, "split.pdf")
    with open(combined, "wb") as f:
        writer.write(f)
    if len(indexes) == 1:
        return combined, None
    # Also zip individual pages for convenience
    zip_path = os.path.join(dest_dir, "split_pages.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in indexes:
            w = _pdf_writer()
            w.add_page(reader.pages[i])
            buf_name = f"page_{i + 1}.pdf"
            buf_path = os.path.join(dest_dir, buf_name)
            with open(buf_path, "wb") as f:
                w.write(f)
            zf.write(buf_path, buf_name)
            os.remove(buf_path)
    return combined, zip_path


def compress_pdf(path, dest):
    """Best-effort rewrite with content stream compression."""
    reader = _pdf_reader(path)
    writer = _pdf_writer()
    for page in reader.pages:
        try:
            page.compress_content_streams()
        except Exception:
            pass
        writer.add_page(page)
    try:
        writer.compress_identical_objects = True
    except Exception:
        pass
    with open(dest, "wb") as f:
        writer.write(f)
    # If somehow larger, keep original copy
    if os.path.getsize(dest) > os.path.getsize(path):
        shutil.copy2(path, dest)
    return dest


def run_auto(job, job_dir):
    """Execute auto fulfilment for pdf_merge / pdf_split / pdf_compress.
    Returns list of (stored_name, kind) result files. Raises ValueError on bad input."""
    sid = job.get("service_id")
    files = job.get("files") or {}
    inputs = job.get("inputs") or {}

    if sid == "pdf_merge":
        sources = []
        # Multi-file: source_0.pdf, source_1.pdf, ... or list in files["uploads"]
        uploads = files.get("uploads") or []
        if uploads:
            for u in uploads:
                sources.append(os.path.join(job_dir, u["stored"]))
        elif files.get("source"):
            sources.append(os.path.join(job_dir, files["source"]))
        # Also pick source_*.pdf pattern
        if not sources:
            for name in sorted(os.listdir(job_dir)):
                if re.match(r"source(_\d+)?\.pdf$", name, re.I):
                    sources.append(os.path.join(job_dir, name))
        if len(sources) < 1:
            raise ValueError("ไม่พบไฟล์ PDF ที่จะรวม")
        if len(sources) == 1:
            # still "merge" of one file — just copy
            dest = os.path.join(job_dir, "result.pdf")
            shutil.copy2(sources[0], dest)
        else:
            dest = os.path.join(job_dir, "result.pdf")
            merge_pdfs(sources, dest)
        return [("result.pdf", "pdf")]

    if sid == "pdf_split":
        src_name = files.get("source")
        if not src_name:
            raise ValueError("ไม่พบไฟล์ PDF")
        src = os.path.join(job_dir, src_name)
        ranges = (inputs.get("ranges") or "").strip()
        if not ranges:
            n = len(_pdf_reader(src).pages)
            ranges = f"1-{n}" if n else "1"
        combined, zipped = split_pdf(src, ranges, job_dir)
        out = [("result.pdf", "pdf")]
        # rename combined to result.pdf
        if combined != os.path.join(job_dir, "result.pdf"):
            shutil.move(combined, os.path.join(job_dir, "result.pdf"))
        if zipped:
            dest_zip = os.path.join(job_dir, "result.zip")
            if zipped != dest_zip:
                shutil.move(zipped, dest_zip)
            out.append(("result.zip", "zip"))
        return out

    if sid == "pdf_compress":
        src_name = files.get("source")
        if not src_name:
            raise ValueError("ไม่พบไฟล์ PDF")
        dest = os.path.join(job_dir, "result.pdf")
        compress_pdf(os.path.join(job_dir, src_name), dest)
        return [("result.pdf", "pdf")]

    raise ValueError(f"ไม่รองรับการทำอัตโนมัติสำหรับบริการ {sid}")
