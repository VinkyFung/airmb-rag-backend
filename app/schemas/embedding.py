from pydantic import BaseModel, ConfigDict, Field


class FaqEmbeddingData(BaseModel):
    faq_id: int
    knowledge_id: str
    embedding_status: int
    embedding_input_hash: str | None
    embedding_model: str
    embedding_dimension: int


class FaqEmbeddingRebuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=1000)
    only_pending: bool = True


class FaqEmbeddingRebuildItem(BaseModel):
    faq_id: int
    success: bool
    message: str


class FaqEmbeddingRebuildData(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[FaqEmbeddingRebuildItem]


class FaqSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class FaqSearchItem(BaseModel):
    faq_id: int
    knowledge_id: str | None = None
    score: float
    standard_question: str | None = None
    answer: str | None = None
    category_l1: str | None = None
    category_l2: str | None = None
    category_l3: str | None = None
    status: int | None = None


class FaqSearchData(BaseModel):
    query: str
    top_k: int
    items: list[FaqSearchItem]

