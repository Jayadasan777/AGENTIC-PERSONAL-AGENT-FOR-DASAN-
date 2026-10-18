"""Recursive text chunker preserving citation metadata (page, section, sequence).

Splits text hierarchically across paragraph boundaries, newlines, sentence terminators,
and words while respecting chunk size and chunk overlap constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.services.document_parser import ParsedSection


@dataclass
class ChunkItem:
    """Individual text chunk ready for vector embedding and storage."""

    content: str
    chunk_index: int
    token_count: int
    page_number: int | None = None
    section_heading: str | None = None


class RecursiveTextChunker:
    """Hierarchical text chunker maintaining context boundaries."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""]

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text into segments within target chunk size."""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        if not separators:
            # Fallback hard slice
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

        sep = separators[0]
        remaining_seps = separators[1:]

        if sep == "":
            splits = list(text)
        else:
            splits = text.split(sep)

        chunks: list[str] = []
        current = ""

        for part in splits:
            candidate = f"{current}{sep}{part}" if current else part
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                if len(part) > self.chunk_size:
                    # Recurse with deeper separator
                    sub_chunks = self._split_text(part, remaining_seps)
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current and current.strip():
            chunks.append(current.strip())

        return chunks

    def chunk_sections(self, sections: list[ParsedSection]) -> list[ChunkItem]:
        """Convert a list of parsed document sections into sequenced chunk items."""
        chunk_items: list[ChunkItem] = []
        global_index = 0

        for section in sections:
            raw_chunks = self._split_text(section.content, self._separators)

            # Apply overlap if chunks exist
            processed_chunks: list[str] = []
            for i, chunk in enumerate(raw_chunks):
                if i > 0 and self.chunk_overlap > 0:
                    prev_tail = raw_chunks[i - 1][-self.chunk_overlap :]
                    # Ensure we don't duplicate exact prefix
                    if not chunk.startswith(prev_tail):
                        chunk = f"{prev_tail} {chunk}"
                processed_chunks.append(chunk)

            for text_chunk in processed_chunks:
                cleaned = text_chunk.strip()
                if not cleaned:
                    continue

                # Rough token estimation (whitespace words)
                token_count = len(re.findall(r"\w+", cleaned))

                chunk_items.append(
                    ChunkItem(
                        content=cleaned,
                        chunk_index=global_index,
                        token_count=token_count,
                        page_number=section.page_number,
                        section_heading=section.section_heading,
                    )
                )
                global_index += 1

        return chunk_items
