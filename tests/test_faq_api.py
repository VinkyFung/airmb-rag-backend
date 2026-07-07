from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.faqs import get_faq_service
from app.main import app
from app.schemas.common import PageMeta
from app.schemas.faq import FaqDeleteData, FaqItem, FaqListData, FaqUpdate


def make_item(*, version: int = 2, question: str = "如何修改手机号？") -> FaqItem:
    return FaqItem(
        id=1,
        knowledge_id="FAQ-ACCOUNT-001",
        version=version,
        category_l1="平台服务",
        category_l2="账户管理",
        category_l3=None,
        standard_question=question,
        paraphrases=["手机号怎么换"],
        answer="进入账号与安全页面修改。",
        user_role="common",
        business_type="账户",
        risk_level=1,
        auth_required=True,
        auto_answer=True,
        human_required=False,
        status=1,
        review_status=1,
        updated_at=datetime(2026, 7, 7, 12, 0, 0),
        updated_by="客服运营",
    )


class FakeFaqService:
    async def list_faqs(self, **_: object) -> FaqListData:
        return FaqListData(
            items=[make_item()],
            pagination=PageMeta(page=1, page_size=20, total=1),
        )

    async def update_faq(self, faq_id: int, payload: FaqUpdate) -> FaqItem:
        assert faq_id == 1
        return make_item(version=payload.version + 1, question=payload.standard_question)

    async def delete_faq(self, faq_id: int, *, updated_by: str) -> FaqDeleteData:
        assert faq_id == 1
        assert updated_by == "客服运营"
        return FaqDeleteData(id=faq_id, status=2)


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_faq_service] = FakeFaqService
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_list_faqs_contract(client: TestClient) -> None:
    response = client.get(
        "/api/v1/faqs",
        params={"page": 1, "page_size": 20, "status": 1},
    )

    assert response.status_code == 200
    assert response.json()["data"]["pagination"]["total"] == 1
    assert response.json()["data"]["items"][0]["knowledge_id"] == "FAQ-ACCOUNT-001"


def test_update_faq_contract(client: TestClient) -> None:
    response = client.put(
        "/api/v1/faqs/1",
        json={
            "version": 2,
            "category_l1": "平台服务",
            "category_l2": "账户管理",
            "category_l3": None,
            "standard_question": "手机号在哪里修改？",
            "paraphrases": ["手机号怎么换"],
            "answer": "进入账号与安全页面修改。",
            "user_role": "common",
            "business_type": "账户",
            "risk_level": 1,
            "auth_required": True,
            "auto_answer": True,
            "human_required": False,
            "status": 1,
            "review_status": 1,
            "updated_by": "客服运营",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["version"] == 3
    assert response.json()["data"]["standard_question"] == "手机号在哪里修改？"


def test_delete_faq_contract(client: TestClient) -> None:
    response = client.delete(
        "/api/v1/faqs/1",
        params={"updated_by": "客服运营"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"id": 1, "status": 2}

