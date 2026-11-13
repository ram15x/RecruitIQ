import io
import re
import zipfile

MAX_PAGES = 25


class UploadError(ValueError):
    pass


def _pdf(data: bytes) -> str:
    import pdfplumber
    parts = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:MAX_PAGES]:
                parts.append(page.extract_text() or "")
    except Exception as e:
        raise UploadError("could not read this PDF") from e
    return "\n".join(parts)


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "word/document.xml" not in z.namelist():
                raise UploadError("not a Word document")
            if z.getinfo("word/document.xml").file_size > 20_000_000:
                raise UploadError("document is too large to read")
            xml = z.read("word/document.xml").decode("utf8", "ignore")
    except zipfile.BadZipFile as e:
        raise UploadError("could not read this Word file") from e
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def extract(data: bytes, filename: str = "", max_bytes: int = 5_000_000) -> str:
    """Return plain text from a PDF, DOCX or text upload. The kind is decided by content, not by the file name."""
    if len(data) > max_bytes:
        raise UploadError(f"file is larger than {max_bytes // 1_000_000} MB")
    if data[:5] == b"%PDF-":
        text = _pdf(data)
    elif data[:2] == b"PK":
        text = _docx(data)
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise UploadError("unsupported file type, use PDF, DOCX or plain text") from e
    return text.replace("\x00", "").strip()
