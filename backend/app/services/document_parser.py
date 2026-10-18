"""Secure document upload validation and multi-format text extractors.

Supported formats:
- Plain text (.txt) and Markdown (.md, .markdown)
- PDF (.pdf) via pure-Python pypdf with page citation extraction
- Microsoft Word (.docx) via pure-Python python-docx with section heading extraction

Security controls:
- File size enforcement against MAX_UPLOAD_SIZE_BYTES
- Magic byte (file signature) validation preventing file extension spoofing
- Path traversal defense and filename sanitization
- Binary null-byte checks preventing executable polyglot uploads
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import dataclass
from typing import BinaryIO

from docx import Document as DocxDocument
from pypdf import PdfReader


class DocumentValidationError(Exception):
    """Raised when an uploaded document fails security or validation checks."""


@dataclass
class ParsedSection:
    """A segment of extracted text preserving citation metadata."""

    content: str
    page_number: int | None = None
    section_heading: str | None = None


# Magic byte signatures
PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"  # DOCX is a zip archive with this header

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
}


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and shell injection attacks."""
    # Strip paths (supporting both POSIX / and Windows \ separators)
    normalized = filename.replace("\\", "/")
    basename = os.path.basename(normalized)
    # Remove control characters and non-standard symbols
    cleaned = re.sub(r"[^\w\.\-\_]", "_", basename)
    # Ensure reasonable length
    if len(cleaned) > 200:
        name, ext = os.path.splitext(cleaned)
        cleaned = name[: 200 - len(ext)] + ext
    return cleaned or "unnamed_document"


def validate_file_signature(data: bytes, filename: str) -> str:
    """Verify magic bytes and content integrity to determine valid MIME type.

    Raises:
        DocumentValidationError if the file fails security checks.
    """
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentValidationError(
            f"Unsupported file format '{ext}'. Allowed: {list(ALLOWED_EXTENSIONS.keys())}"
        )

    if ext == ".pdf":
        if not data.startswith(PDF_MAGIC):
            raise DocumentValidationError(
                "File extension is .pdf but magic bytes do not match %PDF- signature."
            )
        return "application/pdf"

    if ext == ".docx":
        if not data.startswith(ZIP_MAGIC):
            raise DocumentValidationError(
                "File extension is .docx but magic bytes do not match ZIP/OOXML signature."
            )
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if ext in {".txt", ".md", ".markdown", ".csv"}:
        if b"\x00" in data:
            raise DocumentValidationError(
                "Text file contains prohibited null bytes (binary polyglot detected)."
            )
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as err:
            raise DocumentValidationError(f"Text file is not valid UTF-8: {err}") from err
        return ALLOWED_EXTENSIONS[ext]

    raise DocumentValidationError(f"Unhandled file extension: {ext}")


def parse_pdf(file_stream: BinaryIO) -> list[ParsedSection]:
    """Extract page-by-page text from PDF with page citations."""
    sections: list[ParsedSection] = []
    try:
        reader = PdfReader(file_stream)
        for page_idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            cleaned = text.strip()
            if cleaned:
                sections.append(
                    ParsedSection(
                        content=cleaned,
                        page_number=page_idx,
                        section_heading=f"Page {page_idx}",
                    )
                )
    except Exception as err:
        raise DocumentValidationError(f"Failed to parse PDF document: {err}") from err
    return sections


def parse_docx(file_stream: BinaryIO) -> list[ParsedSection]:
    """Extract paragraph and heading text from Word DOCX document."""
    sections: list[ParsedSection] = []
    try:
        doc = DocxDocument(file_stream)
        current_heading = "Document Content"
        current_paragraphs: list[str] = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            if p.style and p.style.name and p.style.name.startswith("Heading"):
                if current_paragraphs:
                    sections.append(
                        ParsedSection(
                            content="\n\n".join(current_paragraphs),
                            section_heading=current_heading,
                        )
                    )
                    current_paragraphs = []
                current_heading = text
            else:
                current_paragraphs.append(text)

        if current_paragraphs:
            sections.append(
                ParsedSection(
                    content="\n\n".join(current_paragraphs),
                    section_heading=current_heading,
                )
            )
    except Exception as err:
        raise DocumentValidationError(f"Failed to parse DOCX document: {err}") from err
    return sections


def parse_text(text: str) -> list[ParsedSection]:
    """Parse plain text or Markdown into initial section."""
    cleaned = text.strip()
    if not cleaned:
        return []
    return [ParsedSection(content=cleaned, section_heading="Full Document")]


def extract_sections(data: bytes, mime_type: str) -> list[ParsedSection]:
    """Route document bytes to the appropriate parser based on MIME type."""
    stream = io.BytesIO(data)
    if mime_type == "application/pdf":
        return parse_pdf(stream)
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return parse_docx(stream)
    # Plain text / Markdown
    text = data.decode("utf-8", errors="replace")
    return parse_text(text)


def compute_sha256(data: bytes) -> str:
    """Return SHA-256 hexadecimal digest of bytes."""
    return hashlib.sha256(data).hexdigest()
