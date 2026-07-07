from datetime import datetime
from hashlib import sha256

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.faq import KbFaq, KbFaqParaphrase


class FaqRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        category_l1: str | None,
        status: int | None,
    ) -> tuple[list[KbFaq], int, dict[int, list[str]]]:
        filters = [KbFaq.deleted_at.is_(None)]
        if keyword:
            like_keyword = f"%{keyword}%"
            filters.append(
                or_(
                    KbFaq.knowledge_id.like(like_keyword),
                    KbFaq.standard_question.like(like_keyword),
                    KbFaq.answer.like(like_keyword),
                )
            )
        if category_l1:
            filters.append(KbFaq.category_l1 == category_l1)
        if status is not None:
            filters.append(KbFaq.status == status)

        total = await self.session.scalar(select(func.count(KbFaq.id)).where(*filters))
        statement: Select[tuple[KbFaq]] = (
            select(KbFaq)
            .where(*filters)
            .order_by(KbFaq.updated_at.desc(), KbFaq.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        faqs = list((await self.session.scalars(statement)).all())
        paraphrases = await self._load_paraphrases([faq.id for faq in faqs])
        return faqs, int(total or 0), paraphrases

    async def get_by_id(self, faq_id: int, *, for_update: bool = False) -> KbFaq | None:
        statement = select(KbFaq).where(
            KbFaq.id == faq_id,
            KbFaq.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def replace_paraphrases(
        self,
        *,
        faq_id: int,
        values: list[str],
        updated_by: str,
        now: datetime,
    ) -> None:
        existing = list(
            (
                await self.session.scalars(
                    select(KbFaqParaphrase).where(KbFaqParaphrase.faq_id == faq_id)
                )
            ).all()
        )
        existing_by_hash = {item.text_hash: item for item in existing}
        active_hashes: set[str] = set()

        for sort_order, text in enumerate(values):
            normalized = " ".join(text.split())
            text_hash = sha256(normalized.encode("utf-8")).hexdigest()
            active_hashes.add(text_hash)
            item = existing_by_hash.get(text_hash)
            if item is None:
                self.session.add(
                    KbFaqParaphrase(
                        faq_id=faq_id,
                        paraphrase_text=text,
                        normalized_text=normalized,
                        text_hash=text_hash,
                        source_type=0,
                        status=True,
                        sort_order=sort_order,
                        created_by=updated_by,
                        updated_by=updated_by,
                        created_at=now,
                        updated_at=now,
                    )
                )
                continue

            item.paraphrase_text = text
            item.normalized_text = normalized
            item.status = True
            item.sort_order = sort_order
            item.updated_by = updated_by
            item.updated_at = now
            item.deleted_at = None

        for item in existing:
            if item.text_hash not in active_hashes and item.deleted_at is None:
                item.status = False
                item.updated_by = updated_by
                item.updated_at = now
                item.deleted_at = now

    async def _load_paraphrases(self, faq_ids: list[int]) -> dict[int, list[str]]:
        if not faq_ids:
            return {}
        rows = (
            await self.session.execute(
                select(KbFaqParaphrase.faq_id, KbFaqParaphrase.paraphrase_text)
                .where(
                    KbFaqParaphrase.faq_id.in_(faq_ids),
                    KbFaqParaphrase.status.is_(True),
                    KbFaqParaphrase.deleted_at.is_(None),
                )
                .order_by(
                    KbFaqParaphrase.faq_id,
                    KbFaqParaphrase.sort_order,
                    KbFaqParaphrase.id,
                )
            )
        ).all()
        result: dict[int, list[str]] = {}
        for faq_id, text in rows:
            result.setdefault(faq_id, []).append(text)
        return result

