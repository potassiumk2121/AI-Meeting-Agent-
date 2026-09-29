import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    for statement in (
        """
        CREATE INDEX IF NOT EXISTS ix_embedding_chunks_hnsw
        ON embedding_chunks USING hnsw (embedding vector_cosine_ops)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_embedding_chunks_fts
        ON embedding_chunks USING gin (to_tsvector('english', content))
        """,
        "ALTER TABLE speaker_profiles ADD COLUMN IF NOT EXISTS voice VARCHAR(300)",
    ):
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement))
        except Exception:
            logger.warning("optional index was not created", exc_info=True)


async def ping_db() -> None:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
