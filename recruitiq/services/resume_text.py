import io
import zipfile

MAX_PAGES = 25


class UploadError(ValueError):
    pass


def _light(color) -> bool:
    """True for white or nearly white fill colours, in gray, RGB or CMYK."""
    if color is None:
        return False
    c = list(color) if isinstance(color, (list, tuple)) else [color]
    try:
        if len(c) == 1:
            return c[0] >= 0.92
        if len(c) == 3:
            return min(c) >= 0.92
        if len(c) == 4:
            return max(c) <= 0.08
    except TypeError:
        return False
    return False


def _hidden_chars(page) -> tuple[set, int]:
    """Characters a person cannot see: white on white, tiny, or off the page. White text on a dark box is a normal design and stays."""
    dark_boxes = [r for r in page.rects if r.get("fill") and not _light(r.get("non_stroking_color"))]
    hidden = set()
    for i, ch in enumerate(page.chars):
        if not ch["text"].strip():
            continue
        off = ch["x1"] < 0 or ch["x0"] > page.width or ch["bottom"] < 0 or ch["top"] > page.height
        tiny = ch.get("size", 10) < 3
        pale = _light(ch.get("non_stroking_color")) and not any(
            r["x0"] - 1 <= (ch["x0"] + ch["x1"]) / 2 <= r["x1"] + 1 and r["top"] - 1 <= (ch["top"] + ch["bottom"]) / 2 <= r["bottom"] + 1 for r in dark_boxes)
        if off or tiny or pale:
            hidden.add(i)
    return hidden, len(hidden)


def _pdf(data: bytes) -> tuple[str, list]:
    import pdfplumber
    parts, hidden_total = [], 0
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:MAX_PAGES]:
                bad, n = _hidden_chars(page)
                hidden_total += n
                if bad:
                    ids = {id(page.chars[i]) for i in bad}
                    page = page.filter(lambda o: o.get("object_type") != "char" or id(o) not in ids)
                parts.append(page.extract_text() or "")
    except Exception as e:
        raise UploadError("could not read this PDF") from e
    notes = [f"{hidden_total} characters were invisible on the page (white, tiny or off the page) and were left out of the text that was scored"] if hidden_total >= 10 else []
    return "\n".join(parts), notes


def _docx(data: bytes) -> tuple[str, list]:
    import docx
    from docx.oxml.ns import qn
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "word/document.xml" not in z.namelist():
                raise UploadError("not a Word document")
            if z.getinfo("word/document.xml").file_size > 20_000_000:
                raise UploadError("document is too large to read")
        d = docx.Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise UploadError("could not read this Word file") from e

    def shaded(el) -> bool:
        for anc in el.iterancestors():
            if anc.tag in (qn("w:p"), qn("w:tc")):
                pr = anc.find(qn("w:pPr") if anc.tag == qn("w:p") else qn("w:tcPr"))
                shd = pr.find(qn("w:shd")) if pr is not None else None
                if shd is not None and (shd.get(qn("w:fill")) or "auto").lower() not in ("auto", "ffffff", "fff"):
                    return True
        return False

    out, hidden = [], 0
    for p in d.element.body.iter(qn("w:p")):
        line = []
        for r in p.iter(qn("w:r")):
            t = "".join(x.text or "" for x in r.iter(qn("w:t")))
            pr = r.find(qn("w:rPr"))
            vanish = pr is not None and pr.find(qn("w:vanish")) is not None
            col = pr.find(qn("w:color")) if pr is not None else None
            white = col is not None and (col.get(qn("w:val")) or "").lower() in ("ffffff", "fff") and not shaded(r)
            size = pr.find(qn("w:sz")) if pr is not None else None
            tiny = size is not None and size.get(qn("w:val")) and int(size.get(qn("w:val"))) < 6  # half points, so under 3pt
            if vanish or white or tiny:
                hidden += len(t.strip())
                continue
            line.append(t)
        out.append("".join(line))
    notes = [f"{hidden} characters were hidden in the document (white, tiny or marked hidden) and were left out of the text that was scored"] if hidden >= 10 else []
    return "\n".join(out), notes


def extract_ex(data: bytes, filename: str = "", max_bytes: int = 5_000_000) -> tuple[str, list]:
    """Return plain text and any warnings about the file. The kind is decided by content, not by the file name."""
    if len(data) > max_bytes:
        raise UploadError(f"file is larger than {max_bytes // 1_000_000} MB")
    notes: list = []
    if data[:5] == b"%PDF-":
        text, notes = _pdf(data)
    elif data[:2] == b"PK":
        text, notes = _docx(data)
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise UploadError("unsupported file type, use PDF, DOCX or plain text") from e
    return text.replace("\x00", "").strip(), notes


def extract(data: bytes, filename: str = "", max_bytes: int = 5_000_000) -> str:
    return extract_ex(data, filename, max_bytes)[0]
