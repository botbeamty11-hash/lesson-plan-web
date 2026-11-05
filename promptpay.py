"""PromptPay EMVCo QR helpers (generate + best-effort decode). Soft-fail if libs missing."""
from __future__ import annotations

import re


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for ch in data.encode("ascii"):
        crc ^= ch << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def normalize_promptpay_id(raw: str) -> str | None:
    """Return digits-only PromptPay target, or None if empty/invalid."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw.strip())
    if not digits:
        return None
    # Thai mobile: 0XXXXXXXXX (10 digits) -> 0066XXXXXXXXX
    if len(digits) == 10 and digits.startswith("0"):
        return "0066" + digits[1:]
    # Already 0066... or national ID (13) or e-wallet
    if len(digits) in (13, 15) or (len(digits) >= 11 and digits.startswith("0066")):
        return digits
    if len(digits) >= 9:
        return digits
    return None


def build_payload(promptpay_id: str, amount: float | None = None) -> str | None:
    """Build a PromptPay QR payload string. amount=None -> static QR (no amount)."""
    target = normalize_promptpay_id(promptpay_id)
    if not target:
        return None
    if len(target) == 13 and not target.startswith("0066"):
        # National ID / tax ID
        merchant = _tlv("29", _tlv("00", "A000000677010111") + _tlv("02", target))
    else:
        merchant = _tlv("29", _tlv("00", "A000000677010111") + _tlv("01", target))
    poi = "12" if amount is not None else "11"
    parts = [
        _tlv("00", "01"),
        _tlv("01", poi),
        merchant,
        _tlv("53", "764"),
        _tlv("58", "TH"),
    ]
    if amount is not None:
        parts.insert(-1, _tlv("54", f"{float(amount):.2f}"))
    body = "".join(parts) + "6304"
    return body + _crc16_ccitt(body)


def _read_tlv(s: str, i: int):
    if i + 4 > len(s):
        return None, None, i
    tag, ln = s[i:i+2], int(s[i+2:i+4])
    val = s[i+4:i+4+ln]
    if len(val) != ln:
        return None, None, i
    return tag, val, i + 4 + ln


def extract_promptpay_id_from_payload(payload: str) -> str | None:
    """Best-effort: pull mobile/national ID from a PromptPay EMVCo payload."""
    if not payload:
        return None
    i = 0
    while i + 4 <= len(payload):
        tag, val, nxt = _read_tlv(payload, i)
        if tag is None:
            break
        if tag in ("29", "30") and "A0000006770101" in val:
            j = 0
            while j + 4 <= len(val):
                t2, v2, j2 = _read_tlv(val, j)
                if t2 is None:
                    break
                if t2 in ("01", "02") and v2:
                    return v2
                j = j2
        i = nxt
    return None


def generate_qr_png(promptpay_id: str, dest_path: str, amount: float | None = None) -> bool:
    """Write a PNG QR to dest_path. Returns False if qrcode missing or id invalid."""
    payload = build_payload(promptpay_id, amount)
    if not payload:
        return False
    try:
        import qrcode
    except ImportError:
        return False
    img = qrcode.make(payload)
    img.save(dest_path)
    return True


def decode_qr_from_image(path: str) -> list[str]:
    """Return list of decoded QR payload strings. Empty if libs/image unavailable."""
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode as zbar_decode
    except ImportError:
        return []
    try:
        img = Image.open(path)
        results = zbar_decode(img)
        out = []
        for r in results:
            try:
                out.append(r.data.decode("utf-8", "replace"))
            except Exception:
                pass
        return out
    except Exception:
        return []
