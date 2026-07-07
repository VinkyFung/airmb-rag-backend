from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.faq import KbFaq
from app.schemas.faq import FaqUpdate
from app.services.faq import FaqService


def make_faq() -> KbFaq:
    return KbFaq(
        id=1,
        knowledge_id="FAQ-001",
        version=2,
        category_l1="平台服务",
        category_l2="账户管理",
        category_l3=None,
        standard_question="旧问题",
        answer="旧答案",
        user_role="common",
        business_type="账户",
        risk_level=0,
        auth_required=False,
        auto_answer=True,
        human_required=False,
        status=1,
        review_status=1,
        embedding_status=2,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def make_payload(version: int = 2) -> FaqUpdate:
    return FaqUpdate(
        version=version,
        category_l1="平台服务",
        category_l2="账户管理",
        standard_question="新问题",
        paraphrases=["问法一", "问法一", " 问法二 "],
        answer="新答案",
        business_type="账户",
        risk_level=1,
        auth_required=True,
        auto_answer=True,
        status=1,
    )


@pytest.mark.asyncio
async def test_update_faq_increments_version_and_resets_embedding() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = FaqService(session)
    faq = make_faq()
    service.repository.get_by_id = AsyncMock(return_value=faq)
    service.repository.replace_paraphrases = AsyncMock()

    result = await service.update_faq(1, make_payload())

    assert result.version == 3
    assert result.standard_question == "新问题"
    assert result.paraphrases == ["问法一", "问法二"]
    assert faq.embedding_status == 0
    assert faq.content_hash
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_faq_rejects_stale_version() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = FaqService(session)
    service.repository.get_by_id = AsyncMock(return_value=make_faq())

    with pytest.raises(BusinessError) as exc_info:
        await service.update_faq(1, make_payload(version=1))

    assert exc_info.value.code == "FAQ_VERSION_CONFLICT"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_faq_is_soft_delete() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = FaqService(session)
    faq = make_faq()
    service.repository.get_by_id = AsyncMock(return_value=faq)

    result = await service.delete_faq(1, updated_by="客服运营")

    assert result.status == 2
    assert faq.deleted_at is not None
    assert faq.auto_answer is False
    assert faq.version == 3
    session.commit.assert_awaited_once()

