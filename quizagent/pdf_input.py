"""PDF validation + text extraction. Text-based PDFs only: the text is extracted here and
only the text is sent to the AI."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from functools import cached_property

from pypdf import PdfReader
from pypdf.errors import DependencyError, PyPdfError

MAX_TEXT_CHARS = 200_000
MIN_TEXT_CHARS = 400


class PdfError(ValueError):
    """A problem with the uploaded file that the user can fix. The message is safe to show."""


def normalize_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class SourceMaterial:
    filename: str
    page_count: int
    text: str
    truncated: bool = False

    @cached_property
    def token_set(self) -> frozenset[str]:
        return frozenset(normalize_tokens(self.text))


def load_pdf(data: bytes, filename: str, *, max_mb: int = 25, max_pages: int = 60) -> SourceMaterial:
    if len(data) > max_mb * 1024 * 1024:
        raise PdfError(f"That file is larger than {max_mb} MB. Compress it or upload a shorter extract.")
    if not data.startswith(b"%PDF"):
        raise PdfError("That doesn't look like a PDF. Upload a file that ends in .pdf.")
    try:
        reader = PdfReader(io.BytesIO(data))
        # Many university PDFs are "encrypted" only to block printing; they open with an empty password.
        if reader.is_encrypted and int(reader.decrypt("")) == 0:
            raise PdfError("That PDF needs a password to open. Remove the password and upload it again.")
        pages = len(reader.pages)
        if pages == 0:
            raise PdfError("That PDF has no pages.")
        if pages > max_pages:
            raise PdfError(f"That PDF has {pages} pages; the limit is {max_pages}. Upload a shorter extract.")
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except PdfError:
        raise
    except (PyPdfError, DependencyError, ValueError, OSError, KeyError, ImportError) as exc:
        raise PdfError("I couldn't read that PDF. It may be damaged or use unsupported encryption.") from exc

    if len(text) < MIN_TEXT_CHARS:
        raise PdfError(
            "I couldn't find enough selectable text in that PDF. It may be a scan or a set of images. "
            "Upload a text-based PDF, one where you can select and copy the words."
        )
    return SourceMaterial(filename, pages, text[:MAX_TEXT_CHARS], truncated=len(text) > MAX_TEXT_CHARS)
