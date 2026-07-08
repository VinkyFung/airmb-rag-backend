import json
from datetime import datetime
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.faq import KbFaq
from app.repositories.faq import FaqRepository
from app.schemas.common import PageMeta
from app.schemas.faq import FaqDeleteData, FaqItem, FaqListData, FaqUpdate


class FaqService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = FaqRepository(session)

    async def list_faqs(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        category_l1: str | None,
        status: int | None,
    ) -> FaqListData:
        faqs, total, paraphrases = await self.repository.list(
            page=page,
            page_size=page_size,
            keyword=keyword,
            category_l1=category_l1,
            status=status,
        )
        return FaqListData(
            items=[self._to_item(faq, paraphrases.get(faq.id, [])) for faq in faqs],
            pagination=PageMeta(page=page, page_size=page_size, total=total),
        )

    async def update_faq(self, faq_id: int, payload: FaqUpdate) -> FaqItem:
        faq = await self.repository.get_by_id(faq_id, for_update=True)
        if faq is None:
            raise BusinessError("FAQ 不存在或已删除", code="FAQ_NOT_FOUND", status_code=404)
        if faq.version != payload.version:
            raise BusinessError(
                "FAQ 已被其他人更新，请刷新后重试",
                code="FAQ_VERSION_CONFLICT",
                status_code=409,
            )

        now = datetime.now()
        self._apply_update(faq, payload, now)
        await self.repository.replace_paraphrases(
            faq_id=faq.id,
            values=payload.paraphrases,
            updated_by=payload.updated_by,
            now=now,
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._to_item(faq, payload.paraphrases)

    async def delete_faq(self, faq_id: int, *, updated_by: str) -> FaqDeleteData:
        faq = await self.repository.get_by_id(faq_id, for_update=True)
        if faq is None:
            raise BusinessError("FAQ 不存在或已删除", code="FAQ_NOT_FOUND", status_code=404)

        now = datetime.now()
        faq.status = 2
        faq.auto_answer = False
        faq.version += 1
        faq.updated_by = updated_by
        faq.updated_at = now
        faq.deleted_at = now
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return FaqDeleteData(id=faq.id, status=faq.status)

    @staticmethod
    def _apply_update(faq: KbFaq, payload: FaqUpdate, now: datetime) -> None:
        faq.category_l1 = payload.category_l1
        faq.category_l2 = payload.category_l2
        faq.category_l3 = payload.category_l3
        faq.standard_question = payload.standard_question
        faq.answer = payload.answer
        faq.user_role = payload.user_role
        faq.business_type = payload.business_type
        faq.risk_level = payload.risk_level
        faq.auth_required = payload.auth_required
        faq.auto_answer = payload.auto_answer
        faq.human_required = payload.human_required
        faq.status = payload.status
        faq.review_status = payload.review_status
        faq.version += 1
        faq.updated_by = payload.updated_by
        faq.updated_at = now
        faq.embedding_status = 0
        faq.embedding_error = None

        content = {
            "category_l1": payload.category_l1,
            "category_l2": payload.category_l2,
            "category_l3": payload.category_l3,
            "standard_question": payload.standard_question,
            "answer": payload.answer,
            "user_role": payload.user_role,
            "business_type": payload.business_type,
            "risk_level": payload.risk_level,
            "auth_required": payload.auth_required,
            "auto_answer": payload.auto_answer,
            "human_required": payload.human_required,
            "status": payload.status,
        }
        faq.content_hash = FaqService._hash_json(content)
        faq.embedding_input_hash = FaqService._hash_json(
            {
                "categories": [
                    payload.category_l1,
                    payload.category_l2,
                    payload.category_l3,
                ],
                "question": payload.standard_question,
                "paraphrases": payload.paraphrases,
                "answer": payload.answer,
            }
        )

    @staticmethod
    def _hash_json(value: object) -> str:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_item(faq: KbFaq, paraphrases: list[str]) -> FaqItem:
        return FaqItem(
            id=faq.id,
            knowledge_id=faq.knowledge_id,
            version=faq.version,
            category_l1=faq.category_l1,
            category_l2=faq.category_l2,
            category_l3=faq.category_l3,
            standard_question=faq.standard_question,
            paraphrases=paraphrases,
            answer=faq.answer,
            user_role=faq.user_role,
            business_type=faq.business_type,
            risk_level=faq.risk_level,
            auth_required=faq.auth_required,
            auto_answer=faq.auto_answer,
            human_required=faq.human_required,
            status=faq.status,
            review_status=faq.review_status,
            embedding_status=faq.embedding_status,
            embedding_error=faq.embedding_error,
            embedding_input_hash=faq.embedding_input_hash,
            updated_at=faq.updated_at,
            updated_by=faq.updated_by,
        )
