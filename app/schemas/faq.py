from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import PageData


class FaqItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_id: str
    version: int
    category_l1: str | None
    category_l2: str | None
    category_l3: str | None
    standard_question: str
    paraphrases: list[str] = Field(default_factory=list)
    answer: str
    user_role: str
    business_type: str | None
    risk_level: int
    auth_required: bool
    auto_answer: bool
    human_required: bool
    status: int
    review_status: int
    updated_at: datetime
    updated_by: str | None


class FaqListData(PageData[FaqItem]):
    pass


class FaqUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    category_l1: str | None = Field(default=None, max_length=100)
    category_l2: str | None = Field(default=None, max_length=100)
    category_l3: str | None = Field(default=None, max_length=100)
    standard_question: str = Field(min_length=1, max_length=500)
    paraphrases: list[str] = Field(default_factory=list, max_length=50)
    answer: str = Field(min_length=1, max_length=20000)
    user_role: str = Field(default="common", max_length=20)
    business_type: str | None = Field(default=None, max_length=50)
    risk_level: int = Field(ge=0, le=2)
    auth_required: bool
    auto_answer: bool
    human_required: bool = False
    status: int = Field(ge=0, le=2)
    review_status: int = Field(default=0, ge=0, le=2)
    updated_by: str = Field(default="客服运营", min_length=1, max_length=64)

    @field_validator(
        "category_l1",
        "category_l2",
        "category_l3",
        "business_type",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("standard_question", "answer", "user_role", "updated_by")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("paraphrases")
    @classmethod
    def normalize_paraphrases(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in seen:
                result.append(normalized)
                seen.add(normalized)
        return result


class FaqDeleteData(BaseModel):
    id: int
    status: int

