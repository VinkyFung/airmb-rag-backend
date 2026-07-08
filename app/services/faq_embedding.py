from datetime import datetime
from hashlib import sha256

from qdrant_client.http import models
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.models.faq import KbFaq
from app.repositories.faq import FaqRepository
from app.schemas.embedding import (
    FaqEmbeddingData,
    FaqEmbeddingRebuildData,
    FaqEmbeddingRebuildItem,
    FaqSearchData,
    FaqSearchItem,
)
from app.services.embedding import embedding_service
from app.services.vector_store import vector_store_service


class FaqEmbeddingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = FaqRepository(session)

    async def generate_faq_embedding(self, faq_id: int) -> FaqEmbeddingData:
        faq = await self.repository.get_by_id(faq_id)
        if faq is None:
            raise BusinessError("FAQ 不存在或已删除", code="FAQ_NOT_FOUND", status_code=404)

        try:
            return await self._generate_for_faq(faq)
        except BusinessError:
            raise
        except Exception as exc:
            await self._mark_failed(faq_id, exc)
            raise BusinessError(
                "FAQ 向量生成失败，请检查 BGE-M3 模型、Qdrant 服务和网络配置",
                code="FAQ_EMBEDDING_FAILED",
                status_code=500,
            ) from exc

    async def rebuild_embeddings(
        self,
        *,
        limit: int,
        only_pending: bool,
    ) -> FaqEmbeddingRebuildData:
        faqs = await self.repository.list_embedding_candidates(
            limit=limit,
            only_pending=only_pending,
        )
        faq_ids = [faq.id for faq in faqs]
        items: list[FaqEmbeddingRebuildItem] = []

        for faq_id in faq_ids:
            try:
                faq = await self.repository.get_by_id(faq_id)
                if faq is None:
                    raise BusinessError(
                        "FAQ 不存在或已删除",
                        code="FAQ_NOT_FOUND",
                        status_code=404,
                    )
                await self._generate_for_faq(faq)
            except Exception as exc:
                await self._mark_failed(faq_id, exc)
                items.append(
                    FaqEmbeddingRebuildItem(
                        faq_id=faq_id,
                        success=False,
                        message=str(exc)[:500],
                    )
                )
                continue

            items.append(
                FaqEmbeddingRebuildItem(
                    faq_id=faq_id,
                    success=True,
                    message="向量生成成功",
                )
            )

        succeeded = sum(1 for item in items if item.success)
        failed = len(items) - succeeded
        return FaqEmbeddingRebuildData(
            total=len(items),
            succeeded=succeeded,
            failed=failed,
            items=items,
        )

    async def search_faqs(self, *, query: str, top_k: int) -> FaqSearchData:
        vector = await embedding_service.embed_text(query)
        results = await vector_store_service.search(
            vector=vector,
            top_k=top_k,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(key="biz_type", match=models.MatchValue(value="faq")),
                    models.FieldCondition(key="status", match=models.MatchValue(value=1)),
                ]
            ),
        )
        return FaqSearchData(
            query=query,
            top_k=top_k,
            items=[
                FaqSearchItem(
                    faq_id=int(item["payload"].get("faq_id") or item["id"]),
                    knowledge_id=item["payload"].get("knowledge_id"),
                    score=float(item["score"]),
                    standard_question=item["payload"].get("standard_question"),
                    answer=item["payload"].get("answer"),
                    category_l1=item["payload"].get("category_l1"),
                    category_l2=item["payload"].get("category_l2"),
                    category_l3=item["payload"].get("category_l3"),
                    status=item["payload"].get("status"),
                )
                for item in results
            ],
        )

    async def _generate_for_faq(self, faq: KbFaq) -> FaqEmbeddingData:
        paraphrases = (await self.repository.load_paraphrases([faq.id])).get(faq.id, [])
        embedding_text = build_faq_embedding_text(faq, paraphrases)
        embedding_input_hash = sha256(embedding_text.encode("utf-8")).hexdigest()
        vector = await embedding_service.embed_text(embedding_text)

        await vector_store_service.upsert_faq_vector(
            faq_id=faq.id,
            vector=vector,
            payload={
                "knowledge_id": faq.knowledge_id,
                "standard_question": faq.standard_question,
                "paraphrases": paraphrases,
                "answer": faq.answer,
                "category_l1": faq.category_l1,
                "category_l2": faq.category_l2,
                "category_l3": faq.category_l3,
                "user_role": faq.user_role,
                "business_type": faq.business_type,
                "risk_level": faq.risk_level,
                "auth_required": faq.auth_required,
                "auto_answer": faq.auto_answer,
                "human_required": faq.human_required,
                "status": faq.status,
                "embedding_input_hash": embedding_input_hash,
            },
        )

        latest = await self.repository.get_by_id(faq.id, for_update=True)
        if latest is None:
            raise BusinessError("FAQ 不存在或已删除", code="FAQ_NOT_FOUND", status_code=404)

        latest.embedding_status = 1
        latest.embedding_error = None
        latest.embedding_input_hash = embedding_input_hash
        latest.updated_at = datetime.now()

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return FaqEmbeddingData(
            faq_id=latest.id,
            knowledge_id=latest.knowledge_id,
            embedding_status=latest.embedding_status,
            embedding_input_hash=latest.embedding_input_hash,
            embedding_model=settings.embedding_model,
            embedding_dimension=settings.embedding_dimension,
        )

    async def _mark_failed(self, faq_id: int, exc: Exception) -> None:
        await self.session.rollback()
        faq = await self.repository.get_by_id(faq_id, for_update=True)
        if faq is None:
            return
        faq.embedding_status = 2
        faq.embedding_error = str(exc)[:2000]
        faq.updated_at = datetime.now()
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise


def build_faq_embedding_text(faq: KbFaq, paraphrases: list[str]) -> str:
    parts = [
        ("问题", faq.standard_question),
        ("相似问法", "；".join(paraphrases)),
        ("答案", faq.answer),
        ("一级分类", faq.category_l1),
        ("二级分类", faq.category_l2),
        ("三级分类", faq.category_l3),
        ("用户角色", faq.user_role),
        ("业务类型", faq.business_type),
    ]
    return "\n".join(f"{label}：{value}" for label, value in parts if value)
