from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.v1.endpoints.faqs import (
    get_faq_embedding_service as get_faq_embedding_service_for_faqs,
)
from app.api.v1.endpoints.search import (
    get_faq_embedding_service as get_faq_embedding_service_for_search,
)
from app.main import app
from app.schemas.embedding import FaqEmbeddingData, FaqEmbeddingRebuildData, FaqSearchData
from app.services.faq_embedding import build_faq_embedding_text

client = TestClient(app)


class FakeFaqEmbeddingService:
    async def generate_faq_embedding(self, faq_id: int) -> FaqEmbeddingData:
        return FaqEmbeddingData(
            faq_id=faq_id,
            knowledge_id=f"FAQ_{faq_id}",
            embedding_status=1,
            embedding_input_hash="abc",
            embedding_model="BAAI/bge-m3",
            embedding_dimension=1024,
        )

    async def rebuild_embeddings(
        self, *, limit: int, only_pending: bool
    ) -> FaqEmbeddingRebuildData:
        return FaqEmbeddingRebuildData(
            total=1,
            succeeded=1,
            failed=0,
            items=[
                {
                    "faq_id": 1,
                    "success": True,
                    "message": f"limit={limit}, only_pending={only_pending}",
                }
            ],
        )

    async def search_faqs(self, *, query: str, top_k: int) -> FaqSearchData:
        return FaqSearchData(
            query=query,
            top_k=top_k,
            items=[
                {
                    "faq_id": 1,
                    "knowledge_id": "FAQ_1",
                    "score": 0.88,
                    "standard_question": "如何实名认证？",
                    "answer": "请在账户中心提交认证资料。",
                    "category_l1": "账户",
                    "status": 1,
                }
            ],
        )


def override_faq_embedding_service() -> FakeFaqEmbeddingService:
    return FakeFaqEmbeddingService()


def test_generate_faq_embedding_endpoint() -> None:
    app.dependency_overrides[get_faq_embedding_service_for_faqs] = override_faq_embedding_service
    try:
        response = client.post("/api/v1/faqs/1/embedding")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["faq_id"] == 1
    assert body["data"]["embedding_dimension"] == 1024


def test_rebuild_faq_embeddings_endpoint() -> None:
    app.dependency_overrides[get_faq_embedding_service_for_faqs] = override_faq_embedding_service
    try:
        response = client.post(
            "/api/v1/faqs/embeddings/rebuild",
            json={"limit": 10, "only_pending": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["succeeded"] == 1
    assert body["data"]["failed"] == 0


def test_search_faqs_endpoint() -> None:
    app.dependency_overrides[get_faq_embedding_service_for_search] = override_faq_embedding_service
    try:
        response = client.post(
            "/api/v1/search/faqs",
            json={"query": "实名认证怎么做", "top_k": 3},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["query"] == "实名认证怎么做"
    assert body["data"]["items"][0]["score"] == 0.88


def test_build_faq_embedding_text() -> None:
    faq = SimpleNamespace(
        standard_question="如何实名认证？",
        answer="请在账户中心提交认证资料。",
        category_l1="账户",
        category_l2="认证",
        category_l3=None,
        user_role="common",
        business_type="account",
    )

    text = build_faq_embedding_text(faq, ["实名认证在哪里做？"])

    assert "问题：如何实名认证？" in text
    assert "相似问法：实名认证在哪里做？" in text
    assert "答案：请在账户中心提交认证资料。" in text
    assert "三级分类" not in text
