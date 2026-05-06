"""Tests for the documents API — focused on PR S7 additions: tags + ingestion timing."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.collection import Collection
from src.models.document import Document
from src.models.ingestion_job import IngestionJob
from src.storage.database import Base


@pytest.fixture
async def seeded_db():
    """Set up a fresh in-memory DB with one collection and yield a session factory."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        col = Collection(name="exp-corpus", description="Experiment papers")
        session.add(col)
        await session.flush()
        await session.commit()
        col_id = col.id

    yield engine, session_factory, col_id

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


class TestDocumentTagsRoundTrip:
    async def test_tags_persisted_and_returned_via_response_projection(self, seeded_db):
        from src.api.routes.documents import _build_document_response

        _, session_factory, col_id = seeded_db
        tags = {
            "domain": "ai-ethics-law",
            "role": "Anchor",
            "year": 2026,
            "authors": "Stober & Dornis",
        }

        async with session_factory() as session:
            doc = Document(
                collection_id=col_id,
                filename="stober_dornis_2026.pdf",
                tags=tags,
                status="completed",
            )
            session.add(doc)
            await session.flush()
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            stored = (await session.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            response = await _build_document_response(session, stored)

        assert response.tags == tags

    async def test_tags_default_to_none_when_unset(self, seeded_db):
        from src.api.routes.documents import _build_document_response

        _, session_factory, col_id = seeded_db
        async with session_factory() as session:
            doc = Document(collection_id=col_id, filename="untagged.pdf", status="completed")
            session.add(doc)
            await session.flush()
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            stored = (await session.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            response = await _build_document_response(session, stored)

        assert response.tags is None


class TestIngestionTimingExposure:
    async def test_ingestion_seconds_computed_from_latest_job(self, seeded_db):
        from src.api.routes.documents import _build_document_response

        _, session_factory, col_id = seeded_db
        started = datetime(2026, 5, 4, 12, 0, 0)
        completed = started + timedelta(seconds=47.2)

        async with session_factory() as session:
            doc = Document(collection_id=col_id, filename="paper.pdf", status="completed")
            session.add(doc)
            await session.flush()
            job = IngestionJob(
                document_id=doc.id,
                parser="docling",
                chunk_size=512,
                chunk_overlap=50,
                contextual_enrichment=True,
                started_at=started,
                completed_at=completed,
                status="complete",
            )
            session.add(job)
            await session.flush()
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            stored = (await session.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            response = await _build_document_response(session, stored)

        assert response.ingestion_started_at == started
        assert response.ingestion_completed_at == completed
        assert response.ingestion_seconds == pytest.approx(47.2)

    async def test_ingestion_seconds_none_when_job_incomplete(self, seeded_db):
        from src.api.routes.documents import _build_document_response

        _, session_factory, col_id = seeded_db
        async with session_factory() as session:
            doc = Document(collection_id=col_id, filename="paper.pdf", status="processing")
            session.add(doc)
            await session.flush()
            job = IngestionJob(
                document_id=doc.id,
                parser="docling",
                chunk_size=512,
                chunk_overlap=50,
                contextual_enrichment=True,
                started_at=datetime(2026, 5, 4, 12, 0, 0),
                completed_at=None,
                status="running",
            )
            session.add(job)
            await session.flush()
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            stored = (await session.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            response = await _build_document_response(session, stored)

        assert response.ingestion_seconds is None
        assert response.ingestion_completed_at is None

    async def test_ingestion_seconds_none_when_no_job(self, seeded_db):
        from src.api.routes.documents import _build_document_response

        _, session_factory, col_id = seeded_db
        async with session_factory() as session:
            doc = Document(collection_id=col_id, filename="orphan.pdf", status="pending")
            session.add(doc)
            await session.flush()
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            stored = (await session.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            response = await _build_document_response(session, stored)

        assert response.ingestion_started_at is None
        assert response.ingestion_seconds is None


class TestIngestionTokenExposure:
    """Enrichment-token totals on the latest IngestionJob surface in DocumentResponse."""

    async def test_tokens_surface_when_present(self, seeded_db):
        from src.api.routes.documents import _build_document_response

        _, session_factory, col_id = seeded_db
        async with session_factory() as session:
            doc = Document(collection_id=col_id, filename="paper.pdf", status="completed")
            session.add(doc)
            await session.flush()
            job = IngestionJob(
                document_id=doc.id,
                parser="docling",
                chunk_size=512,
                chunk_overlap=50,
                contextual_enrichment=True,
                started_at=datetime(2026, 5, 4, 12, 0, 0),
                completed_at=datetime(2026, 5, 4, 12, 0, 30),
                status="complete",
                prompt_tokens=12345,
                completion_tokens=678,
            )
            session.add(job)
            await session.flush()
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            stored = (await session.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            response = await _build_document_response(session, stored)

        assert response.ingestion_prompt_tokens == 12345
        assert response.ingestion_completion_tokens == 678

    async def test_tokens_none_when_enrichment_disabled(self, seeded_db):
        from src.api.routes.documents import _build_document_response

        _, session_factory, col_id = seeded_db
        async with session_factory() as session:
            doc = Document(collection_id=col_id, filename="paper.pdf", status="completed")
            session.add(doc)
            await session.flush()
            job = IngestionJob(
                document_id=doc.id,
                parser="docling",
                chunk_size=512,
                chunk_overlap=50,
                contextual_enrichment=False,
                started_at=datetime(2026, 5, 4, 12, 0, 0),
                completed_at=datetime(2026, 5, 4, 12, 0, 30),
                status="complete",
            )
            session.add(job)
            await session.flush()
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            stored = (await session.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            response = await _build_document_response(session, stored)

        assert response.ingestion_prompt_tokens is None
        assert response.ingestion_completion_tokens is None
