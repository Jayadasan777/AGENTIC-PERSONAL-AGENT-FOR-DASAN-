"""API v1 endpoints for Document Intelligence and RAG.

Enforces strict tenant isolation: every operation requires an authenticated user,
and document/chunk items are verified against the requester's ID before any read/write.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies.auth import get_current_active_user
from backend.app.api.v1.schemas.document import (
    DocumentChunkResponse,
    DocumentResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)
from backend.app.core.config import settings
from backend.app.db.session import get_async_session
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.user import User
from backend.app.services.document_parser import (
    DocumentValidationError,
    compute_sha256,
    sanitize_filename,
    validate_file_signature,
)
from backend.app.services.rag import RAGService

router = APIRouter(prefix="/documents", tags=["documents"])
_rag_service = RAGService()


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and index a document for RAG",
)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DocumentResponse:
    """Upload a PDF, DOCX, or text document, validate magic bytes, and index for RAG."""
    filename = file.filename or "uploaded_document.txt"
    safe_filename = sanitize_filename(filename)

    # 1. Read content
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES} bytes",
        )

    # 2. Magic byte security validation
    try:
        mime_type = validate_file_signature(content, safe_filename)
    except DocumentValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    # 3. Compute hash and store file locally
    sha256 = compute_sha256(content)
    doc_id = uuid.uuid4()
    storage_dir = settings.STORAGE_LOCAL_DIR
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, f"{doc_id}_{safe_filename}")

    try:
        with open(storage_path, "wb") as f:
            f.write(content)
    except OSError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist file: {err}",
        ) from err

    # 4. Insert Document record
    document = Document(
        id=doc_id,
        user_id=current_user.id,
        filename=safe_filename,
        storage_path=storage_path,
        mime_type=mime_type,
        file_size_bytes=len(content),
        sha256_hash=sha256,
        status="pending",
        total_chunks=0,
        is_deleted=False,
    )
    session.add(document)
    await session.flush()

    # 5. Parse, chunk, embed and store chunks
    await _rag_service.index_document_content(session, document, content)
    await session.commit()
    await session.refresh(document)

    return DocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="List all indexed documents for current user",
)
async def list_documents(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentResponse]:
    """Retrieve metadata of all active documents owned by the caller."""
    stmt = (
        select(Document)
        .where(
            Document.user_id == current_user.id,
            Document.is_deleted.is_(False),
        )
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get single document status and metadata",
)
async def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DocumentResponse:
    """Fetch metadata for a single document owned by the caller."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
        Document.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse.model_validate(doc)


@router.get(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkResponse],
    summary="List chunks for a document with citation metadata",
)
async def list_document_chunks(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[DocumentChunkResponse]:
    """Retrieve all chunks belonging to a document, preserving page and section citations."""
    # Ensure document exists and belongs to current user
    doc_stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
        Document.is_deleted.is_(False),
    )
    doc_res = await session.execute(doc_stmt)
    if doc_res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    chunk_stmt = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.user_id == current_user.id,
            DocumentChunk.is_deleted.is_(False),
        )
        .order_by(DocumentChunk.chunk_index.asc())
    )
    chunk_res = await session.execute(chunk_stmt)
    chunks = chunk_res.scalars().all()
    return [DocumentChunkResponse.model_validate(c) for c in chunks]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its indexed chunks",
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    hard: bool = Query(default=False, description="Perform hard delete if true"),
) -> None:
    """Delete a document and cascade to all associated chunks."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
        Document.is_deleted.is_(False),
    )
    res = await session.execute(stmt)
    doc = res.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if hard:
        if os.path.exists(doc.storage_path):
            try:
                os.remove(doc.storage_path)
            except OSError:
                pass
        await session.delete(doc)
    else:
        doc.is_deleted = True
        # Mark all chunks deleted as well
        await session.execute(
            update(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .values(is_deleted=True)
        )

    await session.commit()


@router.post(
    "/rag/query",
    response_model=RAGQueryResponse,
    summary="Query RAG across indexed documents with citations",
)
async def query_rag(
    body: RAGQueryRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> RAGQueryResponse:
    """Perform hybrid retrieval and citation-grounded LLM question answering."""
    result = await _rag_service.query_rag(
        session=session,
        user_id=current_user.id,
        query=body.query,
        limit=body.limit,
        threshold=body.threshold,
    )
    return RAGQueryResponse.model_validate(result)
