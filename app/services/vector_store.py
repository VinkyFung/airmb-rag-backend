from typing import Any

from qdrant_client.http import models

from app.core.config import settings
from app.core.vector_db import qdrant_client_context


class VectorStoreService:
    async def health(self) -> dict[str, Any]:
        async with qdrant_client_context() as client:
            collections = await client.get_collections()
            names = [item.name for item in collections.collections]
            return {
                "provider": settings.vector_db_provider,
                "url": settings.qdrant_url,
                "collection": settings.qdrant_collection,
                "collection_exists": settings.qdrant_collection in names,
                "embedding_model": settings.embedding_model,
                "embedding_dimension": settings.embedding_dimension,
                "collections": names,
            }

    async def ensure_collection(self) -> dict[str, Any]:
        async with qdrant_client_context() as client:
            collections = await client.get_collections()
            names = {item.name for item in collections.collections}
            created = settings.qdrant_collection not in names

            if created:
                await client.create_collection(
                    collection_name=settings.qdrant_collection,
                    vectors_config=models.VectorParams(
                        size=settings.embedding_dimension,
                        distance=models.Distance.COSINE,
                    ),
                )

            return {
                "provider": settings.vector_db_provider,
                "collection": settings.qdrant_collection,
                "created": created,
                "embedding_dimension": settings.embedding_dimension,
                "distance": models.Distance.COSINE.value,
            }

    async def upsert_faq_vector(
        self,
        *,
        faq_id: int,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        await self.ensure_collection()
        async with qdrant_client_context() as client:
            await client.upsert(
                collection_name=settings.qdrant_collection,
                points=[
                    models.PointStruct(
                        id=faq_id,
                        vector=vector,
                        payload={
                            **payload,
                            "biz_type": "faq",
                            "faq_id": faq_id,
                            "embedding_model": settings.embedding_model,
                            "embedding_dimension": settings.embedding_dimension,
                        },
                    )
                ],
            )

    async def delete_faq_vector(self, faq_id: int) -> None:
        await self.ensure_collection()
        async with qdrant_client_context() as client:
            await client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=models.PointIdsList(points=[faq_id]),
            )

    async def search(
        self,
        *,
        vector: list[float],
        top_k: int = 5,
        query_filter: models.Filter | None = None,
    ) -> list[dict[str, Any]]:
        await self.ensure_collection()
        async with qdrant_client_context() as client:
            results = await client.query_points(
                collection_name=settings.qdrant_collection,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            return [
                {
                    "id": item.id,
                    "score": item.score,
                    "payload": item.payload or {},
                }
                for item in results.points
            ]


vector_store_service = VectorStoreService()
