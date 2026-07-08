from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from qdrant_client import AsyncQdrantClient

from app.core.config import settings


def create_qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        timeout=settings.qdrant_timeout,
        check_compatibility=False,
        trust_env=False,
    )


@asynccontextmanager
async def qdrant_client_context() -> AsyncIterator[AsyncQdrantClient]:
    client = create_qdrant_client()
    try:
        yield client
    finally:
        await client.close()
