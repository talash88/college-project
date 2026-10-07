from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


async def check_database_connection(session: AsyncSession) -> bool:
    try:
        result = await session.execute(text("SELECT 1"))
        return result.scalar() == 1
    except SQLAlchemyError:
        return False


async def check_pgvector_available(session: AsyncSession) -> bool:
    try:
        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        return result.scalar() is not None
    except SQLAlchemyError:
        return False
